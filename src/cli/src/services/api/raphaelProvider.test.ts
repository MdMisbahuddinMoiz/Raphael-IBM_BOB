/**
 * raphaelProvider.test.ts — IBM BOB boundary contract tests.
 *
 * Deterministic: a fake `fetchImpl` is injected; no network is used.
 * Proves the BOB `/runs/model` request/response contract, error taxonomy,
 * retry policy, redaction, and that no fake streaming/tool output is produced.
 */
import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import {
  buildRunModelRequest,
  createRaphaelClient,
  extractProvenance,
  getRaphaelProvenance,
  RaphaelProviderError,
  redactSecrets,
} from './raphaelProvider.js'

const MISSION = {
  mission_id: 'M-D6',
  description: 'D6 contract test',
  scope: 'src/',
  criteria: ['recover'],
  problem: { symptom_target: 'src/a.py' },
}

const BOB_RESULT = {
  run: {
    run_id: '20260101T000000_abc123',
    session_id: 'sess-1',
    mission: MISSION,
    workspace_root: '/ws',
    state: 'completed',
    terminal: true,
    gate_verdict: 'complete',
    plan_ids: ['P-1'],
    finding_ids: ['F-1'],
    failure_reason: null,
  },
  terminal: 'done',
  terminal_reason: '',
  turns: 4,
  gate_verdict: 'complete',
  tasks: { tasks: [] },
}

const ENV_KEYS = [
  'RAPHAEL_BOB_URL',
  'RAPHAEL_ORCHESTRATOR_URL',
  'RAPHAEL_API_KEY',
  'RAPHAEL_SESSION_ID',
  'RAPHAEL_MISSION_JSON',
  'RAPHAEL_BOB_PROVIDER',
  'RAPHAEL_BOB_MAX_TURNS',
  'RAPHAEL_BOB_TIMEOUT_MS',
  'RAPHAEL_BOB_MAX_RETRIES',
  'RAPHAEL_BOB_ALLOWED_HOSTS',
]

let snapshot: Record<string, string | undefined> = {}

function recordingFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const fetchImpl = (async (input: any, init: any) => {
    calls.push({ url: String(input), init })
    return handler(String(input), init)
  }) as unknown as typeof fetch
  return { fetchImpl, calls }
}

function jsonResponse(status: number, data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function client(overrides: Record<string, unknown> = {}) {
  return createRaphaelClient({
    sessionId: 'sess-1',
    mission: MISSION,
    retryBaseDelayMs: 0,
    ...overrides,
  } as any)
}

beforeEach(() => {
  snapshot = {}
  for (const k of ENV_KEYS) {
    snapshot[k] = process.env[k]
    delete process.env[k]
  }
})

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (snapshot[k] === undefined) delete process.env[k]
    else process.env[k] = snapshot[k]!
  }
})

describe('factory shape', () => {
  test('exposes a single non-recursive factory', () => {
    const c = client()
    expect(typeof c.messages.create).toBe('function')
    expect(typeof c.beta.messages.create).toBe('function')
  })
})

describe('config + validation', () => {
  test('missing session_id is a BOB_CONFIG_ERROR', async () => {
    const c = createRaphaelClient({ mission: MISSION } as any)
    await expect(c.messages.create({})).rejects.toMatchObject({ code: 'BOB_CONFIG_ERROR' })
  })

  test('missing mission is a BOB_CONFIG_ERROR', async () => {
    const c = createRaphaelClient({ sessionId: 's1' } as any)
    await expect(c.messages.create({})).rejects.toMatchObject({ code: 'BOB_CONFIG_ERROR' })
  })

  test('rejects unsupported URL scheme and embedded credentials', () => {
    expect(() => createRaphaelClient({ baseUrl: 'ftp://bob', sessionId: 's', mission: MISSION } as any))
      .toThrow(RaphaelProviderError)
    expect(() => createRaphaelClient({ baseUrl: 'http://u:p@bob:8787', sessionId: 's', mission: MISSION } as any))
      .toThrow(/credentials/)
  })

  test('enforces hostname allowlist', () => {
    expect(() => createRaphaelClient({
      baseUrl: 'http://evil.example:8787', sessionId: 's', mission: MISSION,
      allowedHosts: ['127.0.0.1'],
    } as any)).toThrow(/allowlisted/)
  })

  test('rejects unknown mission fields (mirrors BOB)', () => {
    expect(() => buildRunModelRequest({
      sessionId: 's', mission: { ...MISSION, bogus: 1 } as any,
    })).toThrow(/unknown mission fields/)
  })
})

describe('request serialization', () => {
  test('sends only the documented /runs/model body', async () => {
    const { fetchImpl, calls } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    const c = client({ fetchImpl, provider: 'openai-compatible', maxTurns: 7 })
    await c.messages.create({ messages: [{ role: 'user', content: 'hi' }], tools: [{}] })

    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('http://127.0.0.1:8787/runs/model')
    expect(calls[0].init.method).toBe('POST')
    const body = JSON.parse(String(calls[0].init.body))
    expect(body.session_id).toBe('sess-1')
    expect(body.provider).toBe('openai-compatible')
    expect(body.max_turns).toBe(7)
    expect(body.mission).toEqual({
      mission_id: 'M-D6', description: 'D6 contract test', scope: 'src/',
      criteria: ['recover'], problem: { symptom_target: 'src/a.py' },
    })
    for (const forbidden of ['messages', 'tools', 'target', 'mode', 'persona', 'opsec', 'prompt', 'system', 'stream']) {
      expect(body).not.toHaveProperty(forbidden)
    }
  })

  test('does not forward arbitrary incoming auth headers', async () => {
    const { fetchImpl, calls } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    const c = client({
      fetchImpl,
      apiKey: 'bob-key',
      defaultHeaders: { Authorization: 'Bearer anthropic-secret', 'X-Trace': 't' },
    })
    await c.messages.create({})
    const headers = calls[0].init.headers as Record<string, string>
    expect(headers['X-API-Key']).toBe('bob-key')
    expect(JSON.stringify(headers)).not.toContain('anthropic-secret')
    expect(headers['Authorization']).toBeUndefined()
    expect(headers['X-Trace']).toBeUndefined()
  })

  test('omits X-API-Key when no key is configured', async () => {
    const { fetchImpl, calls } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    await client({ fetchImpl }).messages.create({})
    expect((calls[0].init.headers as Record<string, string>)['X-API-Key']).toBeUndefined()
  })
})

describe('response normalization (BOB authoritative)', () => {
  test('preserves the raw BOB result and does not fabricate usage/stop_reason', async () => {
    const { fetchImpl } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    const msg: any = await client({ fetchImpl }).messages.create({ model: 'raphael' })
    expect(msg.raphael.provider).toBe('ibm-bob')
    expect(msg.raphael.raw).toEqual(BOB_RESULT)
    expect(msg.raphael.provenance.run_id).toBe('20260101T000000_abc123')
    expect(msg.raphael.provenance.gate_verdict).toBe('complete')
    expect(msg.stop_reason).toBeNull()
    expect(msg.usage).toBeNull()
    expect(msg.content).toHaveLength(1)
    expect(msg.content[0].type).toBe('text')
    expect(msg.content[0].text).toContain('20260101T000000_abc123')
    expect(msg.content[0].text).toContain('gate_verdict=complete')
    // No fabricated tool calls.
    expect(msg.content.some((b: any) => b.type === 'tool_use')).toBe(false)
  })

  test('extractProvenance / getRaphaelProvenance expose BOB identifiers', async () => {
    const { fetchImpl } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    const msg: any = await client({ fetchImpl }).messages.create({})
    expect(extractProvenance(BOB_RESULT).plan_ids).toEqual(['P-1'])
    expect(getRaphaelProvenance(msg)?.finding_ids).toEqual(['F-1'])
    expect(getRaphaelProvenance(null)).toBeNull()
  })
})

describe('error taxonomy', () => {
  const cases: Array<[number, string, number]> = [
    [400, 'BOB_BAD_REQUEST', 1],
    [401, 'BOB_AUTH_ERROR', 1],
    [403, 'BOB_AUTH_ERROR', 1],
    [404, 'BOB_BAD_REQUEST', 1],
    [422, 'BOB_BAD_REQUEST', 1],
    [429, 'BOB_RATE_LIMIT', 3],
    [500, 'BOB_SERVER_ERROR', 3],
    [503, 'BOB_SERVER_ERROR', 3],
  ]
  for (const [status, code, expectedCalls] of cases) {
    test(`HTTP ${status} -> ${code} (${expectedCalls} call(s))`, async () => {
      const { fetchImpl, calls } = recordingFetch(() => new Response('err-body', { status }))
      const c = client({ fetchImpl, maxRetries: 2 })
      await expect(c.messages.create({})).rejects.toMatchObject({ code, status })
      expect(calls).toHaveLength(expectedCalls)
    })
  }

  test('503 MODEL_NOT_CONFIGURED -> BOB_CONFIG_ERROR (configuration, not retried)', async () => {
    const body = JSON.stringify({ error: { code: 'MODEL_NOT_CONFIGURED', message: 'no provider' } })
    const { fetchImpl, calls } = recordingFetch(() => new Response(body, { status: 503 }))
    await expect(client({ fetchImpl, maxRetries: 3 }).messages.create({}))
      .rejects.toMatchObject({ code: 'BOB_CONFIG_ERROR', status: 503 })
    expect(calls).toHaveLength(1)
  })

  test('retries a transient 500 then succeeds', async () => {
    let n = 0
    const { fetchImpl, calls } = recordingFetch(() => (++n === 1 ? new Response('boom', { status: 500 }) : jsonResponse(201, BOB_RESULT)))
    const msg: any = await client({ fetchImpl, maxRetries: 2 }).messages.create({})
    expect(calls).toHaveLength(2)
    expect(msg.raphael.provenance.run_id).toBe('20260101T000000_abc123')
  })

  test('network failure -> BOB_NETWORK_ERROR (retried)', async () => {
    const { fetchImpl, calls } = recordingFetch(() => { throw new TypeError('fetch failed') })
    await expect(client({ fetchImpl, maxRetries: 1 }).messages.create({}))
      .rejects.toMatchObject({ code: 'BOB_NETWORK_ERROR' })
    expect(calls).toHaveLength(2)
  })

  test('malformed success body -> BOB_INVALID_RESPONSE (not retried)', async () => {
    const { fetchImpl, calls } = recordingFetch(() => new Response('<html>nope</html>', { status: 200 }))
    await expect(client({ fetchImpl, maxRetries: 3 }).messages.create({}))
      .rejects.toMatchObject({ code: 'BOB_INVALID_RESPONSE' })
    expect(calls).toHaveLength(1)
  })

  test('timeout -> BOB_TIMEOUT', async () => {
    const fetchImpl = ((_u: any, init: any) => new Promise((_r, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })) as unknown as typeof fetch
    await expect(client({ fetchImpl, timeout: 10, maxRetries: 0 }).messages.create({}))
      .rejects.toMatchObject({ code: 'BOB_TIMEOUT' })
  })
})

describe('security', () => {
  test('redacts the configured secret from error diagnostics', async () => {
    const { fetchImpl } = recordingFetch(() => new Response('key=SECRET-KEY leaked', { status: 400 }))
    const c = client({ fetchImpl, apiKey: 'SECRET-KEY' })
    let caught: any
    try {
      await c.messages.create({})
    } catch (e) {
      caught = e
    }
    expect(caught.code).toBe('BOB_BAD_REQUEST')
    expect(caught.message).not.toContain('SECRET-KEY')
    expect(caught.message).toContain('[REDACTED]')
  })

  test('redactSecrets masks auth headers and credential URLs', () => {
    const out = redactSecrets('x-api-key: abc\nAuthorization: Bearer tok\nhttp://u:p@h/x', ['tok'])
    expect(out).not.toContain('abc')
    expect(out).not.toContain('tok')
    expect(out).not.toContain('u:p@')
    expect(out).toContain('[REDACTED]')
  })
})

describe('streaming is explicitly unsupported (not faked)', () => {
  test('beta stream:true rejects with BOB_STREAMING_UNSUPPORTED', async () => {
    const { fetchImpl, calls } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    await expect(client({ fetchImpl }).beta.messages.create({}, { stream: true }))
      .rejects.toMatchObject({ code: 'BOB_STREAMING_UNSUPPORTED' })
    expect(calls).toHaveLength(0)
  })

  test('beta non-streaming performs a synchronous BOB run', async () => {
    const { fetchImpl, calls } = recordingFetch(() => jsonResponse(201, BOB_RESULT))
    const msg: any = await client({ fetchImpl }).beta.messages.create({}, {})
    expect(calls).toHaveLength(1)
    expect(msg.raphael.raw).toEqual(BOB_RESULT)
  })
})
