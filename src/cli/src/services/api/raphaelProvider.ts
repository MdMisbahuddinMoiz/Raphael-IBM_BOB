/**
 * raphaelProvider — IBM BOB model/runtime boundary adapter.
 *
 * Raphael/OpenClaude expects an Anthropic-shaped model client. IBM BOB is
 * NOT a chat-completion API: its authoritative boundary is the synchronous,
 * governed `POST /runs/model`, which accepts a session + mission and returns
 * a governed run result (gate verdict, findings, plans, turns).
 *
 * This module is the thinnest possible compatibility layer:
 *   - it builds a valid BOB `/runs/model` request from real run context;
 *   - it normalizes the BOB envelope into the Anthropic message shape the
 *     surrounding code consumes, while preserving the RAW BOB result under
 *     `message.raphael` for provenance;
 *   - it never fabricates token streaming, tool calls, stop reasons, or
 *     usage (BOB provides none of these);
 *   - it never sends messages/tools/target/mode/persona/opsec/prompt/system
 *     (BOB does not accept them).
 *
 * BOB identifiers (run_id, session_id, mission_id, plan_ids, finding_ids,
 * terminal, gate_verdict, turns, failure_reason) are preserved verbatim.
 * Missing BOB fields stay null rather than being invented.
 *
 * Model output is UNTRUSTED data: this adapter returns it to the caller and
 * never treats it as instructions or executes anything.
 */

// ---------------------------------------------------------------------------
// Error taxonomy
// ---------------------------------------------------------------------------

export type BOBErrorCode =
  | 'BOB_CONFIG_ERROR'
  | 'BOB_AUTH_ERROR'
  | 'BOB_BAD_REQUEST'
  | 'BOB_RATE_LIMIT'
  | 'BOB_SERVER_ERROR'
  | 'BOB_TIMEOUT'
  | 'BOB_NETWORK_ERROR'
  | 'BOB_STREAM_ERROR'
  | 'BOB_INVALID_RESPONSE'
  | 'BOB_STREAMING_UNSUPPORTED'
  | 'RAPHAEL_PROVIDER_ERROR'

export class RaphaelProviderError extends Error {
  readonly code: BOBErrorCode
  readonly status?: number
  readonly retryable: boolean

  constructor(
    code: BOBErrorCode,
    message: string,
    opts?: { status?: number; retryable?: boolean },
  ) {
    super(message)
    this.name = 'RaphaelProviderError'
    this.code = code
    this.status = opts?.status
    this.retryable = opts?.retryable ?? false
  }
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export interface RaphaelMission {
  mission_id: string
  description?: string
  scope?: string
  criteria?: string[]
  problem?: Record<string, unknown>
}

export interface RaphaelClientOptions {
  /** Reserved for callers that pass provider headers; auth headers are NOT forwarded. */
  defaultHeaders?: Record<string, string>
  maxRetries?: number
  timeout?: number
  /** Base URL of IBM BOB (defaults to RAPHAEL_BOB_URL / RAPHAEL_ORCHESTRATOR_URL / loopback). */
  baseUrl?: string
  /** BOB API key (defaults to RAPHAEL_API_KEY). Never logged. */
  apiKey?: string
  /** CLI/run session id (defaults to RAPHAEL_SESSION_ID). Required to start a run. */
  sessionId?: string
  /** BOB mission (defaults to RAPHAEL_MISSION_JSON). Required to start a run. */
  mission?: RaphaelMission
  /** Optional BOB provider adapter name (defaults to RAPHAEL_BOB_PROVIDER). */
  provider?: string
  /** Optional max turns (defaults to RAPHAEL_BOB_MAX_TURNS). */
  maxTurns?: number
  /** Injectable fetch for deterministic tests. */
  fetchImpl?: typeof fetch
  /** Optional hostname allowlist (defaults to RAPHAEL_BOB_ALLOWED_HOSTS). */
  allowedHosts?: string[]
  /** Base delay for exponential backoff (ms). Tests set 0. */
  retryBaseDelayMs?: number
  reasoningEffort?: 'low' | 'medium' | 'high' | 'xhigh'
  providerOverride?: { model: string; baseURL: string; apiKey: string }
}

const DEFAULT_BASE_URL = 'http://127.0.0.1:8787'
const DEFAULT_TIMEOUT_MS = 600_000
const DEFAULT_MAX_RETRIES = 2
const MAX_ERROR_BODY_CHARS = 2_000

const MISSION_FIELDS = new Set([
  'mission_id',
  'description',
  'scope',
  'criteria',
  'problem',
])

function env(name: string): string | undefined {
  const v = process.env[name]
  return v === undefined || v === '' ? undefined : v
}

function parseInteger(raw: string | undefined, fallback: number): number {
  if (raw === undefined) return fallback
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n >= 0 ? n : fallback
}

function validateBaseUrl(raw: string, allowedHosts?: string[]): string {
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      'RAPHAEL_BOB_URL is not a valid URL',
    )
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      `unsupported BOB URL scheme: ${parsed.protocol}`,
    )
  }
  if (parsed.username || parsed.password) {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      'BOB URL must not embed credentials',
    )
  }
  const allow = allowedHosts ?? env('RAPHAEL_BOB_ALLOWED_HOSTS')?.split(',').map(s => s.trim()).filter(Boolean)
  if (allow && allow.length > 0 && !allow.includes(parsed.hostname)) {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      `BOB host not allowlisted: ${parsed.hostname}`,
    )
  }
  return parsed.toString().replace(/\/+$/, '')
}

// ---------------------------------------------------------------------------
// Secret redaction
// ---------------------------------------------------------------------------

/**
 * Remove secrets from arbitrary diagnostic text before it is surfaced.
 * Redacts the configured key, common auth header values, and
 * credential-bearing URLs. Never returns an api key.
 */
export function redactSecrets(text: string, secrets: Array<string | undefined> = []): string {
  let out = text
  for (const secret of secrets) {
    if (!secret) continue
    out = out.split(secret).join('[REDACTED]')
  }
  out = out.replace(/(x-api-key\s*[:=]\s*)\S+/gi, '$1[REDACTED]')
  out = out.replace(/(authorization\s*[:=]\s*)(bearer\s+)?\S+/gi, '$1[REDACTED]')
  out = out.replace(/([a-z][a-z0-9+.-]*:\/\/)[^/@\s]+@/gi, '$1[REDACTED]@')
  return out
}

// ---------------------------------------------------------------------------
// Request construction
// ---------------------------------------------------------------------------

function normalizeMission(mission: RaphaelMission): RaphaelMission {
  if (!mission || typeof mission !== 'object') {
    throw new RaphaelProviderError('BOB_CONFIG_ERROR', 'mission must be an object')
  }
  const unknown = Object.keys(mission).filter(k => !MISSION_FIELDS.has(k))
  if (unknown.length > 0) {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      `unknown mission fields: ${unknown.sort().join(', ')}`,
    )
  }
  if (typeof mission.mission_id !== 'string' || mission.mission_id.trim() === '') {
    throw new RaphaelProviderError('BOB_CONFIG_ERROR', 'mission.mission_id is required')
  }
  if (mission.criteria !== undefined && !Array.isArray(mission.criteria)) {
    throw new RaphaelProviderError('BOB_CONFIG_ERROR', 'mission.criteria must be an array')
  }
  if (mission.problem !== undefined && (typeof mission.problem !== 'object' || mission.problem === null || Array.isArray(mission.problem))) {
    throw new RaphaelProviderError('BOB_CONFIG_ERROR', 'mission.problem must be an object')
  }
  return {
    mission_id: mission.mission_id,
    description: mission.description ?? '',
    scope: mission.scope ?? '',
    criteria: mission.criteria ?? [],
    problem: mission.problem ?? {},
  }
}

/**
 * Build the exact BOB `/runs/model` body. Only documented fields are emitted;
 * chat-only fields (messages/tools/target/mode/persona/opsec/prompt/system/
 * stream) are never sent.
 */
export function buildRunModelRequest(input: {
  sessionId?: string
  mission?: RaphaelMission
  provider?: string
  maxTurns?: number
}): Record<string, unknown> {
  const sessionId = input.sessionId ?? env('RAPHAEL_SESSION_ID')
  if (!sessionId || sessionId.trim() === '') {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      'session_id is required: set RAPHAEL_SESSION_ID or pass options.sessionId',
    )
  }
  const mission = input.mission ?? parseMissionFromEnv()
  if (!mission) {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      'mission is required: pass options.mission or set RAPHAEL_MISSION_JSON',
    )
  }
  const body: Record<string, unknown> = {
    session_id: sessionId,
    mission: normalizeMission(mission),
  }
  const provider = input.provider ?? env('RAPHAEL_BOB_PROVIDER')
  if (provider) body.provider = provider
  const maxTurns = input.maxTurns ?? (env('RAPHAEL_BOB_MAX_TURNS') !== undefined
    ? parseInteger(env('RAPHAEL_BOB_MAX_TURNS'), 0)
    : undefined)
  if (maxTurns !== undefined && maxTurns > 0) body.max_turns = maxTurns
  return body
}

function parseMissionFromEnv(): RaphaelMission | undefined {
  const raw = env('RAPHAEL_MISSION_JSON')
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as RaphaelMission
  } catch {
    throw new RaphaelProviderError(
      'BOB_CONFIG_ERROR',
      'RAPHAEL_MISSION_JSON is not valid JSON',
    )
  }
}

// ---------------------------------------------------------------------------
// HTTP transport (timeout, cancellation, bounded retries)
// ---------------------------------------------------------------------------

function classifyResponse(status: number, bodyText: string): { code: BOBErrorCode; retryable: boolean } {
  if (status === 401 || status === 403) return { code: 'BOB_AUTH_ERROR', retryable: false }
  if (status === 429) return { code: 'BOB_RATE_LIMIT', retryable: true }
  if (status >= 500) {
    // BOB surfaces missing server-side model configuration as 503 with a
    // stable code; that is a configuration error, not a transient failure.
    let bobCode: string | undefined
    try {
      bobCode = JSON.parse(bodyText)?.error?.code
    } catch {
      bobCode = undefined
    }
    if (bobCode === 'MODEL_NOT_CONFIGURED' || /MODEL_NOT_CONFIGURED/.test(bodyText)) {
      return { code: 'BOB_CONFIG_ERROR', retryable: false }
    }
    return { code: 'BOB_SERVER_ERROR', retryable: true }
  }
  if (status >= 400 && status < 500) return { code: 'BOB_BAD_REQUEST', retryable: false }
  return { code: 'RAPHAEL_PROVIDER_ERROR', retryable: false }
}

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

interface TransportConfig {
  baseUrl: string
  apiKey?: string
  timeout: number
  maxRetries: number
  fetchImpl: typeof fetch
  retryBaseDelayMs: number
}

async function postRunModel(
  cfg: TransportConfig,
  body: Record<string, unknown>,
  callerSignal?: AbortSignal,
): Promise<{ status: number; data: unknown; rawText: string }> {
  const url = `${cfg.baseUrl}/runs/model`
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  // Auth header is constructed ONLY from the resolved key; arbitrary incoming
  // headers (including Anthropic credentials) are never forwarded.
  if (cfg.apiKey) headers['X-API-Key'] = cfg.apiKey

  let lastError: RaphaelProviderError | undefined
  for (let attempt = 0; attempt <= cfg.maxRetries; attempt++) {
    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, cfg.timeout)
    const onCallerAbort = () => controller.abort()
    callerSignal?.addEventListener('abort', onCallerAbort, { once: true })
    try {
      if (callerSignal?.aborted) {
        throw new RaphaelProviderError('RAPHAEL_PROVIDER_ERROR', 'request cancelled by caller')
      }
      const res = await cfg.fetchImpl(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      const rawText = await res.text()
      if (res.ok) {
        let data: unknown
        try {
          data = rawText.length > 0 ? JSON.parse(rawText) : {}
        } catch {
          throw new RaphaelProviderError(
            'BOB_INVALID_RESPONSE',
            `BOB returned non-JSON success body (status ${res.status})`,
            { status: res.status, retryable: false },
          )
        }
        return { status: res.status, data, rawText }
      }
      const { code, retryable } = classifyResponse(res.status, rawText)
      const safeBody = redactSecrets(rawText.slice(0, MAX_ERROR_BODY_CHARS), [cfg.apiKey])
      const err = new RaphaelProviderError(
        code,
        `${code} (HTTP ${res.status})${safeBody ? `: ${safeBody}` : ''}`,
        { status: res.status, retryable },
      )
      if (!retryable || attempt === cfg.maxRetries) throw err
      lastError = err
    } catch (e) {
      if (e instanceof RaphaelProviderError) {
        // Non-retryable or exhausted: rethrow.
        if (!e.retryable || attempt === cfg.maxRetries) throw e
        lastError = e
      } else if (timedOut) {
        const err = new RaphaelProviderError('BOB_TIMEOUT', `BOB request timed out after ${cfg.timeout}ms`, { retryable: true })
        if (attempt === cfg.maxRetries) throw err
        lastError = err
      } else if (callerSignal?.aborted) {
        throw new RaphaelProviderError('RAPHAEL_PROVIDER_ERROR', 'request cancelled by caller')
      } else {
        const err = new RaphaelProviderError(
          'BOB_NETWORK_ERROR',
          `BOB network error: ${redactSecrets(String((e as Error)?.message ?? e), [cfg.apiKey])}`,
          { retryable: true },
        )
        if (attempt === cfg.maxRetries) throw err
        lastError = err
      }
    } finally {
      clearTimeout(timer)
      callerSignal?.removeEventListener('abort', onCallerAbort)
    }
    if (attempt < cfg.maxRetries) {
      await sleep(cfg.retryBaseDelayMs * 2 ** attempt)
    }
  }
  throw lastError ?? new RaphaelProviderError('RAPHAEL_PROVIDER_ERROR', 'BOB request failed')
}

// ---------------------------------------------------------------------------
// Response normalization (Anthropic-shaped, raw BOB preserved)
// ---------------------------------------------------------------------------

export interface BOBProvenance {
  run_id: string | null
  session_id: string | null
  mission: Record<string, unknown> | null
  state: string | null
  terminal: unknown
  terminal_reason: unknown
  turns: unknown
  gate_verdict: string | null
  plan_ids: string[]
  finding_ids: string[]
  tasks: unknown
  failure_reason: string | null
}

function summarizeBobResult(data: any): string {
  const run = data?.run ?? {}
  const gate = data?.gate_verdict ?? run.gate_verdict ?? 'unknown'
  const state = run.state ?? 'unknown'
  const terminal = data?.terminal ?? 'unknown'
  const turns = data?.turns ?? 'unknown'
  const runId = run.run_id ?? 'unknown'
  return [
    `IBM BOB governed run ${runId}`,
    `state=${state}`,
    `gate_verdict=${gate}`,
    `terminal=${terminal}`,
    `turns=${turns}`,
  ].join(' ')
}

export function extractProvenance(data: any): BOBProvenance {
  const run = data?.run ?? {}
  const mission = run.mission && typeof run.mission === 'object'
    ? (run.mission as Record<string, unknown>)
    : null
  return {
    run_id: run.run_id ?? null,
    session_id: run.session_id ?? null,
    mission,
    state: run.state ?? null,
    terminal: data?.terminal ?? null,
    terminal_reason: data?.terminal_reason ?? null,
    turns: data?.turns ?? null,
    gate_verdict: data?.gate_verdict ?? run.gate_verdict ?? null,
    plan_ids: Array.isArray(run.plan_ids) ? run.plan_ids : [],
    finding_ids: Array.isArray(run.finding_ids) ? run.finding_ids : [],
    tasks: data?.tasks ?? null,
    failure_reason: run.failure_reason ?? null,
  }
}

/** Anthropic-shaped message with the raw BOB result retained under `raphael`. */
function normalizeBobResponse(data: any, requestedModel?: string) {
  const provenance = extractProvenance(data)
  return {
    id: provenance.run_id ?? `bob_${Date.now()}`,
    type: 'message',
    role: 'assistant',
    // The surrounding code consumes a single text block. This is a
    // deterministic translation, NOT fabricated streaming/tool output.
    content: [{ type: 'text', text: summarizeBobResult(data) }],
    model: requestedModel ?? provenance.mission?.['mission_id'] ?? 'raphael-bob',
    // BOB provides neither a stop_reason nor token usage; do not fabricate.
    stop_reason: null,
    stop_sequence: null,
    usage: null,
    // Preserved, untrusted BOB result for provenance/ActionReceipt consumers.
    raphael: {
      provider: 'ibm-bob',
      endpoint: '/runs/model',
      raw: data,
      provenance,
    },
  }
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createRaphaelClient(options: RaphaelClientOptions = {}) {
  const baseUrl = validateBaseUrl(
    options.baseUrl ?? env('RAPHAEL_BOB_URL') ?? env('RAPHAEL_ORCHESTRATOR_URL') ?? DEFAULT_BASE_URL,
    options.allowedHosts,
  )
  const apiKey = options.apiKey ?? env('RAPHAEL_API_KEY')
  const timeout = options.timeout ?? parseInteger(env('RAPHAEL_BOB_TIMEOUT_MS'), DEFAULT_TIMEOUT_MS)
  const maxRetries = options.maxRetries ?? parseInteger(env('RAPHAEL_BOB_MAX_RETRIES'), DEFAULT_MAX_RETRIES)
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  const retryBaseDelayMs = options.retryBaseDelayMs ?? 250

  if (typeof fetchImpl !== 'function') {
    throw new RaphaelProviderError('BOB_CONFIG_ERROR', 'no fetch implementation available')
  }

  const cfg: TransportConfig = { baseUrl, apiKey, timeout, maxRetries, fetchImpl, retryBaseDelayMs }

  const invoke = async (params: any, callOptions?: { signal?: AbortSignal }) => {
    const body = buildRunModelRequest({
      sessionId: params?.sessionId ?? options.sessionId,
      mission: params?.mission ?? options.mission,
      provider: params?.provider ?? options.provider,
      maxTurns: params?.maxTurns ?? options.maxTurns,
    })
    const { data } = await postRunModel(cfg, body, callOptions?.signal)
    if (data === null || typeof data !== 'object') {
      throw new RaphaelProviderError('BOB_INVALID_RESPONSE', 'BOB success body was not an object', { retryable: false })
    }
    return normalizeBobResponse(data, params?.model)
  }

  return {
    messages: {
      create: async (params: any, callOptions?: { signal?: AbortSignal }) => invoke(params, callOptions),
    },
    beta: {
      messages: {
        // BOB `/runs/model` is synchronous and does not stream model tokens.
        // A caller that genuinely requires token streaming is failed
        // explicitly rather than handed fabricated deltas.
        create: async (params: any, callOptions?: { stream?: boolean; signal?: AbortSignal }) => {
          if (callOptions?.stream) {
            throw new RaphaelProviderError(
              'BOB_STREAMING_UNSUPPORTED',
              'IBM BOB /runs/model is synchronous; token streaming is not supported. ' +
                'Use the non-streaming call or BOB /runs/{run_id}/events/stream for ledger observability.',
            )
          }
          return invoke(params, callOptions)
        },
      },
    },
  }
}

/** Convenience accessor for provenance-aware consumers (ActionReceipt/Episode Recorder). */
export function getRaphaelProvenance(message: any): BOBProvenance | null {
  return message?.raphael?.provenance ?? null
}

export const STREAMING_UNSUPPORTED = true
