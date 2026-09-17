# Phase 2C — Isolation Engineering Preparation (Design Only)

**DESIGN / PREPARATION ONLY.** No provider execution, no `npm ci`, no isolation
provisioning, no probes, no live proof. **M1/M2/M5 remain OPEN.** Live provider
execution is **NOT AUTHORIZED**.

Source of record: pinned T3MP3ST at `/home/moiz/audit-repos/T3MP3ST`
(`29824d5625ede419ac8cdae418c8f4c72c6270f7`, tree clean, unmodified).

## 1. Provider install analysis (Part 1) — NOT executed

| item | finding |
|---|---|
| `engines.node` | `>=22.19.0` → host node `v22.22.1` **satisfies** |
| package manager | none declared (`packageManager` absent) |
| lockfile | `package-lock.json`, `lockfileVersion 3`, **477 packages**, 476 `integrity` + 476 `resolved` URLs |
| type | ESM (`"type": "module"`) |
| build/start scripts | `build: tsc`, `start: node dist/cli.js`, `server: tsx src/server.ts`, `server:prod: node dist/server.js`, `dev: tsx src/cli.ts` |
| runtime deps | `@modelcontextprotocol/sdk`, `ajv`, `boxen`, `chalk`, `cli-table3`, `commander`, `conf`, `cors`, `dotenv`, `eventemitter3`, `express`, `figlet`, `gradient-string`, `inquirer`, `ora`, **`playwright`**, `socks`, `tree-sitter-wasms`, `tsx`, `undici`, `web-tree-sitter` |
| possible native/system dep | **`playwright`** (downloads browsers unless skipped) |
| offline install possible? | **NO** from current local state — `node_modules` absent and 476 packages resolve to the npm registry |
| integrity info available locally | **YES** — 476 lockfile `integrity` (sha512) + `resolved` entries |
| modifies provider source? | **NO** — `npm ci` writes only `node_modules/` + possibly playwright cache |

### PROVIDER INSTALL REQUEST (do NOT execute)

```
COMMAND (eventual, not run):  cd /home/moiz/audit-repos/T3MP3ST && npm ci
  (playwright browsers:       PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1, unless the
                               proof path requires a browser — C1A does not)
EXPECTED NETWORK:             registry.npmjs.org (HTTPS/443) for ~476 packages;
                              plus Playwright browser CDN (cdn.playwright.dev)
                              unless skipped
EXPECTED ARTIFACTS:           /home/moiz/audit-repos/T3MP3ST/node_modules/**
                              (+ playwright browser cache if not skipped)
EXPECTED RISKS:               supply-chain (npm lifecycle scripts), network
                              egress from the build host, disk growth; the
                              provider SOURCE tree is not modified
REQUIRED AUTHORIZATION:       explicit ChatGPT authorization to run `npm ci`
                              (network/package installation)
```

## 2. Execution-export channel design (Part 2)

B4 needs a SECONDARY provider-execution record to cross-check the PRIMARY
RAPHAEL boundary events. The provider exposes `getExecutions()` **only
in-process** (`src/arsenal/index.ts:484`); there is **no HTTP endpoint** for it.
The provider does emit `ArsenalEvents` (`class Arsenal extends
EventEmitter<ArsenalEvents>`, `index.ts:319`) — `tool:registered`,
`tool:executed`, `tool:error`.

| option | trust model | attribution | out-of-proc | complexity | provider changes | fork | B4 correlation | failure modes | can stay SECONDARY |
|---|---|---|---|---|---|---|---|---|---|
| **A** provider HTTP endpoint for `getExecutions()` | provider-trusted | high | yes | high (new provider surface) | **YES** (add endpoint) | effectively | via echoed ids | endpoint not present; broadens provider API | yes but forbidden |
| **B** RAPHAEL-kept transcript (launcher observes provider events) | RAPHAEL-observed | high | yes (launcher is the out-of-process boundary) | medium | **NO** | no | direct (launcher sees both) | launcher bugs; process-boundary trust | yes |
| **C** bounded execution event export (subscribe to `ArsenalEvents`, pipe JSON) | provider-emitted, RAPHAEL-observed | high | yes | medium | **NO** | no | direct | event loss if not flushed | yes |

**Selected: B + C (one RAPHAEL-owned launcher).** A RAPHAEL-authored launcher runs
**inside the sandbox**, in-process with the pinned provider: it constructs an
`Arsenal`, registers/selects only `binary_sink_scan`, subscribes to
`tool:executed`/`tool:error` (**PRIMARY transcript**, provider-emitted and
observed at the process boundary), calls `Arsenal.execute('binary_sink_scan', ctx)`
exactly once, then reads `getExecutions()` (**SECONDARY**) and emits a bounded
JSON transcript on stdout. Rationale: **no provider fork, no provider source
change, no broad management API**; the transcript and `getExecutions()` are
captured in the same isolated process and correlated by RAPHAEL-assigned ids.

**Trust caveat (recorded):** the launcher and provider share a process, so
`getExecutions()` is provider-trusted. The **PRIMARY** record stays the
RAPHAEL-observed boundary event stream; provider metadata never overrides it.
**No clean *pure-HTTP* export exists without modifying/forking T3MP3ST** — stated
explicitly.

## 3. Fresh-instance lifecycle (Part 3, refined)

```
CREATE            one fresh launcher process inside a fresh sandbox instance
  → verify identity    pin SHA + module digest + launcher digest
  → proof_session_id   RAPHAEL-assigned (immutable)
  → bind instance      instance_id = invocation_id (one launcher = one proof)
  → clean history      launcher constructs a NEW Arsenal (no shared registry);
                       assert getExecutions().length == 0 before execute
  → execute ONE        binary_sink_scan on the exact fixture literal
  → collect PRIMARY    subscribe tool:executed/tool:error → boundary transcript
  → collect SECONDARY  getExecutions() snapshot
  → B4 attestation     expected_calls = 1 (b4_attestation.attest)
  → teardown           kill launcher + sandbox
  → verify teardown    external observation (PID gone / cgroup empty) → M5
  → discard            no reuse of the instance or sandbox
```

- **Instance identity:** launcher process id + sandbox id + pin SHA + module
  digest, asserted before binding.
- **Freshness guarantee:** new process + new `Arsenal` instance; no registry
  reuse; the pre-execution `getExecutions() == []` assertion is the evidence.
- **Dedication evidence:** one launcher ↔ one proof_session_id ↔ one invocation.
- **Teardown evidence:** reaped PID + empty cgroup (see §5).
- Implementable **without modifying T3MP3ST** (uses its public `Arsenal` API).

## 4. Isolation architecture (Part 4)

Candidate (no container runtime present): **`bwrap` + user namespace + cgroup v2
+ seccomp + tmpfs**, single-file, read-only fixture. Chosen over raw
`unshare/setpriv/chroot` because `bwrap` composes the mount + userns + no-new-privs
controls declaratively and is auditable.

**FILESYSTEM**
- bind **only** `fixtures/c1a_proof/` → `/fixture` **read-only** (`--ro-bind`)
- provider source bound **read-only** at `/provider`
- `node_modules` (post-install) bound **read-only**
- **scratch**: one small `tmpfs` (`--tmpfs /tmp`, size-capped) only if the
  provider requires it; otherwise absent
- no `$HOME`, no `/etc` beyond `resolv`-free minimal, **no docker socket**,
  no unrelated writable mounts, no writable provider source

**NETWORK**
- `--unshare-net` (no interfaces / no DNS / no route) — egress denied
- verify with an egress probe **only after** authorization (M2, not now)

**PROCESS**
- non-root (`--unshare-user --uid 1000`), `--die-with-parent`, `--new-session`
- `--cap-drop ALL`, **no-new-privileges**
- cgroup v2: `memory.max`, `pids.max`, `cpu.max` bounds
- hard wall-clock timeout; on expiry RAPHAEL stops waiting (see §5)

**SECURITY**
- seccomp filter (deny `socket`, `execve` beyond node, `ptrace`, mount) once
  curated; `noexec,nosuid,nodev` on non-exec mounts; device policy: no host
  devices; minimal `/dev` (`--dev /dev`)

**M1/M2 remain OPEN**: this is a *specification*. Escape probes (M1) and egress
probes (M2) are required before closure.

## 5. M5 teardown design (Part 5)

```
timeout / stop
  → RAPHAEL stops waiting                     (does NOT imply termination)
  → orphan_possible = true  unless termination is OBSERVED
  → cancellation_acknowledged = true ONLY after external observation:
        (a) launcher PID reaped (waitpid → gone), AND
        (b) sandbox process tree gone (no descendant PIDs), AND
        (c) cgroup emptied (cgroup.events populated=0) — where used
  → teardown evidence recorded (pids, cgroup state, monotonic times)
```

No "cancelled = terminated" claim. Late provider output after stop is cut off
and recorded as `late_output:true`; it can never become success. Implemented
only at the live stage.

## 6. Checklist changes (Part 6)

`docs/integration/phase-2c-first-proof-checklist.json` gains a
`readiness_stage` distinction:

- `READY_FOR_PROVISIONING_DESIGN` — design artifacts complete.
- `READY_FOR_LIVE_PROOF` — false for every item until the environment exists and
  is independently verified.

M1/M2/M5 are **NOT** marked READY. G0/G2/B4/C1A/M4/M7 stay `READY` (contract /
artifact items) with `ready_for_live_proof: false`.

## 7. Status, blockers, authorizations

**Blockers before live proof:** (1) `npm ci` authorization + execution;
(2) isolation sandbox implementation (bwrap spec → concrete args);
(3) out-of-process launcher + transport (Protocol, not implemented);
(4) fresh-instance lifecycle implementation + empty-history assertion;
(5) M5 teardown observation; (6) M1 escape probes + M2 egress probes;
(7) golden expected result captured at the authorized proof.

**Authorizations still required:** (a) run `npm ci`; (b) provision the isolation
sandbox; (c) run escape/egress probes; (d) execute the single live provider
proof.

**M1: OPEN. M2: OPEN. M5: OPEN. Live provider execution: NOT AUTHORIZED.**
