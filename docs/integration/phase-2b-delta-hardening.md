# Phase 2B-δ — Pre-2C Hardening & Static Evidence Review

**STATUS: DESIGN / EVIDENCE ONLY. IMPLEMENTATION: PROHIBITED. PROVIDER EXECUTION: PROHIBITED. PHASE 2C: NOT AUTHORIZED.**

Labels used throughout: **VERIFIED FROM SOURCE** (file + symbol cited),
**INFERRED** (reasoning from verified source, not itself executed),
**UNKNOWN / NOT VERIFIED** (source path insufficient). No claim in this
document is backed by provider execution; none was performed.

Baseline / provenance:

| item | value |
|---|---|
| RAPHAEL HEAD | `98c9a078f5a3635a986882d061d78f97b35f310c` (`feature/raphael-harness-live-model`) |
| Phase 2B design authority | `docs/integration/phase-2b-provider-runtime-scope-result-design.md` |
| Compatibility audit | `docs/integration/decepticon-t3mp3st-compatibility-audit.md` |
| Decepticon pin | `PurpleAILAB/Decepticon@31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` (working tree clean) |
| T3MP3ST pin | `elder-plinius/T3MP3ST@29824d5625ede419ac8cdae418c8f4c72c6270f7` (working tree clean) |
| first proof capability | `C1 static_file_manifest` |

**This document does not claim that any invariant is satisfied because it is
specified.** Specification is a prerequisite, not evidence. Every acceptance
criterion below states what would *count* as evidence and whether it can be
obtained statically.

---

## A. REQUIREMENT + ACCEPTANCE CRITERIA — M1–M7

Each blocker is a REQUIREMENT with an observable ACCEPTANCE CRITERION. The
"Phase 2B status" column records what the accepted Phase 2B design claims
today: in every case the claim is *specification only* → **NOT CLOSED**.

### A.0 Summary

| # | blocker | invariant (compressed) | enforce layer | statically verifiable? | live exec needed? | status |
|---|---|---|---|---|---|---|
| M1 | filesystem-root enforcement | OS mount namespace makes out-of-root access impossible; provider cooperation not load-bearing | namespace + mounts + adapter + tests | partly (spec/mount table yes; escape resistance no) | partly (escape probes only) | NOT CLOSED |
| M2 | network egress denial | netns with zero interfaces + no DNS; seccomp socket deny as belt-and-braces | runtime + adapter + tests | partly (config yes; live egress test no) | partly (egress probes only) | NOT CLOSED |
| M3 | generic-execution prohibition | capability class = enforced syscall profile; C1 denies `execve`/`fork`/`socket`/`ptrace`… | seccomp + image minimality + static call-graph | partly (syscall policy + image manifest yes; conformance no) | partly (syscall trace of real provider) | NOT CLOSED |
| M4 | provider authority-field rejection | `ProviderResult` is a CLOSED allow-list schema; authority fields REJECTED, not ignored | adapter + closed parser + tests | yes | no | NOT CLOSED |
| M5 | cancellation acknowledgement | `cancellation.acknowledged` true only after externally observed termination | adapter + runtime + tests | partly (semantics yes; live teardown no) | partly | NOT CLOSED |
| M6 | provenance fail-closed | missing/malformed/mismatched provenance → fail closed; provider IDs never authoritative | adapter + runtime + tests | yes | no | NOT CLOSED |
| M7 | output limits / truncation | exceeding byte/entry/artifact limit MUST NOT be `success`; truncation is `partial` | adapter + parser + tests | yes | no | NOT CLOSED |

### A.1 M1 — filesystem-root enforcement

- **Threat / failure mode**: a C1 operation touches any path outside the single
  authorized engagement root — by absolute path, `..`, symlink, hardlink,
  `/proc` fd, or a provider-side second mount.
- **Required invariant**: the container/mount namespace makes anything outside
  `{authorized root (ro), scratch tmpfs (rw, size-capped), provider runtime (ro)}`
  unreachable through OS mechanisms. Provider-side path checks are
  defence-in-depth, **not** load-bearing.
- **Enforcement layer**: container runtime / mount namespace + `ProviderRuntime`
  adapter + RAPHAEL ledger recording the sandbox config digest + tests.
- **Observable acceptance criterion**: given a sandbox instance, an escape-probe
  suite (symlink, hardlink, `..`, `/proc/self/fd`, `/proc/<pid>/root`,
  open-by-handle/`openat2` `RESOLVE_NO_XDEV`, TOCTOU) returns
  `denied`/`unavailable` for every out-of-root read, **and** an
  adapter-side consistency check refuses to invoke when the running sandbox's
  config digest ≠ the digest bound in the `ScopeHandoff`.
- **Evidence required before Phase 2C**: versioned sandbox spec; exact mount
  table; assertion that no `hostPath`, no docker socket, no host `/proc` is
  mounted; escape-probe results; env allow-list dump == allow-list.
- **Statically verifiable?**: mount/config assertions **yes**; escape
  resistance **no** (requires executing probe code — not the provider).
- **Live provisioner/provider execution required?**: only probe code, not the
  provider.
- **Remaining UNKNOWN**: whether the chosen container runtime honours the spec
  exactly; whether provider-internal secondary mounts exist (per-provider,
  UNKNOWN — see C/D).

### A.2 M2 — network egress denial

- **Threat / failure mode**: exfiltration or remote-instruction fetch via DNS
  tunnel, proxy env var, abstract-socket side channel, or metadata endpoint.
- **Required invariant**: `RESOURCE SCOPE network:"none"`; run in a network
  namespace with zero interfaces and no DNS; fail closed if the runtime cannot
  guarantee it. seccomp additionally denies `socket`/`connect`/`sendto`.
- **Enforcement layer**: container runtime + adapter + tests.
- **Observable acceptance criterion**: from inside the C1 sandbox, TCP/UDP
  connect to any address (incl. metadata `169.254.169.254`), DNS resolution, and
  abstract-socket connect all fail; env dump shows no `*_PROXY`, no credentials,
  no API keys; `/proc/net/*` shows no non-loopback interface.
- **Evidence required before Phase 2C**: sandbox network config; env allow-list
  proof; egress-probe results; confirmation no credentials are injected.
- **Statically verifiable?**: config **yes**; actual egress denial **no**.
- **Live provider execution required?**: no (probe code only).
- **Remaining UNKNOWN**: whether the runtime's default DNS path is fully
  removed vs. merely unreachable — must be probe-confirmed.

### A.3 M3 — generic-execution prohibition

- **Threat / failure mode**: `C1 static_file_manifest` internally reaches
  `sh -c`, tmux, an arbitrary subprocess, a generic command dispatcher, or
  dynamic tool dispatch — i.e. it is a generic-execution primitive wearing a
  file-op name.
- **Required invariant**: capability classes are defined by **enforced syscall
  profiles**, not provider intent. The C1 profile allows read-only FS syscalls
  (`openat` `O_RDONLY`, `read`, `getdents64`, `stat`/`fstatat`, `close`,
  `lseek`, `mmap`) plus bootstrap and `clone` restricted to
  `CLONE_THREAD|CLONE_VM|CLONE_FS|CLONE_SIGHAND`; it **denies** `execve`/
  `execveat`, `fork`, namespace `clone`, `socket*`, `ptrace`, `mount*`,
  `keyctl`, `bpf`, `userfaultfd`, `perf_event_open`. Image contains no shell,
  no tmux, no package manager.
- **Enforcement layer**: kernel seccomp (layer 1) + image minimality (layer 2) +
  static call-graph proof from C1 entry points (layer 3) + syscall-trace
  conformance gate.
- **Observable acceptance criterion**: C1 run under the profile produces a
  syscall trace containing **no** occurrence of the denied set; a deliberate
  generic-exec attempt (`execve`) is killed; the image manifest lists no
  shell/tmux.
- **Evidence required before Phase 2C**: seccomp policy artifact; image
  manifest; enumerated/bounded dynamic-dispatch surfaces at C1 entry points.
- **Statically verifiable?**: syscall policy + image manifest **yes**;
  conformance **no**.
- **Live provider execution required?**: **yes** for syscall-trace conformance
  of the real provider → authorization catch-22 (see §E).
- **Remaining UNKNOWN**: whether either pinned provider exposes a C1 path that
  does not depend on a generic execution primitive (§C/§D: both are **NO** at
  this pin).

### A.4 M4 — provider authority-field rejection

- **Threat / failure mode**: a provider-supplied epistemic/authority field
  (`verifyGate`, `verdict`, `severity`, `confidence`, `authorized`,
  `validation`) is consumed as a RAPHAEL finding/decision, transferring
  authority to the provider.
- **Required invariant**: `ProviderResult` is a **closed allow-list** schema.
  Every non-allow-listed field is **REJECTED fail-closed**, never silently
  stripped (silent stripping is spoofable through allow-listed free text).
- **Enforcement layer**: adapter + RAPHAEL closed parser (defence in depth) +
  tests.
- **Observable acceptance criterion**: a `ProviderResult` bearing any
  deny-listed key is rejected with a typed error; free-text/diagnostic fields
  are inert — never rendered/parsed/regexed/model-processed into status,
  verdict, or severity.
- **Evidence required before Phase 2C**: closed schema; deny-by-category list;
  name-normalization (case/separators/Unicode NFKC homoglyph) tests; nested
  artifact fields governed by their own closed schema; duplicate-JSON-key
  rejection at parser level.
- **Statically verifiable?**: **yes.**
- **Live provider execution required?**: no.
- **Remaining UNKNOWN**: completeness of the deny-list against real provider
  payloads (only reachable once a provider returns a result — but the
  *rejection* mechanism is statically verifiable).

### A.5 M5 — cancellation acknowledgement

- **Threat / failure mode**: `cancellation.acknowledged:true` is set because the
  provider *said* it accepted cancellation, while the process is still running.
- **Required invariant**: `cancellation.acknowledged` may become `true **only**
  following externally observed termination/teardown` (process reaped / container
  gone / PID gone), never on provider testimony.
- **Enforcement layer**: adapter + runtime + tests.
- **Observable acceptance criterion**: after a cancel request, the runtime polls
  an **independent** liveness source (OS process table / runtime sandbox state)
  until termination is observed, or times out to `timeout`/`failed`; a provider
  claiming acceptance while the process lives yields acknowledged=`false`.
- **Evidence required before Phase 2C**: teardown semantics doc; liveness source
  named; a negative test (phantom ack) that stays unacknowledged.
- **Statically verifiable?**: semantics **yes**; live teardown **no**.
- **Live provider execution required?**: only to prove teardown on the real
  runtime.
- **Remaining UNKNOWN**: the runtime's teardown guarantees on hard-kill.

### A.6 M6 — provenance fail-closed

- **Threat / failure mode**: missing/malformed/mismatched/duplicated/late/
  conflicting provenance lets a provider result be attributed to the wrong
  run/action/evidence, or lets a provider-supplied ID masquerade as RAPHAEL's.
- **Required invariant**: provenance enters from RAPHAEL (`run_id`,
  `action_request_id`, `invocation_id`, `operation_id` assigned before invoke).
  Missing/malformed/mismatched provenance → **fail closed** (`denied`/`failure`),
  never a defaulted success. Provider-reported IDs are **never authoritative**.
- **Enforcement layer**: adapter + runtime + tests.
- **Observable acceptance criterion**: each fail mode maps to a deterministic
  non-success status; a mismatched `invocation_id` is rejected; a duplicate is
  rejected; provider-echoed IDs never overwrite RAPHAEL IDs.
- **Evidence required before Phase 2C**: provenance field table; fail-mode →
  status matrix; tests per mode.
- **Statically verifiable?**: **yes.**
- **Live provider execution required?**: no.
- **Remaining UNKNOWN**: none structural.

### A.7 M7 — output limits / truncation

- **Threat / failure mode**: an unbounded output silently truncates yet remains
  `success`, so a partial manifest is consumed as complete; or an oversized
  payload exhausts memory/disk.
- **Required invariant**: exact byte/entry/artifact limits per capability.
  Exceeding the output limit **MUST NOT remain success** → becomes
  `partial` (with `truncated:true`) or `failure`. Artifacts are REFERENCES ONLY.
- **Enforcement layer**: adapter + parser + tests.
- **Observable acceptance criterion**: a payload just under the limit is
  `success`; just over is `partial`/`failure` and never `success`; entry-count
  and per-artifact-size caps enforced; scratch writes capped via
  `RLIMIT_FSIZE` + tmpfs size.
- **Evidence required before Phase 2C**: numeric limits per capability;
  boundary tests at limit−1 / limit / limit+1.
- **Statically verifiable?**: **yes.**
- **Live provider execution required?**: no.
- **Remaining UNKNOWN**: none structural.

---

## B. STATIC PROVIDER SOURCE AUDIT (HASH-BOUND)

Providers unchanged at their pinned commits. All findings below are from
inspected source at these commits; inferred statements are marked.

### B.0 Evidence index (sha256 of audited files)

Decepticon `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06`:

| path | sha256 |
|---|---|
| `packages/decepticon/decepticon/tools/filesystem.py` | `bd16dffd7571fe66d289f8e903b5c5021e0f1ce9c55072c8a63e6d996acdd182` |
| `packages/decepticon/decepticon/middleware/filesystem.py` | `515b78386e5f1863c400f2e11323becd80275222350f44ca8ba387d72a59e46e` |
| `packages/decepticon/decepticon/sandbox_server/app.py` | `5dac0bdbcbca2e9661aef792cf7507190c087f79ee7ea10e294fde5058d09d11` |
| `packages/decepticon/decepticon/sandbox_kernel/base.py` | `9b7f685160c28c4c22787667fc5854ff34c64a053369cdf1c7c17244838bb934` |
| `packages/decepticon/decepticon/backends/http_sandbox.py` | `188871e232d7535e5420e1a7530fe7742f952075e77e8183c89dc9414f68a93e` |
| `packages/decepticon/decepticon/tools/bash/bash.py` | `fb9e585a2130b8d1b7d5b2f1ab9b865e3dda5c0b715e2b4be446f0cd56cf87d8` |

T3MP3ST `29824d5625ede419ac8cdae418c8f4c72c6270f7`:

| path | sha256 |
|---|---|
| `src/arsenal/catalog.ts` | `e599d228e1014114aae547457443ab4f64b81805cae06b7bfe42c67424afa089` |
| `src/arsenal/adapter-tools.ts` | `2831a6d150a9daeed757b4e94809a8c2abf6e7c94acd5e912e32f17e2ff9901f` |
| `src/arsenal/local-file-scope.ts` | `4ad421feaee1a59510ca16425c15b426dcc483a3f410add1486626724ab50038` |
| `src/arsenal/index.ts` | `30f95e7a506c8d97e696a821670da22092990cce69cbf7cc21ca26f9fd4aacc8` |
| `src/index.ts` | `008c66c439f508f3d60ae893e86d3d04ca40d44938c2c6fe156dff6bcc46b533` |

### B.1 Fifteen questions — Decepticon

| # | question | answer | evidence |
|---|---|---|---|
| 1 | C1 candidate directly reads FS APIs? | **NO** | `middleware/filesystem.py:62` `EngagementFilesystemBackend` only *rewrites paths* and delegates to `self._backend.ls/read/glob/grep` (`:149,:166,:222,:252`). No `open()`/`os.listdir` in this path. **VERIFIED FROM SOURCE.** |
| 2 | invokes subprocesses? | **YES** | `sandbox_kernel/base.py:249` `subprocess.run([*self._exec_prefix, "sh", "-c", command], …)`. **VERIFIED FROM SOURCE.** |
| 3 | invokes shell/bash/tmux? | **YES** | `execute()` runs `"sh", "-c"` (`base.py:250`); tmux surface `base.py:306+`, `tools/bash/bash.py:511`. **VERIFIED FROM SOURCE.** |
| 4 | invokes a generic command dispatcher? | **YES** | provider `execute()` is a generic `sh -c` dispatcher (`base.py:245-270`). **VERIFIED FROM SOURCE.** |
| 5 | dynamically dispatches arbitrary tools? | **YES (inferred from sink)** — the sandbox exposes `/execute` + tmux routes that run arbitrary commands (`sandbox_server/app.py:293-357`). **VERIFIED FROM SOURCE (the surface); INFERRED (that C1 must use it).** |
| 6 | requires the broader provider orchestrator? | **YES** for the real path: file ops need a running HTTP sandbox daemon (`http_sandbox.py:158`, `sandbox_server/app.py`). **VERIFIED FROM SOURCE.** |
| 7 | reachable through a minimal entry point? | **NO** — no FS-only entry point in the pinned source; the only FS implementation is inherited `BaseSandbox` → `execute()` (`base.py:121-126` docstring states files ops delegate to `execute()`). **VERIFIED FROM SOURCE.** |
| 8 | provider-local config controls its root? | `SANDBOX_ROOT_DIR` (default `/workspace`) at `sandbox_server/app.py:190`; engagement root via `workspace_path` / `DECEPTICON_WORKSPACE_PATH` / `DECEPTICON_ENGAGEMENT` (`tools/bash/bash.py:307-327`). **VERIFIED FROM SOURCE.** |
| 9 | can that root be overridden? | **YES** (env + per-run `configurable.workspace_path`/`sandbox_url`). **VERIFIED FROM SOURCE.** |
| 10 | symlinks resolved? | **UNKNOWN** in the pinned source — resolution would occur in the deepagents `BaseSandbox` FS implementation (third-party, not in the pin). `_normalize_engagement_workspace` is lexical only (`middleware/filesystem.py:34-59`). |
| 11 | parent traversal rejected? | **YES (lexical only)** — `middleware/filesystem.py:56` `posixpath.normpath(expected) != expected → None`; `sandbox_kernel/base.py:178`. Does **not** cover symlink/hardlink escape. **VERIFIED FROM SOURCE.** |
| 12 | `/proc`, `/sys`, device nodes, sockets reachable? | **YES (once `execute()` is the mechanism)** — `sh -c` has full OS-visible path access subject to container mounts; no in-source `chroot`/mount restriction. **INFERRED FROM SOURCE.** |
| 13 | import-time side effects requiring exec? | **NO** exec at import in the audited modules (lazy imports inside `_rebind_sandbox_per_run`, `middleware/filesystem.py:319-322`). **VERIFIED FROM SOURCE.** |
| 14 | does the candidate operation write anything? | For a *manifest* op, no write intended; but Decepticon `_offload_large_output` writes via `upload_files` and `_prune_old_scratch` runs `find … -delete` (`tools/bash/bash.py:370,419`). **VERIFIED FROM SOURCE.** |
| 15 | evidence per answer | see column 4 + §B.0 hashes. |

### B.2 Fifteen questions — T3MP3ST

| # | question | answer | evidence |
|---|---|---|---|
| 1 | C1 candidate directly reads FS APIs? | **NO** for the `file` capability — `catalog.ts:58-72` declares adapter `id:'file'`, `binary:'file'`, `execution:'safe_command'`; execution goes through `runSubprocess` (`adapter-tools.ts:652`; `arsenal/index.ts:3371-3392`). (Direct FS APIs exist only in `local-file-scope.ts:1` `realpathSync/statSync`, used by `binary.ts:75` / `r2-analyze.ts:37`, not by `file`.) **VERIFIED FROM SOURCE.** |
| 2 | invokes subprocesses? | **YES** — `execFileAsync` → `execFile` (`arsenal/index.ts:9,27,3380`). **VERIFIED FROM SOURCE.** |
| 3 | invokes shell/bash/tmux? | **NO shell for `file`** — `execFile` does not spawn a shell (`arsenal/index.ts:3371+`); but `local-agents.ts:322` uses `spawn(..., shell:true)` for unrelated agent CLIs. **VERIFIED FROM SOURCE.** |
| 4 | invokes a generic command dispatcher? | **YES** — `runSubprocess(command,args)` is a generic subprocess runner; `buildAdapterTools` mints one tool per catalog binary (`adapter-tools.ts:703-746`). **VERIFIED FROM SOURCE.** |
| 5 | dynamically dispatches arbitrary tools? | **YES (catalog-bounded)** — `adapterForBinary`/`TOOL_ADAPTERS` and minted tools dispatch any mintable adapter binary (`catalog.ts:1279-1281`; `adapter-tools.ts:575-576`). **VERIFIED FROM SOURCE.** |
| 6 | requires broader orchestrator? | **NO for a direct call** — `runSubprocess` is exported standalone, but `buildAdapterTools` needs `AdapterToolDeps` and Arsenal registration (`src/index.ts:442`). **VERIFIED FROM SOURCE.** |
| 7 | minimal entry point? | **PARTIAL** — `runSubprocess('file',[path])` is a minimal programmatic entry point (`arsenal/index.ts:3371`), but it is generic subprocess, not a bounded FS read. **VERIFIED FROM SOURCE.** |
| 8 | provider-local config controls its root? | `T3MP3ST_SOURCE_ROOT` — but **only** `approvedLocalPath` consults it (`local-file-scope.ts:5`); `file` does **not**. **VERIFIED FROM SOURCE.** |
| 9 | can that root be overridden? | **YES** — process env var, read per call, no signature/binding. **VERIFIED FROM SOURCE.** |
| 10 | symlinks resolved? | **YES in `approvedLocalPath`** (`realpathSync`, `local-file-scope.ts:8-9`); **N/A for `file`** (no such check). **VERIFIED FROM SOURCE.** |
| 11 | parent traversal rejected? | **YES in `approvedLocalPath`** (`relative()` `..` check, `:10-13`); **N/A for `file`**. **VERIFIED FROM SOURCE.** |
| 12 | `/proc`, `/sys`, device nodes, sockets reachable? | For `file`: **YES** — target path is passed straight to the binary with no root bound (`adapter-tools.ts:601-615,652`). For `approvedLocalPath` tools: realpath outside root is rejected. **VERIFIED FROM SOURCE.** |
| 13 | import-time side effects requiring exec? | **NO** — module-level `promisify(execFile)` only (`arsenal/index.ts:27`). **VERIFIED FROM SOURCE.** |
| 14 | does candidate write anything? | `file` itself is read-only; `runSubprocess` captures stdout, does not write. Report-file adapters write to a private workspace (`adapter-tools.ts:640-699`) but `file` has no report template. **VERIFIED FROM SOURCE.** |
| 15 | evidence per answer | see column 4 + §B.0 hashes. |

---

## C. DECEPTICON-SPECIFIC AUDIT

Trace: `FilesystemMiddleware` (`middleware/filesystem.py:336`) →
`EngagementFilesystemBackend._get_backend` wraps
`_rebind_sandbox_per_run(super()._get_backend(runtime))` (`:343-351`) → the
production backend is `HTTPSandbox` (`:325-332`) → `HTTPSandbox` extends
`deepagents BaseSandbox` (`backends/http_sandbox.py:158`) and implements **no**
`ls/read/glob/grep` itself (its only methods are `execute`, `upload_files`,
`download_files`, and the tmux/background surface, `:240-518`) → `BaseSandbox`
implements `ls/read/glob/grep` by calling `execute()` → `SandboxBase.execute()`
runs `subprocess.run([*exec_prefix, "sh", "-c", command])`
(`sandbox_kernel/base.py:245-270`) → `sandbox_server/app.py:293` exposes
`/execute` (generic command) and `/execute_tmux` (`:344`).

**Answer to the decisive question** — *"Can `C1 static_file_manifest` use the
pinned Decepticon source without depending on a generic execution primitive?"*

**NO — directly demonstrated by source.** The pinned source provides no
filesystem read path that is not mediated by `execute()` (`sh -c`) or the tmux
surface; `sandbox_kernel/base.py:121-126` states verbatim that file operations
"are handled by BaseSandbox, which delegates them to execute()". The HTTP daemon
exposes only generic `/execute` and tmux routes — there is no `/ls`, `/read`,
`/glob`, or `/grep` route (`sandbox_server/app.py:282-499`).

Caveat (keeps the "NO" honest): the *exact command strings* `BaseSandbox` uses
for `ls/read/glob` live in the third-party `deepagents==0.6.8` package (pinned
in `uv.lock:668-681`), not in the Decepticon pin. That the FS ops are
shell-mediated is established by Decepticon source; the specific command text is
**UNKNOWN / NOT VERIFIED** at this pin. This does not change the classification:
a `sh -c` dependency is present regardless of the command string.

The provider was not modified or forked.

---

## D. T3MP3ST-SPECIFIC AUDIT

Trace of `file` from registration to execution:

1. Registration: `catalog.ts:58-72` — `id:'file'`, `binary:'file'`,
   `category:'core'`, `risk:'local_read'`, `execution:'safe_command'`,
   `networked:false`.
2. Minting: `buildAdapterTools` (`adapter-tools.ts:733`) → `isMintable`
   (`:575-576`) → `safe_command` qualifies → `adapterToCustomTool`
   (`:578+`) mints tool `file_tool` (`toolNameFor`, `:723`).
3. Dispatch: `src/index.ts:442` registers minted tools with Arsenal.
4. Execution: `adapterToCustomTool`'s handler (`adapter-tools.ts:591-701`) →
   `resolveTemplate` (no bespoke template for `file` → `DEFAULT_TEMPLATE`,
   `targetParam:'target'`, `build: target => [target]`, `:531-536`) →
   `runSubprocess(adapter.binary, argv, …)` (`:652`) →
   `execFileAsync('file', [path])` (`arsenal/index.ts:3380`).

Findings:

- **exact tool implementation**: external `file(1)` binary, invoked via
  `execFile`; no in-process reader. **VERIFIED FROM SOURCE.**
- **invokes subprocesses**: **YES** (`arsenal/index.ts:3380`). **VERIFIED FROM SOURCE.**
- **depends on Arsenal**: programmatically only via
  `buildAdapterTools`/`AdapterToolDeps`; the runner itself does not require
  `AgentLoop`/`MissionControl`. **VERIFIED FROM SOURCE.**
- **AgentLoop/MissionControl required**: **NO** for a direct
  `runSubprocess('file',[…])` call. **VERIFIED FROM SOURCE (exports).**
- **`T3MP3ST_SOURCE_ROOT` use**: consulted **only** by `approvedLocalPath`
  (`local-file-scope.ts:5`); **the `file` adapter does not call it**. So for
  `file`, `T3MP3ST_SOURCE_ROOT` provides **no** bound. **VERIFIED FROM SOURCE.**
- **bounded to that root**: **NO for `file`** (no `approvedLocalPath` call in
  the trace). **VERIFIED FROM SOURCE.**
- **another path/config can supersede it**: `T3MP3ST_SOURCE_ROOT` is a mutable
  process env var read per call; `file` ignores it entirely.
  **VERIFIED FROM SOURCE.**
- **minimal entry point exists**: `runSubprocess` is exported, but it is a
  generic subprocess runner — not a bounded read. **VERIFIED FROM SOURCE.**

**`C1 static_file_manifest` in T3MP3ST: NO — directly demonstrated by source.**
It is a generic subprocess (`execFile`) of an arbitrary catalog binary; it is
not a bounded, capability-scoped filesystem read. Under the strict M3 standard
(§E) it does not qualify.

No provider modification / fork.

---

## E. M3 DECISION RECORD — STRICT C1 STANDARD

**Decision (do not silently weaken).** `C1` qualifies as *non-generic-execution*
**only if** the operation does not invoke: shell, tmux, arbitrary subprocess,
generic command dispatch, or arbitrary tool dispatch.

Consequences per pinned provider:

- **Decepticon `31e1c8e`** — C1 path is `EngagementFilesystemBackend` →
  inherited `BaseSandbox` FS ops → `SandboxBase.execute()` → `sh -c`
  (`sandbox_kernel/base.py:245-270`). Shell + generic command dispatch present.
  → **`C1 NOT APPLICABLE TO THIS PROVIDER UNDER THE PINNED COMMIT`.**
- **T3MP3ST `29824d5`** — C1 path is catalog adapter `file` → `runSubprocess` →
  `execFile('file', argv)` (`adapter-tools.ts:652`, `arsenal/index.ts:3380`).
  Arbitrary subprocess present. → **`C1 NOT APPLICABLE TO THIS PROVIDER UNDER
  THE PINNED COMMIT`.**

Explicit non-action: **we do not fork either provider to make it qualify.** If
C1 cannot be served by a pinned provider under the strict standard, the options
are (a) narrow the first proof to a capability the pinned source *can* satisfy
by construction, or (b) accept that the first provider-backed proof requires an
explicitly authorized, sandboxed execution milestone in Phase 2C — which is a
scope decision for the architecture authority, not an OpenCode decision.

Remaining UNKNOWN that could change this record: only a future pin (new commit)
or a documented provider flag that routes `file`/FS ops through a non-exec
in-process reader. Neither is present at the pinned commits.

---

## F. MINIMUM SANDBOX SPEC (DESIGN ONLY)

**This is a specification. None of these controls is claimed deployed.**

| control | minimum requirement |
|---|---|
| network | zero network interfaces; network namespace with no routes; no DNS |
| DNS | resolution disabled; `/etc/resolv.conf` absent/empty |
| authorized workspace | exactly one read-only mount at the C1 root |
| scratch | bounded tmpfs (size + `RLIMIT_FSIZE`) |
| runtime FS | read-only root filesystem |
| host mounts | none; no `hostPath`; no host `/proc`, `/sys`, `/dev` |
| docker socket | absent (primary control), asserted and tested |
| namespaces | private PID / IPC / NET / UTS / mount / user as available; never shared |
| env | constructed allow-list, default empty; strip credentials, API keys, CI vars, `*_PROXY` |
| credentials | none for C1 |
| IPC | private; private `/dev/shm`; no shared mqueue |
| privileges | non-root; `CapEff=0`; `no_new_privs=1`; no SUID on rootfs |
| seccomp | default-deny allow-list matching the C1 profile (§A.3) |
| limits | bounded CPU, memory, PIDs, open files, output bytes, wall-clock |
| teardown | process-timeout kill + hard teardown; cancellation ack only on observed death (§A.5) |
| `/dev` | `null`, `zero`, `random`, `urandom` only |
| image | no shell, no tmux, no package manager, no interpreters beyond the C1 runtime |

---

## G. `ProviderResult` HARDENING DECISIONS

### G.1 M4 — closed schema / authority-field rejection

`ProviderResult` is a **closed allow-list** schema. Fields outside the allow-list
are **REJECTED fail-closed** (typed error; the result is not produced), never
silently ignored. Minimum deny-by-category (reject on presence, normalized):

- gate: `verifyGate`
- verdict: `verdict`, `conclusion`, `validated`, `verified`, `refuted`
- severity/risk: `severity`, `assertedSeverity`, `risk`, `priority`, `impact`, `cvss`
- confidence: `confidence`, `confidence_score`, `score`, `probability`, `certainty`, `trust`
- authority: `authorized`, `approved`, `approval`, `permission`, `policy`, `gate_pass`, `gatePass`
- completeness: `complete`, `COMPLETE`, `done`
- direction: `recommendation`, `recommendations`, `next_steps`, `directives`

Anti-evasion: name normalization (case, separators, Unicode NFKC homoglyphs);
nested artifact fields governed by their own closed schema; duplicate JSON keys
rejected at the parser level; closed parser inside RAPHAEL (defence in depth).
Semantic containment: all free-text/diagnostic fields are **inert** — never
rendered, parsed, regexed, or model-processed into status/verdict/severity.

### G.2 M5 — cancellation

`cancellation.acknowledged` may become `true` **only after** externally observed
termination/teardown (process reaped, PID gone, sandbox state gone). A provider
message saying "cancel accepted" is insufficient. Absent observation → the
invocation resolves to `timeout`/`failed`, `acknowledged:false`.

### G.3 M6 — provenance

Missing, malformed, mismatched, duplicated, late, or conflicting provenance
**fails closed** (→ `denied` or `failure`; never a defaulted success).
Provider-reported IDs are recorded as untrusted metadata only and never enter
`run_id`/`action_request_id`/`invocation_id`/`operation_id`/`evidence_id`.

### G.4 M7 — output limits / truncation

Exact byte / entry-count / artifact-size limits are declared per capability.
**Exceeding any limit MUST NOT remain `success`.** It becomes `partial` with
`truncated:true` (bounded) or `failure` (unbounded/over-hard-limit). `partial`
is never promoted to a complete manifest. Artifacts are **REFERENCES ONLY**:
no automatic ingestion, no execution, no semantic promotion of contents.

---

## H. PROVENANCE / ARTIFACT POLICY

Identifier ownership: `run_id`, `action_request_id`, `invocation_id`,
`operation_id`, `evidence_id`, `artifact_ref` are **assigned by RAPHAEL before
invocation** and are immutable thereafter. A provider-echoed value never
overwrites one.

Fail-mode matrix:

| mode | condition | behavior |
|---|---|---|
| missing | required id absent | fail closed → `denied`/`failure` |
| malformed | wrong type/shape/encoding | fail closed |
| mismatched | provider id ≠ bound id | fail closed |
| duplicated | same id reused within a run | fail closed |
| late | result arrives after timeout/cancel | recorded as `timeout`/`cancelled`; never success |
| conflicting | two results claim same invocation | first is authoritative; second → `denied` (conflict) |

Artifact policy: artifacts are stored as **references** with a content hash and
size. No automatic ingestion, no execution, no parsing that promotes artifact
content into status/verdict/severity. Provider-supplied free text inside an
artifact remains inert (§G.1).

---

## I. OPEN UNKNOWNS (carried forward)

1. deepagents `0.6.8` exact `BaseSandbox` FS command strings (third-party, not
   in the Decepticon pin) — **UNKNOWN / NOT VERIFIED.**
2. Whether any pinned provider exposes a non-execution C1 path behind a flag or
   config not visible in the audited files — not found; treated **UNKNOWN**.
3. Syscall-trace conformance of the *real* provider requires executing it →
   authorization catch-22; must be resolved by the architecture authority
   (authorize pre-2C sandboxed harness runs, or designate as the first gated 2C
   milestone).
4. Runtime-specific mount/teardown guarantees (probe-confirmable, not
   source-confirmable).

## J. WHAT THIS DOCUMENT IS NOT

- Not implementation. Not a Phase 2C authorization. Not a claim that M1–M7 are
  closed. Not provider execution. Not a substitute for the GLM adversarial
  review, which remains the authority on closure sufficiency.
