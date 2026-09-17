# Phase 2B-δ.1 — Exhaustive Provider Capability Enumeration Audit

**STATUS: STATIC / READ-ONLY AUDIT. NO PROVIDER EXECUTED. NO IMPLEMENTATION.
PHASE 2C: NOT AUTHORIZED.**

Labels: **VERIFIED FROM SOURCE** (file + symbol cited), **INFERRED**,
**UNKNOWN / NOT VERIFIED**. Every sha256 below was computed at the pinned
revision noted. No provider tool, sandbox operation, or binary was run.

Baseline:

| item | value |
|---|---|
| RAPHAEL HEAD at audit start | `98c9a078f5a3635a986882d061d78f97b35f310c` |
| Decepticon pin | `PurpleAILAB/Decepticon@31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` (clean) |
| T3MP3ST pin | `elder-plinius/T3MP3ST@29824d5625ede419ac8cdae418c8f4c72c6270f7` (clean) |
| pinned dependency | `deepagents==0.6.8` (sdist sha256 `70cdd4da920cc420a8a0f729792ec559688bbbff39f7ab1508110cce9f901c06`, per `uv.lock:668-681`) |

---

## 1. Audit Objective

Determine, by hash-bound read-only source inspection, whether **any genuine
Class-A (execution-free) capability exists in either pinned provider**, and
thereby settle the provider-wide negative that the prior audit only established
for `C1 static_file_manifest`. No convenience-driven conclusion is permitted.

## 2. Authority / Class-A Definition (locked, not weakened)

A capability is **Class A** iff its execution invokes **none** of:

- shell
- tmux
- arbitrary subprocess
- generic command dispatch
- arbitrary tool dispatch

**Class B** = sandboxed pinned-binary execution with full isolation and
RAPHAEL-validated arguments. Class B is a separate threat model and **must never
be represented as Class A / C1**.

Additional recorded attributes (not Class-A disqualifiers per the locked
definition, but material to RAPHAEL scope): network dependency, filesystem
dependency, scope mechanism, provider-authority implications.

A **pure internal helper is not automatically a Class-A capability** — it must
be reachable as a provider-facing/invocable operation.

## 3. Pinned Revisions & Hash-Bound Evidence Index

Decepticon `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` (paths under
`packages/decepticon/decepticon/`):

| path | sha256 |
|---|---|
| `tools/__init__.py` | `b28e8ea73b0b8d65b30c0cd62b2272afd2c8b581b1fa2f8083bf517ed4abcff0` |
| `mcp_server/tools_interactive.py` | `98c83f5b4dd5f2f4847a0d58357c8b6e043e07927717d8ccff3402e4bbebca82` |
| `mcp_server/tools_lifecycle.py` | `84f616cab09e51bf1305e99dfd1388fbbb05977925c36763d0904dfbff465a9a` |
| `capabilities/evidence.py` | `fce20302eb156dca2093f4dcc309483a214867e5ac031786d306508a3ce63edc` |
| `capabilities/contracts.py` | `564f7a59faf0349ba207ce8aa57334df0705fac0709e0cf584beca7c395f06fa` |
| `capabilities/scorecards.py` | `48b1fc0cde25d74cdf9935b1afee241d0a1c4071e850ac96118fb401d132c716` |

Phase 2B-δ audited files (unchanged, restated): `middleware/filesystem.py`
`515b7838…`, `sandbox_kernel/base.py` `9b7f6851…`, `backends/http_sandbox.py`
`188871e2…`, `sandbox_server/app.py` `5dac0bdb…`, `tools/bash/bash.py`
`fb9e585a…`, `tools/filesystem.py` `bd16dffd…`.

`deepagents==0.6.8` (extracted sdist; read-only, not installed into any env):

| path | sha256 |
|---|---|
| `deepagents/backends/sandbox.py` | `024e11e94dc1ccaf15f8d481ce77c174bddeb7cfa6a9710b3a24978be363903e` |
| `deepagents/backends/local_shell.py` | `4f587258c0bb888bbee410eabb02321baa8af29ec378db922d4f0cb36ac475bc` |
| `deepagents/backends/filesystem.py` | `f8163516dbaa5b9951666dd4fa536467224fec05263e5c617261f2d15d647af7` |
| `deepagents/backends/state.py` | `48f4a195f90186dabbc527c5e329ed3a7d110b02e5534f64cfdf45e0d7ba3bca` |
| `deepagents/backends/store.py` | `370e7f2da29fffe33c6d27196cc1d8ad881952566e6cbcfe706bebf9de21c958` |
| `deepagents/backends/composite.py` | `894bf500772c92db64f1683eea886740ba6e2abeae5db1f7044de691717f2494` |
| `deepagents/backends/context_hub.py` | `4558a3e103474bd0ef7b20d8b34ca2a8c2bbf58bbb41d7fa3cd6e144df6f7f59` |
| `deepagents/middleware/filesystem.py` | `6decf8b07bab3849c27e37eafe1bce2c99e024fae989cdd6643045aa7637436a` |

T3MP3ST `29824d5625ede419ac8cdae418c8f4c72c6270f7` (paths under `src/`):

| path | sha256 |
|---|---|
| `arsenal/catalog.ts` | `e599d228e1014114aae547457443ab4f64b81805cae06b7bfe42c67424afa089` |
| `arsenal/adapter-tools.ts` | `2831a6d150a9daeed757b4e94809a8c2abf6e7c94acd5e912e32f17e2ff9901f` |
| `arsenal/index.ts` | `30f95e7a506c8d97e696a821670da22092990cce69cbf7cc21ca26f9fd4aacc8` |
| `arsenal/binary.ts` | `b48a94f80527d23a1191218f7146464ea4aa3f746e141eda3892f54c6a02dfd2` |
| `arsenal/local-file-scope.ts` | `4ad421feaee1a59510ca16425c15b426dcc483a3f410add1486626724ab50038` |
| `arsenal/js-analyze.ts` | `6574d26dcfc91f199d4e1603d37c8b09643198c2d59f59ffcdc54ef771a4b354` |
| `arsenal/r2-analyze.ts` | `3b252c102d82ba2056adc66e1f13aa9d8f6b6074e7bce449ec9e42807bdafbb1` |
| `arsenal/social-osint.ts` | `516d406e071013f8287da1b41c7721244bcfcef7aa2fcae9ace50ad91dace126` |
| `arsenal/parsers.ts` | `9635095445920a4a32fda12c553c8dab19ba41f3a917b70df3212064f8f29aea` |

## 4. Decepticon Enumeration

### 4.1 Provider-facing surfaces (the only externally-invocable operations)

**S1 — Sandbox HTTP daemon** (`sandbox_server/app.py`, `5dac0bdb…`).
Routes: `/healthz`, `/execute`, `/upload_files`, `/download_files`,
`/execute_tmux`, `/start_background`, `/poll_completion`, `/kill_session`,
`/read_session_log_diff`, `/reset_session_log_offset`, `/provision_egress`,
`/session_log_path` (`:282-499`).

- `/execute` → `DaemonSandbox.execute` → `subprocess.run([... , "sh", "-c", cmd])` (`sandbox_kernel/base.py:245-270`). **Shell + generic command dispatch.**
- `/execute_tmux` → tmux session execution (`base.py:306`). **tmux + shell.**
- `/upload_files` / `/download_files` → `LocalSandbox` pathlib / `docker cp` (`base.py:11-13`, `daemon.py`). **Filesystem, no shell — but a file transfer primitive, not an analysis capability.**
- `/provision_egress` → `nft` ruleset (`sandbox_server/app.py:461-486`). **External binary + network control.**
- There is **no** `/ls`, `/read`, `/glob`, `/grep` route. **VERIFIED FROM SOURCE.**

**S2 — MCP server** (`mcp_server/tools_lifecycle.py`, `mcp_server/tools_interactive.py`).
Registered tools (`tools_*`:35,45,79,104,119 and `:39,48,62,82,93`):
`decepticon_list_graphs`, `decepticon_start_engagement`,
`decepticon_engagement_status`, `decepticon_engagement_findings`,
`decepticon_cancel_engagement`, `decepticon_list_engagements`,
`decepticon_send_message`, `decepticon_transcript`,
`decepticon_engagement_state`, `decepticon_watch`.

Every one is **control-plane or orchestration**: start/list/steer/cancel a
LangGraph engagement or read its persisted state. `start_engagement` launches the
full agent (which executes tooling); `engagement_findings` reads
`<workspace>/graph.json` from disk (`tools_lifecycle.py:95`). None is a bounded,
deterministic, execution-free capability. **VERIFIED FROM SOURCE.**

**S3 — Agent tool surface** (`tools/__init__.py`). Exported groups:
`BASH_TOOLS, AD_TOOLS, CLOUD_TOOLS, CONTRACT_TOOLS, DEFENSE_TOOLS,
EVIDENCE_TOOLS, PATCH_TOOLS, REFERENCES_TOOLS, REPORTING_TOOLS, RESEARCH_TOOLS,
REVERSING_TOOLS, SCANNER_TOOLS, WEB_TOOLS` (`:1-39`). These are LangChain tools
handed to an LLM **inside** the agent; their network/execution work is performed
by the bash tool (`tools/bash/bash.py`, `fb9e585a…`) and the sandbox, i.e.
group `S1`. They are **not** provider-facing capabilities over S1/S2.

**S4 — In-process pure helpers (NOT provider-facing).**

- `capabilities/evidence.py` (`fce20302…`) — `validate_evidence()` pure regex
  comparison; `validate_evidence_files()` reads two workspace-bounded files with
  `Path.read_text` (`:94-137`). **Execution-free; internal helper.** Used by the
  agent's verification step, not exposed via S1/S2.
- `capabilities/contracts.py` (`564f7a59…`) — pydantic contract validation +
  `SKILL.md` file reads (`:101-130`). **Execution-free; internal helper.**
- `capabilities/scorecards.py` (`48b1fc0c…`) — scorecard metadata.

**S5 — Other subsystems (not exhaustively read → UNKNOWN).**
`sandbox_web/*` (`executor.py`, `transport.py`, `fetch_chain.py`, …),
`tools/mcp/client.py`, `tools/ops/*`, `middleware/kg_internal/*`,
`skillogy/*` (Neo4j), `telemetry/*`, `cli/*`, `runtime/*`. These are a web-recon
subsystem, knowledge-graph middleware, skill graph, telemetry, and CLI. Their
individual handlers were not read line-by-line. **UNKNOWN.**

### 4.2 Decepticon candidate table

| capability | source | entry symbol | execution mechanism | shell | tmux | subprocess | generic dispatch | network | fs | scope | Class-A | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sandbox.generic_execute | `sandbox_server/app.py:293` | `execute` | `sh -c` | yes | no | yes | yes | no | yes | engagement root | **NO** | `base.py:249` |
| sandbox.execute_tmux | `app.py:344` | `execute_tmux` | tmux | yes | yes | yes | yes | no | yes | engagement root | **NO** | `base.py:306` |
| sandbox.upload/download | `app.py:307,320` | `upload_files` | pathlib/cp | no | no | no | no | no | yes | engagement root | not a capability (transfer) | `base.py:11-13` |
| sandbox.provision_egress | `app.py:461` | `provision_egress` | `nft` | yes | no | yes | no | yes | no | policy | **NO** | `app.py:475-486` |
| mcp.start_engagement | `tools_lifecycle.py:45` | `decepticon_start_engagement` | HTTP → LangGraph run | indirect | indirect | indirect | indirect | yes | yes | engagement label | **NO** | `:71-77` |
| mcp.engagement_findings | `tools_lifecycle.py:104` | `decepticon_engagement_findings` | read `graph.json` in-proc | no | no | no | no | no | yes | workspace | helper-like, not bounded capability | `:114-117` |
| mcp.list/status/transcript/… | `tools_*.py` | — | control plane | no | no | no | no | yes (server) | no | — | **NO** | `:40-123` |
| `capabilities.validate_evidence` | `evidence.py:46` | pure | in-process | no | no | no | no | no | no | n/a | **NO (helper, not exposed)** | `:46-91` |
| `capabilities.validate_evidence_files` | `evidence.py:107` | in-process fs read | no | no | no | no | no | yes | workspace | **NO (helper, not exposed)** | `:107-137` |
| `capabilities.contracts` | `contracts.py:101` | in-process | no | no | no | no | no | yes (SKILL.md) | skills root | **NO (helper, not exposed)** | `:101-130` |

**Decepticon Class-A candidates: none exposed.**
**Decepticon Class-B candidates: sandbox.generic_execute, sandbox.execute_tmux,
sandbox.provision_egress (all execution primitives, not capabilities).**
**UNKNOWN candidates: §4.1 S5 subsystems.**

## 5. `deepagents==0.6.8` Audit (resolves the Phase 2B-δ UNKNOWN)

Source: extracted sdist, sha256 verified against `uv.lock:679`.

**`BaseSandbox` (`backends/sandbox.py`, `024e11e9…`) — the class Decepticon uses
via `HTTPSandbox` — implements every FS helper by shelling out through
`execute()`:**

- `ls` → `python3 -c "… os.scandir …"` via `self.execute(cmd)` (`:435-479`).
- `read` → `_READ_COMMAND_TEMPLATE` = `python3 -c "…"` via `execute()` (`:481-543`).
- `glob` → `_GLOB_COMMAND_TEMPLATE` = `python3 -c "… glob.glob …"` via `execute()` (`:832-869`).
- `grep` → `grep -rHnFZ … || true` via `execute()` (`:759-830`) — **literal shell `grep`.**
- `write` → `_WRITE_CHECK_TEMPLATE` (`python3`) + `upload_files` (`:545-597`).
- `edit` → `python3 -c "…"` via `execute()` (`:599-757`).

The class docstring (verbatim, `:404-410`): *"`BaseSandbox` does not reduce or
partition the trust boundary of `execute()`. Its helper methods are convenience
wrappers built on top of the subclass-provided command-execution primitive…"*

→ The Phase 2B-δ "UNKNOWN (exact command construction lives in third-party
deepagents)" is now **RESOLVED**: FS operations are shell-command-derived, at the
pinned dependency revision. This **confirms** (does not change) the Decepticon
`C1` disqualification.

**Other deepagents backends:**

- `FilesystemBackend` (`filesystem.py`, `f8163516…`) — in-process FS, but `grep`
  shells to ripgrep via `subprocess.run` (`:60,630`) with a Python fallback.
- `LocalShellBackend` (`local_shell.py`, `4f587258…`) — `subprocess.run` on the
  host (`:307`). (Not used by Decepticon.)
- `StateBackend` (`state.py`, `48f4a195…`), `StoreBackend` (`store.py`,
  `370e7f2d…`), `ContextHubBackend` (`context_hub.py`, `4558a3e1…`) — in-process,
  no subprocess.
- `CompositeBackend` (`composite.py`, `894bf500…`) — routing.
- `LangSmithSandbox` (`langsmith.py`) — extends `BaseSandbox` → execution-derived.

**None of these in-process backends is exposed by Decepticon's provider surfaces
(S1/S2).** Decepticon's `_rebind_sandbox_per_run` selects `HTTPSandbox`
(`middleware/filesystem.py:325-332`), i.e. the execution-derived path.

## 6. Decepticon Execution Paths (consolidated)

```
FilesystemMiddleware (Decepticon)
  → EngagementFilesystemBackend (path rewrite)
    → deepagents BaseSandbox.ls/read/glob/grep/edit
      → HTTPSandbox.execute()  → HTTP POST /execute
        → DaemonSandbox.execute() → subprocess.run([..., "sh", "-c", cmd])
```

Any filesystem data returned by Decepticon necessarily transits a `sh -c`
primitive; the daemon exposes no FS RPC. **VERIFIED FROM SOURCE (+ pinned
dependency).**

## 7. T3MP3ST Catalog Enumeration

`catalog.ts` (`e599d228…`) declares **75** adapters (`^    id: '` count = 75).
Execution-mode distribution: **35 `safe_command`, 35 `receipt_required`,
4 `catalog_only`, 1 `import_only`.**

- **Mintable (→ callable tool, `isMintable`): 70** — the 35 safe_command + 35
  receipt_required.
- **Non-mintable / inert metadata: 5** — `pacu`, `frida`, `metasploit` (all
  `catalog_only`), `hydra` (`catalog_only`), `bloodhound` (`import_only`).
  `buildAdapterTools` drops these (`adapter-tools.ts:733-746`).

Every mintable adapter executes through `runSubprocess(adapter.binary, argv)`
(`adapter-tools.ts:652`) — **Class-B at best, never Class-A.** Full per-id
execution modes are enumerated in §7.1.

### 7.1 Catalog id → execution mode (75)

safe_command (35): `file, semgrep, gitleaks, trufflehog, trivy, syft, grype,
osv-scanner, checkov, slither, mythril, echidna, foundry-forge, solhint, openssl,
radamsa, afl-fuzz, radare2, ghidra, objdump, checksec, strings, readelf, apktool,
jadx, apkleaks, mobsfscan, class-dump, exiftool, binwalk, yara, wafw00f, dnsx,
testssl, waybackurls`.

receipt_required (35): `curl, dig, host, whois, nmap, subfinder, httpx, naabu,
katana, nuclei, ffuf, gobuster, arjun, feroxbuster, nikto, wpscan, dalfox, sqlmap,
prowler, scoutsuite, cloudfox, pmapper, aws-cli, az-cli, gcloud-cli, garak,
promptfoo, foundry-cast, john, hashcat, gdb, objection, drozer, whatweb, amass`.

catalog_only (4): `pacu, frida, metasploit, hydra`; import_only (1): `bloodhound`.

## 8. Template Enumeration

`ARG_TEMPLATES` (`adapter-tools.ts:180-529`) defines **43** bespoke templates:
`garak, nmap, nuclei, ffuf, feroxbuster, sqlmap, arjun, gobuster, nikto, wpscan,
httpx, naabu, katana, subfinder, dalfox, dig, host, whois, curl, semgrep,
gitleaks, trufflehog, trivy, syft, grype, checkov, objdump, readelf, checksec, r2,
exiftool, myth, apkleaks, slither, mobsfscan, apktool, hashcat, yara, whatweb,
wafw00f, amass, dnsx, waybackurls`.

`resolveTemplate` (`:541-543`): `ARG_TEMPLATES[binary] ?? ARG_TEMPLATES[id] ??
DEFAULT_TEMPLATE`. `DEFAULT_TEMPLATE` (`:531-536`) = `build: (target) => [target]`.

**Every template branch ends at `runSubprocess(adapter.binary, argv)` (`:652`).**
`hasArgTemplate` (`:551`) only distinguishes bespoke vs positional; it does **not**
introduce an in-process path. `file` has **no** bespoke template → DEFAULT →
`execFile('file', [path])`. **VERIFIED FROM SOURCE.**

## 9. `isMintable` / `buildAdapterTools` Analysis

- `isMintable` (`adapter-tools.ts:575-576`): `execution === 'safe_command' ||
  'receipt_required'` → 70 mintable.
- `adapterToCustomTool` (`:578-720`) → handler (`:591-701`): availability check →
  `resolveTarget` → option-looking-target reject (`:610`) → in-handler
  `deps.scopeOk` gate (`:618`) → build argv (`:651`) → `deps.runSubprocess`
  (`:652`). **No branch executes in-process.**
- `buildAdapterTools` (`:733-746`): drops non-mintable, de-dupes against
  `alreadyRegistered` (hand-written `EXTERNAL_TOOLS` win).
- Registration: `src/index.ts:397` `registerMany(BUILTIN_TOOLS)`,
  `:398` `registerMany(EXTERNAL_TOOLS)`, `:442`
  `registerMany(buildAdapterTools(TOOL_ADAPTERS, …))`, `:443`
  `registerMany(buildPostExTools(deps))`.

**Conclusion:** the *catalog → adapter* path is 100% subprocess. The only
in-process tools are `BUILTIN_TOOLS` (see §12).

## 10. `runSubprocess` Map

Definition: `arsenal/index.ts:3371-3392` → `execFileAsync(command, args, {timeout,
maxBuffer: 1MB})` (`execFile` = no shell; `arsenal/index.ts:9,27`).

Call sites (non-test):

| caller | executable | argv source | env/cwd/stdio | result path |
|---|---|---|---|---|
| `adapter-tools.ts:652` | `adapter.binary` (any catalog binary) | `template.build(target, params)` | inherited (execFile default) | `{stdout,stderr,exitCode}` → parse (`:670`) |
| `index.ts:3448` (`nmap_scan`) | `nmap` | sanitized flags + target (`:3441-3446`) | default | parse |
| `index.ts:3486` (`nuclei_scan`) | `nuclei` | args | default | parse |
| `index.ts:3530` (`ffuf_fuzz`) | `ffuf` | args | default | parse |
| `index.ts:3611` (`curl_request`) | `curl` | args (forced `--data-raw`, `@`/`<` reject) | default | parse |
| `post-ex.ts:123` (`metasploit_module`) | `msfconsole` | `['-q','-x',commands]` | default | parse |
| `post-ex.ts:194` (`hydra_bruteforce`) | `hydra` | argv | default | parse |

Other subprocess mechanisms in the repo (non-test): `src/mcp-server.ts:17`
(`execFile`), `src/agent/local-agents.ts:15` (`execFile/execFileSync/spawn`,
incl. `shell: true` for some agent CLIs at `:322`), `src/arsenal/r2-analyze.ts:13`
(`execFile('r2', …)`), `src/cli.ts:192,619` (`execSync` for `npx tsx setup`),
`src/llm/index.ts:17` (`spawn` for local LLM CLIs), `src/server.ts:14`
(`execFile/spawn`). **VERIFIED FROM SOURCE.**

## 11. `approvedLocalPath` Call-Site Map

Definition `local-file-scope.ts:4-22`: reads `T3MP3ST_SOURCE_ROOT`; `realpathSync`
on root + candidate; `relative()` `..` reject (`:11-13`); requires regular file
(or dir if `allowDirectory`); fail-closed on any error.

Call sites (non-test) — **only two**:

| caller | capability | validated path | reaches operation? | bypass? |
|---|---|---|---|---|
| `binary.ts:75` | `binary_sink_scan` | requested path, `allowDirectory=true` | **yes** — `filePath = approved.path` (`:77`) used for `statSync/readdirSync/readFileSync` | none found (realpath + relative guard) |
| `r2-analyze.ts:37` | `r2_analyze` | requested path (`allowDirectory=false`) | **yes** — passed to `execFile('r2', [cmd, path])` | none found |

**`file` adapter status: `approvedLocalPath` is NOT called on the `file` path
(confirmed: no import in `catalog.ts`/`adapter-tools.ts` for it), so the `file`
capability is not root-bounded — it is an unvalidated-argument subprocess.**
`r2_analyze` is root-bounded but still a subprocess (**Class B**).
`binary_sink_scan` is root-bounded and **execution-free** (§12).

## 12. Non-Subprocess Candidate Search

Search results (non-test, `from 'fs'`/`node:fs` / pure modules):

- **`binary.ts` (`binary_sink_scan`)** — `readFileSync`/`statSync`/`readdirSync`
  (`:79-127`), pure string extraction + regex rulesets; **no** `subprocess`,
  `execFile`, `spawn`. Root-bounded by `approvedLocalPath` (`:75`). Bounded 10 MB
  (`:47,123`). Registered in `BUILTIN_TOOLS` (`index.ts:606`). → **Class-A
  candidate.**
- **`js-analyze.ts` (`js_analyze`)** — fetches a URL (`:53`) then analyzes
  in-process. Network-dependent → not Class A (network), and requires a URL.
- **`recon/code-ingest.ts`** — `readdirSync/readFileSync` in-process source
  ingest; if exposed as a tool it would be an execution-free static-analysis
  candidate — **exposure UNKNOWN** (not confirmed as a registered tool).
- **Pure transforms in `BUILTIN_TOOLS`**: `base64_decode`, `jwt_decode`,
  `url_encode`, `cidr_expand` (`index.ts:3272`), and `email_format`
  (`social-osint.ts:155`) — pure computation, no fs/network/subprocess.
  Class-A by the locked definition, but trivial (no target evidence semantics).
- **`arsenal/parsers.ts`** — pure parse functions (internal helpers).
- **`threat-intel/vault.ts`, `reports/*`, `config/*`** — in-process JSON/config
  reads (internal).
- **`report-workspace.ts:21`** — `readFile(path)` for report read-back
  (internal to report adapters).
- **`server.ts:1194`** — `readFile(file)` (server-side ingest; **UNKNOWN**
  exposure).

`arsenal/index.ts:319-438` `Arsenal.execute` performs scope gate → approval gate →
arg validation → `tool.handler` — **no subprocess wrapper**; builtins run
in-process.

## 13. Class-A Matrix

| provider | capability | template | execution path | subprocess | shell | generic dispatch | network | fs | scope | Class-A | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T3MP3ST | `binary_sink_scan` | none (builtin) | in-process `readFileSync` + regex | **no** | no | no | no | yes (ro) | `T3MP3ST_SOURCE_ROOT` | **QUALIFIES** | `binary.ts:15,75,94,127` |
| T3MP3ST | `cidr_expand` | builtin | pure compute | no | no | no | no | no | n/a | QUALIFIES (trivial) | `index.ts:3272` |
| T3MP3ST | `base64_decode`/`jwt_decode`/`url_encode` | builtin | pure | no | no | no | no | no | n/a | QUALIFIES (trivial) | `index.ts` |
| T3MP3ST | `email_format` | builtin | pure | no | no | no | no | no | n/a | QUALIFIES (trivial) | `social-osint.ts:155` |
| T3MP3ST | `js_analyze` | builtin | fetch + parse in-process | no | no | no | **yes** | no | scope gate | no (network) | `js-analyze.ts:53` |
| T3MP3ST | all 70 catalog adapters | 43 templates + DEFAULT | `runSubprocess`→`execFile` | **yes** | no* | catalog dispatch | varies | varies | `approvedLocalPath` (2 of 70) + egress scope | **NO** | `adapter-tools.ts:652` |
| T3MP3ST | `r2_analyze` | builtin | `execFile('r2')` | **yes** | no | no | no | yes | `approvedLocalPath` | **NO** | `r2-analyze.ts:13,37` |
| T3MP3ST | `file` | DEFAULT | `execFile('file')` | **yes** | no | catalog dispatch | no | yes (unbounded arg) | **none** | **NO** | `adapter-tools.ts:531,652` |
| Decepticon | S1 sandbox ops | — | `sh -c` / tmux / nft | **yes** | **yes** | **yes** | partial | yes | engagement root | **NO** | `base.py:245-270` |
| Decepticon | S2 MCP tools | — | orchestration/HTTP | indirect | no | no | yes | yes | — | **NO** | `tools_*.py` |
| Decepticon | `validate_evidence*` | — | in-process | no | no | no | no | yes | workspace | **NO (helper, not exposed)** | `evidence.py` |

\* `execFile` does not spawn a shell — but still an arbitrary subprocess, which
Class A forbids.

## 14. Class-B Matrix

| provider | capability | isolation need | argument validation | threat model |
|---|---|---|---|---|
| T3MP3ST | 70 catalog adapters (nmap, nuclei, semgrep, …) | full M2 sandbox | template argv + egress scope + option-looking-target reject; `approvedLocalPath` only on `r2_analyze` | pinned-binary execution; host-wide read oracle risk where unvalidated |
| T3MP3ST | `file` | full M2 sandbox | **none** (no `approvedLocalPath`) | arbitrary-argument subprocess; host-wide file-probing oracle |
| T3MP3ST | `r2_analyze`, `msfconsole`/`hydra` (post-ex) | full M2 sandbox | `approvedLocalPath` / module+target args | intrusive; approval-gated |
| Decepticon | `sandbox.generic_execute` (`/execute`) | full M2 sandbox | none | arbitrary `sh -c` — the generic execution primitive itself |
| Decepticon | `sandbox.execute_tmux` | full M2 sandbox | none | interactive shell; detached-orphan teardown risk |

## 15. UNKNOWNs

| # | missing source | why it matters | could alter Class-A conclusion? |
|---|---|---|---|
| U1 | Decepticon `sandbox_web/*`, `tools/mcp/client.py`, `tools/ops/*`, `middleware/kg_internal/*`, `skillogy/*`, `telemetry/*`, `runtime/*` handler bodies | a hidden in-process capability could exist | **yes** (Decepticon side) |
| U2 | Decepticon `tools/*` ~400 individual tool handlers | they run inside the agent via bash, but a purely in-process tool could exist | **yes**, but the S1/S2 transport argument limits exposure |
| U3 | T3MP3ST `recon/code-ingest.ts` tool exposure | execution-free static ingest could be a strong Class-A candidate | **yes** (would strengthen T3MP3ST) |
| U4 | T3MP3ST `server.ts` ingest handlers / `kev.ts` vault source | in-process reads could be provider-exposed | possibly |
| U5 | `Arsenal.execute` tail (`index.ts:439-528`) and `describeToolAction`/`scopeViolation` internals | confirms no hidden subprocess wrapper | low |

## 16. Completeness Assessment

- **T3MP3ST catalog surface: complete.** All 75 adapters enumerated; all 43
  templates traced; the single generic runner (`runSubprocess`) fully mapped; all
  non-test subprocess mechanisms listed; `binary_sink_scan` traced line-by-line.
- **T3MP3ST builtin/pure surface: near-complete** for `BUILTIN_TOOLS` (42 entries:
  10 referenced tool objects + 32 inline). Residual UNKNOWN: U3/U4.
- **deepagents dependency: complete** for the classes Decepticon uses; FS-op
  command construction resolved.
- **Decepticon provider surfaces (S1/S2): complete.** Their execution mechanisms
  are fully determined (shell/tmux/nft/HTTP orchestration).
- **Decepticon internal surface: NOT exhaustive** (U1/U2). The negative is
  therefore **architecturally supported** (no provider-facing FS/data capability
  avoids `execute()`), but not line-by-line proven for every internal module.

## 17. Final Class-A Conclusion

**Selection: B — a Class-A candidate does not exist in Decepticon but does exist
in T3MP3ST.**

- **Decepticon**: **no Class-A capability identified.** Every provider-facing
  operation is execution-derived (`sh -c`/tmux/nft) or orchestration. Pure helpers
  exist but are not provider-facing. (Internal-surface UNKNOWN U1/U2 acknowledged.)
- **T3MP3ST**: **`binary_sink_scan` QUALIFIES as Class-A** — in-process
  `readFileSync`/`statSync`/`readdirSync`, no shell/tmux/subprocess/generic
  dispatch, root-bounded by `approvedLocalPath`, 10 MB cap, deterministic regex
  findings. Additional trivial Class-A pure transforms
  (`cidr_expand`, `base64_decode`, `jwt_decode`, `url_encode`, `email_format`).
  The **`file` catalog adapter remains Class-B/disqualified** (subprocess,
  unvalidated argument), confirming the earlier `C1` finding — but the
  **provider is not provider-wide disqualified.**

**Explicit correction note (per §12 change policy):** Phase 2B-δ §C/D stated
`C1 NOT APPLICABLE TO T3MP3ST UNDER THE PINNED COMMIT` scoped to the `C1
static_file_manifest` → `file` adapter mapping. That statement stands for `file`.
It must **not** be read provider-wide: this enumeration shows a *different*
T3MP3ST capability (`binary_sink_scan`) satisfies Class A. Likewise Phase 2B-δ's
"deepagents UNKNOWN" is now **resolved** (§5). No content of the hardening
artifact is deleted; these are additive corrections.

## 18. Architectural Recommendation

1. **Record** `C1 static_file_manifest` (as mapped to the `file` adapter) as
   NOT APPLICABLE; record Decepticon as having no Class-A capability.
2. **Do not weaken** Class A and **do not fork** either provider.
3. **Promote a new first-proof candidate from T3MP3ST Class A** —
   `binary_sink_scan` (read-only, non-networked, root-bounded, deterministic) is
   the honest first provider-backed capability. It maps more to a
   `static_file_inspect`-style proof than to `static_file_manifest`; the
   architecture authority should decide the exact capability ID.
4. **Still require** (before any provider execution) the M1–M7 boundary
   machinery and the exhaustive-audit UNKNOWNs U1–U4 to be closed.
5. **Keep the Class A / Class B split explicit**, with Class B (all catalog
   adapters, Decepticon sandbox ops) carrying its own threat model and never
   labeled Class A.
6. This audit does **not** authorize Phase 2C; it is evidence for the next
   architecture decision.

---

**Read-only audit. Nothing modified, committed, executed, or implemented.**

---

# ADDENDUM A — Phase 2B-δ.1 CORRECTION (additive; prior findings preserved)

This addendum amends the enumeration above **additively**. No prior finding is
deleted. Where an earlier statement is superseded, the original is quoted and the
correction is stated. All corrections are static, read-only, hash-bound (hashes
in §3 above; any new file is hashed inline).

## A.1 Corrections (as mandated)

**A1 — `EXTERNAL_TOOLS` enumerated (was F1).**
`src/arsenal/index.ts:3426` declares exactly **4** tools; all invoke
`runSubprocess` → `execFile` (**Class B**):

| tool | binary | argv source | timeout | risk |
|---|---|---|---|---|
| `nmap_scan` | `nmap` | `sanitizeExternalFlags` + `-p`/target (`index.ts:3441-3446`) | 120000 (`:3448`) | *(adapter nmap: active)* |
| `nuclei_scan` | `nuclei` | args (`:3486`) | 300000 | active |
| `ffuf_fuzz` | `ffuf` | args (`:3530`) | 120000 | active |
| `curl_request` | `curl` | forced `--data-raw`, `@`/`<` reject (`:3611`) | 30000 | active |

**A2 — `buildPostExTools` enumerated (was F2).**
Exactly **2** tools (`post-ex.ts`), both `runSubprocess` (**Class B**):

| tool | binary | argv | timeout | risk tier | notes |
|---|---|---|---|---|---|
| `metasploit_module` (`:135`) | `msfconsole` | `['-q','-x',<joined msf commands>]` (`:123`), metachar sanitizer `:108-112`, target-override refused `:100` | 600000 | dangerous (approval-gated) | DANGEROUS; no in-process tool |
| `hydra_bruteforce` (`:207`) | `hydra` | argv (`:194`) | 600000 | credential (approval-gated) | credential attack |

No in-process tool in `buildPostExTools` → no new Class-A candidate there.

**A3 — `BUILTIN_TOOLS` fully enumerated (was F3); 40 Class-A / 2 Class-B.**
`BUILTIN_TOOLS` (`index.ts:597`) = 10 referenced tool objects + 32 inline = **42**.
Prior §16 wording "near-complete" is **corrected to "complete"** for the builtin
registry; the residual gap is UNKNOWNs U3/U4 only.

- **Class B (2):** `r2_analyze` (`execFile('r2', …)`), `browser_probe`
  (`browser.ts:54` dynamic `import('playwright')` → launches a headless-Chromium
  **browser subprocess**).
- **Class A (40):** the remaining entries — in-process (fetch / dns / net /
  crypto / pure transforms), no shell/subprocess/generic dispatch. Mechanism
  verified per handler: `fetch`/`targetFetch` (network), `dns`/`net` (network),
  `crypto.createHash` (`hash_crack`, `:1596`), pure string/number transforms.
- **5 genuinely pure computational tools** (no network, no fs, no subprocess):
  `base64_decode`, `jwt_decode`, `url_encode`, `cidr_expand` (`:3272`),
  `email_format` (`social-osint.ts:155`).
- **Networked Class-A vs suitable non-networked Class-A:**
  - *networked* Class-A (recorded network attribute, **excluded from first-proof
    promotion** for RAPHAEL scope policy): `dns_lookup`, `port_scan`,
    `subdomain_enum`, `whois_lookup`, `http_request`, `header_analysis`,
    `dir_bruteforce`, `technology_detect`, `xss_scan`, `sqli_scan`, `ssl_scan`,
    `password_spray`, `robots_txt_fetch`, `reverse_dns`,
    `subdomain_takeover_check`, `version_detect`, `network_trace`, `csp_analysis`,
    `api_endpoint_discovery`, `http_methods_test`, `cors_check`,
    `cookie_analysis`, `open_redirect_test`, `lfi_test`, `ssti_test`,
    `clickjacking_test`, `cve_lookup`, `username_search`, `telegram_lookup`,
    `ip_info`, `idor_probe`, `js_analyze`, `kev_check`.
  - *non-networked* Class-A (candidates for first-proof): `binary_sink_scan`
    (local fs, §A.4), `hash_crack` (local crypto), and the 5 pure tools.
  - Correction to prior §13: `js_analyze` is **Class A under the locked
    definition** (network is a recorded attribute, not a disqualifier — this
    fixes errata E6/F20); it is *excluded from promotion* for network policy, not
    reclassified as non-A.

**A4 — `local-agents` reachability (was F4).**
`spawnAgent` (`local-agents.ts:321-324`) uses `shell:true` **only** when
`needsShell(resolvedBin)` = `isWin32() && /\.(cmd|bat)$/i.test(resolvedBin)`
(`:326-328`). This code path serves **local agent-CLI launching**, not Arsenal
tool execution; **no Arsenal tool dispatches into `local-agents`** (registration
in `src/index.ts:397-443` covers `BUILTIN_TOOLS`, `EXTERNAL_TOOLS`,
`buildAdapterTools`, `buildPostExTools` — none calls `local-agents`). Therefore
the `shell:true` surface is **not reachable from the Arsenal tool surface**.
**UNKNOWN preserved:** Win32 `.cmd`/`.bat` runtime robustness is unverified.

**A5 — Decepticon external-surface wording (was F5).**
Prior §4.1 header "S1/S2 — *the only externally-invocable operations*" is
**corrected**: it should read "the only **inbound generic-execution /
orchestration** daemons." The following additional surfaces are documented and
classified relative to the provider boundary:

| surface | nature | in/out of the Phase 2B out-of-process boundary |
|---|---|---|
| `sandbox_server` (`/execute`, `/execute_tmux`, files) | inbound HTTP generic execution | **in** (Class B primitive) |
| `mcp_server` (`tools_lifecycle`/`tools_interactive`) | inbound MCP orchestration/control-plane | **in** |
| `tools/ops/client.py` | outbound HTTP-over-Unix-socket client to `opscontrol` daemon (owns docker socket, ADR-0006) | **out** (tool surface, not an inbound provider capability) |
| `skillogy/server` (Neo4j-backed skill graph) | standalone server subsystem | **out** (separate service; not a RAPHAEL provider capability) |
| `telemetry-gateway` / `telemetry/*` | telemetry export | **out** (observability, not capability) |
| `cli/*` (`cli/scan.py` etc.) | operator CLI entry points | **out** (human CLI, not a provider RPC) |
| `sandbox_web/*` (`executor.py`, `transport.py`, playwright templates) | web-recon subsystem (scripts/browser) | **out** for the inbound boundary; **UNKNOWN** internally (U1 remains) |

No evidence of an inbound Decepticon capability that is execution-free.

**A6 — F6 resolved (integration mode).**
RAPHAEL's external integration mode is **LOCKED in Phase 2B to out-of-process
adapter only (HTTP/MCP); in-process provider embedding is prohibited.** Under this
premise, "provider-facing" = an inbound HTTP/MCP operation. No architecture change
is required for F6; the premise is recorded here as the basis for the Decepticon
and T3MP3ST "provider-facing" classifications.

**A7 — New critical entry (proposed first-proof candidate).**

```
capability:      binary_sink_scan
provider:        T3MP3ST
class:           CLASS-A CANDIDATE / PROPOSED FIRST-PROOF CAPABILITY
                 (NOT APPROVED — architecture authority has not approved it)
purpose:         bounded static binary/source sink + hardcoded-secret scan
                 (= filesystem content inspection)
implementation:  in-process
subprocess:      NO
shell:           NO
generic dispatch: NO
arbitrary tool dispatch: NO
filesystem:      YES (read-only)
network:         NO (verified: no fetch/http/import of net in binary.ts)
scope:           approvedLocalPath (T3MP3ST_SOURCE_ROOT)
output:          bounded text + ToolFinding[]; see §A.4
```

## A.2 `binary_sink_scan` — deep static audit

Source `src/arsenal/binary.ts` (sha256 `b48a94f8…`), `local-file-scope.ts`
(sha256 `4ad421fe…`), `index.ts` (`30f95e7a…`). **Not executed.**

| question | answer | evidence |
|---|---|---|
| exact entry symbol | `binarySinkScanTool` (name `binary_sink_scan`) | `binary.ts:65-66` |
| all callers | registered in `BUILTIN_TOOLS` (`arsenal/index.ts:606`); invoked only via `Arsenal.execute('binary_sink_scan', ctx)` → `tool.handler` | `index.ts:377-438` |
| actual Arsenal registration | `src/index.ts:397` `registerMany(BUILTIN_TOOLS)` | `src/index.ts:397` |
| exact argument schema | single param `path`: string, required | `binary.ts:69-71` |
| exact target path handling | `requestedPath = String(params.path).trim()`; `approvedLocalPath('binary_sink_scan', requestedPath, true)`; `filePath = approved.path` | `binary.ts:73-77` |
| `approvedLocalPath` usage | yes, `allowDirectory=true` | `binary.ts:75` |
| symlink behavior | entry path resolved via `realpathSync` (parent symlinks resolved, must stay in root). **Directory-mode children are NOT re-validated** → a symlink placed inside the approved root can point outside it and be read. | `local-file-scope.ts:8-11`; `binary.ts:86,94` |
| traversal behavior | `..` rejected by `relative()` guard on the entry path; **children not re-checked** | `local-file-scope.ts:10-13` |
| parent/root behavior | root = `realpathSync(resolve(T3MP3ST_SOURCE_ROOT))`; candidate must be inside | `local-file-scope.ts:5-13` |
| maximum file size | 10 MB per file (`MAX_BYTES`); directory mode ≤ 40 files, each ≤ 10 MB | `binary.ts:47,87,93,123` |
| maximum result size | bounded by ruleset × caps: 13 sink + 5 secret rules, ≤ 4 examples × 80 chars each | `binary.ts:22-45,137,144` |
| regex/pattern complexity | fixed literal/anchored patterns over extracted printable runs; linear-ish; no nested quantifiers observed | `binary.ts:22-45` |
| recursion behavior | **none** (top-level directory entries only) | `binary.ts:86` |
| directory handling | top-level `readdirSync`, file-filter, ≤ 40, aggregate per-file tallies | `binary.ts:84-121` |
| special files | directory entries filtered by `isFile()`; single-path read is `readFileSync` on the resolved path | `binary.ts:86,127` |
| device paths | only reachable if inside the approved root after realpath; would be read if so — **UNKNOWN** (no explicit device guard) | `binary.ts:127` |
| `/proc` `/sys` behavior | entry path: realpath outside root → rejected. Child-symlink escape: **UNKNOWN** (see symlink row) | `local-file-scope.ts:8-13` |
| path opened before validation? | **no** — validation precedes every read | `binary.ts:75→79,94,127` |
| helper invoking subprocess indirectly? | **no** — `binary.ts`/`local-file-scope.ts` import only `fs`/`path` | `binary.ts:15-18` |
| dynamic dispatch? | **no** — no `import()`/`eval`/`new Function` in `binary.ts` | (absence) |
| network call? | **no** | (absence) |
| embeds provider verification/authority metadata? | **YES (material)** — returns `ToolFinding` objects with provider-computed `severity` (high/medium) and `cwe[]`, plus a hardcoded "verify in a disassembler before reporting" note (`binary.ts:111-121,161-171,157`). Under M4 these provider-asserted authority fields must be **REJECTED/inert**, not consumed. | `binary.ts:111-121,157,161-171` |

**Residual UNKNOWNs:** directory-mode child re-validation; device-path guard;
`T3MP3ST_SOURCE_ROOT` provenance/default/fail-closed behavior; hardlink/TOCTOU
residuals. None of these change the Class-A execution classification; they affect
whether the scope bound is "root-bounded" in all modes.

## A.3 C1 mapping (identifier NOT chosen silently)

`binary_sink_scan` **reads file contents** and returns content-derived findings.
It is therefore semantically an **inspection** capability, not a
listing/metadata **manifest**. Proposed mapping (for the architecture authority
to ratify):

- `C1 static_file_manifest` (listing/metadata) — **NOT** what this tool does.
- Candidate new ID **`C1A static_file_inspect`** (read-only content inspection,
  bounded) — matches the tool's real behavior.

Property check against the required constraints: **read-only ✓, non-networked ✓,
bounded ✓ (10 MB/file, ≤40 files), deterministic enough ✓ (fixed ruleset),
not generic execution ✓** (in-process; no shell/subprocess/dispatch). The final
ID is the architecture authority's decision.

## A.4 What this addendum does NOT do

- Does not approve `binary_sink_scan` (it remains a CANDIDATE).
- Does not weaken Class A.
- Does not execute any provider/tool.
- Does not delete or rewrite any prior finding (E1–E13 remain recorded; A1–A7
  are corrections, and the E-items that this addendum resolves are noted inline:
  E5/F1→A1, F2→A2, F3/E10→A3, F4→A4, F5/E8→A5, F6→A6, E6/F20→A3).
- Does not authorize Phase 2C.

**Read-only correction. Nothing modified in the providers, nothing executed, no
implementation.**

---

# G0–G3 PRE-2C CLOSURE (C1A static_file_inspect)

Additive. Prior sections and corrections preserved. Static/read-only; no provider
executed. `binary_sink_scan` = **PROVISIONAL CLASS-A** per GLM's second review.

## G0 — Pin integrity (statically verified)

| item | expected | verified value | status |
|---|---|---|---|
| RAPHAEL (pre-audit) | `98c9a078f5a3635a986882d061d78f97b35f310c` | documented | OK |
| RAPHAEL (current HEAD) | advanced by additive audit commits | `3497bf746b479d7f04ae54ea8bb88a986a3c8aab` (`49b8482d` → `3497bf746` on top of `98c9a078f`) | OK |
| Decepticon | `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` | identical; `git status` clean | OK |
| T3MP3ST | `29824d5625ede419ac8cdae418c8f4c72c6270f7` | identical; `git status` clean | OK |
| deepagents | `0.6.8` | `uv.lock:668-681`, sdist sha256 `70cdd4da…` | OK |

Working tree: only untracked `docs/integration/phase-2b-delta-hardening.md`.

## G1 — Complete end-to-end static trace for `binary_sink_scan`

Two distinct provider-facing surfaces exist; **`binary_sink_scan` is not on the
`mcp-server.ts` surface.** `src/mcp-server.ts` is a separate MCP server exposing
its *own* tools (`security_recon`, …) through `runTool` → `execFileAsync`
(`mcp-server.ts:84-105`, allowlist `SAFE_COMMANDS` `:74`). The Arsenal /
`binary_sink_scan` path is reached via the **agent tool loop**:
`src/agent/index.ts:457 this.arsenal.execute(toolCall.name, …)`, driven by the
HTTP/UI server (`src/server.ts`); `server.ts` contains **no** `arsenal.execute`
call. Stage table (for the `binary_sink_scan` invocation):

| stage | symbol / file | shell | subprocess | execFile | spawn | eval / dyn import | generic dispatch | network | fs | external proc |
|---|---|---|---|---|---|---|---|---|---|---|
| HTTP/MCP entry | `src/server.ts` (HTTP/UI); separate `mcp-server.ts` does **not** expose it | no | no | no | no | no | route dispatch | yes (server) | no | no |
| tool loop | `src/agent/index.ts:457` `this.arsenal.execute(toolCall.name, …)` | no | no | no | no | no | named lookup | no | no | no |
| lookup | `Arsenal.execute` `index.ts:381` `this.tools.get(toolName)`; unknown → `ToolError` (`:382-390`) | no | no | no | no | no | fixed registry | no | no | no |
| scope gate | `scopeViolation(this.scope, context)` (`:394`) | no | no | no | no | no | no | no | no | no |
| approval gate | `isGatedRisk(tool.riskTier)` (`:408`); `binary_sink_scan` has **no** `riskTier` → gate not engaged | no | no | no | no | no | no | no | no | no |
| arg validation | `validateToolArgs` (`:425-437`) | no | no | no | no | no | no | no | no | no |
| handler | `tool.handler(context)` (`:449`) → `binary_sink_scan` | no | no | no | no | no | no | no | yes | no |
| scope/read | `approvedLocalPath` (`:75`) → `readFileSync`/`statSync`/`readdirSync` | no | no | no | no | no | no | no | yes | no |
| post-processing | `redactConfiguredSecrets(…)` (`:449`, def `:134-150`) — pure string/object redaction | no | no | no | no | no | no | no | no | no |
| record/emit | `this.executions.push`, `emit('tool:executed')` (`:439-457`) | no | no | no | no | no | no | no | no | no |
| transport serialization | agent returns `ToolResult` to caller/server | no | no | no | no | no | no | no | no | no |

`execFileAsync` **is** imported into `arsenal/index.ts` (`:27`) but is used only by
`isToolAvailable` (`:3361`) and `runSubprocess` (`:3380`) for `EXTERNAL_TOOLS` —
**not** on the `binary_sink_scan` path. `randomUUID` (`:440`) is `crypto` (pure).

**Result:** the `binary_sink_scan` invocation path is **execution-free** (no
shell/subprocess/execFile/spawn/eval/dynamic-import/generic-command-dispatch).
Residual: `src/server.ts` transport tail and `src/agent/index.ts` surrounding loop
were spot-verified (line 457) but not read line-by-line → **UNKNOWN (low)**.

## G2 — Scope closure (`T3MP3ST_SOURCE_ROOT`)

- **Where it comes from:** `process.env.T3MP3ST_SOURCE_ROOT?.trim()`, read **only**
  in `local-file-scope.ts:5` (repo-wide grep: 6 hits total; 4 in this file, 2 in a
  test).
- **Default value:** none.
- **Unset/empty behavior:** **fail-closed** error `T3MP3ST_SOURCE_ROOT must name
  the approved analysis root` (`:6`).
- **Who can set it / inheritance:** the process environment (operator/integration);
  inheritable by child processes; no provider-local config file path overrides it
  (no other reader found).
- **Provider-local override:** not found (UNKNOWN only insofar as environment
  hygiene is an integration concern).
- **RAPHAEL-supplied externally:** yes — RAPHAEL may set the env var for the
  provider process.
- **Canonicalization:** `realpathSync(resolve(configuredRoot))` and
  `realpathSync(resolve/isAbsolute(requested))` (`:8-9`).
- **Fail-closed validation:** any error → `ok:false` (`:19-21`); `..`/absolute-rel
  traversal rejected (`:11-13`); `statSync` must be a regular file (or directory
  when `allowDirectory`).
- **Symlinks/traversal:** entry-path symlinks resolved and bound to root; `..`
  rejected.
- **`binary_sink_scan` read path:** reads only `approved.path` from
  `approvedLocalPath('binary_sink_scan', requestedPath, true)` (`binary.ts:75-77`);
  no direct `T3MP3ST_SOURCE_ROOT` access in `binary.ts`.

**FIRST-PROOF POLICY RECORDED: `binary_sink_scan` MUST be used in SINGLE-FILE
mode only.** Directory mode (`allowDirectory=true`, `binary.ts:84-121`) is
**EXCLUDED FROM FIRST PROOF** because children are not re-validated through
`approvedLocalPath` → a symlink inside the root can be followed out of it.
**Residual/hardening item: directory-mode child-path symlink escape.**

## G3 — Capability identifier / dispatch decision

- **`C1 static_file_manifest` = NOT MET** by current external providers (listing/
  metadata semantics; both providers' manifest-class ops are execution-derived).
- **`C1A static_file_inspect` = proposed new closed capability ID.** Semantics:
  **bounded static content inspection**, not manifest/listing. `binary_sink_scan`
  (read-only content scan) maps to `C1A`. Final ID = architecture authority.
- **Fixed-registry named dispatch interpretation — conditionally confirmed:**

| condition (source-confirmed) | evidence |
|---|---|
| capability identity already selected/authorized | `Arsenal.execute(toolName, …)` (`index.ts:377`) with registry lookup (`:381`) |
| implementation from a fixed registry | `this.tools: Map<string,CustomTool>` populated by `registerMany` (`src/index.ts:397-443`) |
| caller cannot provide an arbitrary executable/tool name | unknown name → `ToolError` (`:382-390`); only registered names resolve |
| arguments cannot substitute another tool | args validated against the tool's own schema (`:425-437`); no tool-name arg |
| no dynamic tool resolution inside handler | `binary.ts` contains no `import()`/`eval`/registry lookup |
| (additional) RAPHAEL-side narrowing possible | `getToolDefinitions(names)` allowlist filter (`:502-523`) |

→ `Arsenal.execute("binary_sink_scan", …)` is **NOT** "arbitrary tool dispatch":
the dispatched-to entity is a fixed, bounded handler, not an execution primitive.
**UNKNOWN (low):** the agent supplies `toolCall.name`; for the first proof RAPHAEL
must pin the name via the capability allowlist.

## G4 / G5 / G6 — Pending requirements (documentation only)

**G4 (adapter contract, pending):** out-of-process HTTP/MCP only; **exactly one
allowed capability** (`binary_sink_scan`, single-file mode); adapter wall-clock
timeout; response-size cap; **M4** provider-authority inerting/rejection (note:
`binary_sink_scan` returns provider-asserted `severity`/`cwe` → must be
rejected/inert, §A.4).

**G5 (prerequisites, NOT implemented):** M1–M7 enforcement and tests remain
prerequisites. **No control is claimed implemented or deployed.**

**G6 (first-proof fixture, pending):** RAPHAEL-controlled fixture; single-file
deterministic fixture; golden expected result; bounded result; residuals
documented (directory-mode symlink escape; provider-asserted severity/cwe;
`T3MP3ST_SOURCE_ROOT` env hygiene).

**Boundary:** this closure does **not** authorize Phase 2C. It documents evidence
and pending requirements; implementation requires an explicit later authorization.

**Read-only closure audit. No provider executed, no implementation, no RAPHAEL core
change.**

---

# Final B1–B4 Pre-2C Closure Audit

Additive; prior history preserved. Static/read-only; no provider executed. Evidence
method is stated per item (full read / static trace / grep).

## B1 — Pin integrity re-verified at current HEAD

| item | documented | actual | status |
|---|---|---|---|
| RAPHAEL HEAD | `98c9a078f` → `3497bf746` | **`a68e214fef3736857c4fd792d831a05f428a89dd`** | OK |
| RAPHAEL delta `98c9a078f..HEAD` | — | **`docs/integration/phase-2b-delta-capability-enumeration.md` only** (docs/audit only) | OK |
| Decepticon | `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` | identical; `git status` clean | OK |
| T3MP3ST | `29824d5625ede419ac8cdae418c8f4c72c6270f7` | identical; `git status` clean | OK |
| deepagents | `0.6.8` | `uv.lock:668-681`, sha256 `70cdd4da…` | OK |
| working tree | — | only untracked `docs/integration/phase-2b-delta-hardening.md` | OK |

**B1 = CLOSED.** Evidence: `git rev-parse HEAD`, `git log --oneline`,
`git diff --name-only 98c9a078f..HEAD`, provider `rev-parse`/`status` (full source
read of git metadata).

## B2 — Complete invocation path (line-by-line)

Path: HTTP/UI (`src/server.ts`) → agent (`src/agent/index.ts`) →
`this.arsenal.execute(toolCall.name, …)` (`agent/index.ts:457`, full read
`:440-494`) → `Arsenal.execute` (`arsenal/index.ts:377-479`, full read) →
`this.tools.get(toolName)` (`:381`) → scope gate (`:394`) → approval gate
(`:408`) → arg validation (`:425`) → `tool.handler` (`:449`) → `binary_sink_scan`
(`binary.ts`, full read) → `redactConfiguredSecrets` (`:449`, def `:134-150`) →
`executions.push`/`emit('tool:executed')` (`:439-457`) → return to agent loop →
`agent:tool_result` (`agent/index.ts:494`).

| # | item | result | evidence |
|---|---|---|---|
| 1 | direct `Arsenal.execute` exposure | only `agent/index.ts:457` and `evidence/retest.ts:74` (non-test) | full grep `arsenal.execute` + full read of both sites |
| 2 | indirect `Arsenal.execute` exposure | none found (no aliasing `const a = arsenal; a.execute`) | full read of `agent/index.ts:440-494`; repo grep `\.execute\(` |
| 3 | runtime register/registerMany/unregister mutation | **none at request time.** `new Arsenal()` once (`src/index.ts:387`); `registerMany` only at construction (`:397,398,442,443`); custom `register` only from `config.tools` in the constructor (`:490-494`); `unregister` (`arsenal/index.ts:528`) has **no** non-test caller | full read `src/index.ts:387-495`; repo grep `register\|registerMany\|unregister` |
| 4 | module-init subprocess calls | none in the traced modules; `execFileAsync` imported for `runSubprocess`/`isToolAvailable` only (see B3) | full read of `arsenal/index.ts` imports + `agent/index.ts` |
| 5 | request-time subprocess on this path | **none** | stage trace above; `binary.ts` full read |
| 6 | execution-path middleware/hooks | `Arsenal` emits events (`tool:executed`/`tool:error`) but no execution hooks that shell out | full read `arsenal/index.ts:377-479` |
| 7 | result serialization | `redactConfiguredSecrets` (pure) → `ToolResult` returned to agent → `agent:tool_result` | full read |
| 8 | callbacks/post-processing | `setupEventForwarding` (`src/index.ts:500+`) forwards events; no subprocess | static trace |

**B2 = CLOSED** for the `binary_sink_scan` path, with one residual: `src/server.ts`
was inspected at the level of its agent-invocation seam and its `execFileAsync`
call sites (`:562`, `:4534`, `:7145`, `:7167`) were located; the full `server.ts`
(7000+ lines) was **not** read line-by-line → **UNKNOWN (low)** for an unrelated
subprocess path there. None of those sites is on the `binary_sink_scan` path.

## B3 — `isToolAvailable` call-site enumeration

Definition: `arsenal/index.ts:3356` (`execFileAsync(probe, [command])`).

Non-test call sites (grep across `src`, then read each):

| caller | when | on `binary_sink_scan` path? | invokes execFile? |
|---|---|---|---|
| `adapter-tools.ts:593` `deps.isToolAvailable(adapter.binary)` | per-invocation, **catalog adapter handlers only** | **no** | yes (probe) |
| `post-ex.ts:62` (`msfconsole`), `:158` (`hydra`) | per-invocation, **post-ex handlers only** | **no** | yes |
| `index.ts:3437/3476/3522/3563` (`nmap`/`nuclei`/`ffuf`/`curl`) | per-invocation, **EXTERNAL_TOOLS handlers only** | **no** | yes |
| `src/index.ts:240,434` | dependency injection into `buildAdapterTools`/`buildPostExTools` (not a call) | no | no |
| `server.ts:4532` | **comment only** | no | no |

`binary_sink_scan` is a builtin whose handler (`binary.ts`) does **not** call
`isToolAvailable`; registration, `getToolDefinitions`, and pre-dispatch do **not**
call it either. **B3 = CLOSED:** no `isToolAvailable` call reaches the
`binary_sink_scan` invocation. Evidence: repo-wide grep of all 29 hits + full read
of the 4 non-test caller sites + full read of `binary.ts`.

## B4 — Invocation determinism / allowlist

- `Arsenal.execute` (`index.ts:377-479`) performs **no capability allowlist
  check**; it dispatches any registered name via `this.tools.get(toolName)`
  (`:381`). The registry is fixed at construction (B2 #3), so the *arbitrariness*
  is bounded to the 118 registered tools — but **all 118 (incl. Class-B) remain
  dispatchable** if the caller names them.
- `getToolDefinitions(categories, names)` (`:502-523`) narrows only what the LLM is
  **told about** (`agent/index.ts:169`), not what `execute` will accept.
- **Option A (execution-path allowlist):** not present; requires a new seam inside
  `Arsenal.execute` (a RAPHAEL-injected allowed-names set).
- **Option B (post-hoc attestation):** **naturally supported already** — the agent
  emits `agent:tool_call {name,args,source}` (`agent/index.ts:453`) and
  `agent:tool_result` (`:494`); `Arsenal` records `ToolExecution {id, toolName,
  result}` (`:439-444`) and exposes `getExecutions()` (`:484`). A verifier can
  confirm the executed name+args match the single allowed capability and
  abort/quarantine on mismatch.

**B4 = NOT CLOSED** (by design — this task is analysis only). Determination:
**Option B is the mechanism the existing architecture already supports**; Option A
would be a new seam. Minimum Phase 2C design seam: either (A) an allowed-names
check added in `Arsenal.execute` before the handler, or (B) a RAPHAEL-side
attestation consumer over the existing `agent:tool_call`/`tool_result` +
`getExecutions()` records. An externally observable attestation (execution
log/transcript) is required; `getToolDefinitions` filtering alone is insufficient.

## B1–B4 status summary

| blocker | status | evidence method |
|---|---|---|
| B1 pin integrity | **CLOSED** | full read (git metadata) |
| B2 invocation path | **CLOSED** (residual: `server.ts` tail UNKNOWN-low) | full read + targeted static trace + grep |
| B3 `isToolAvailable` | **CLOSED** | grep (all hits) + full read of non-test callers + full read `binary.ts` |
| B4 determinism/allowlist | **NOT CLOSED** (analysis only; Option B naturally supported) | full read + static trace |

Remaining UNKNOWNs: `server.ts` full-body subprocess paths off the C1A path
(UNKNOWN-low); no others material to the first proof.

## C — C1A contract ratification proposal (NOT silently ratified)

```
capability:            C1A static_file_inspect
provider:              T3MP3ST
implementation:        binary_sink_scan (BUILTIN_TOOLS)
first-proof restrictions:
  - single-file mode ONLY (no directory mode; allowDirectory path excluded)
  - exact literal RAPHAEL fixture path pinned by the adapter; any other path rejected
  - read-only
  - network denied
  - exactly ONE capability exposed/dispatchable
  - no Class-B path touched
  - deterministic, RAPHAEL-authored fixture
preserved:             C1 static_file_manifest = NOT MET
```
The identifier, the single-file policy, and the one-capability scope require
architecture-authority ratification after a taxonomy collision check.

**Static-only. No provider executed, no implementation, no Phase 2C
authorization.**

---

# FINAL PRE-2C AUTHORIZATION PACKAGE — C1–C7

Additive; prior history preserved. Static/read-only. **PHASE 2C NOT AUTHORIZED.**
Evidence method recorded per item (FULL SOURCE READ / TARGETED SEARCH / GREP).

## C1 — Artifact integrity

This document now contains the complete final audit: Enumeration §1–18 + Addendum A
+ G0–G3 + Final B1–B4 + this C1–C7 package; the previously truncated tail is
present and no sentence is left mid-clause. Content byte count and SHA256 are
recorded in the commit report (computed post-commit on the committed blob; see the
"artifact hash" line in the handoff). Large submissions to reviewers must be split
into numbered chunks, each with a SHA256/byte count, with explicit "ALL N CHUNKS
RECEIVED" confirmation before review.

## C2 — B1 current pin verification (full source read / git metadata)

| item | expected | actual | status |
|---|---|---|---|
| RAPHAEL HEAD | — | **`b5ebddb1ad0f87bc9f6a949dff63b80589e45c5f`** | OK |
| `git status --short` | — | `?? docs/integration/phase-2b-delta-hardening.md` (untracked doc only) | OK |
| delta `98c9a078f..HEAD` | — | exactly one path: `docs/integration/phase-2b-delta-capability-enumeration.md` (docs/audit only) | OK |
| Decepticon | `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` | identical; `git status` clean | OK |
| T3MP3ST | `29824d5625ede419ac8cdae418c8f4c72c6270f7` | identical; `git status` clean | OK |
| deepagents | `0.6.8` | `uv.lock:668-681`, sdist sha256 `70cdd4da920cc420a8a0f729792ec559688bbbff39f7ab1508110cce9f901c06` | OK |

Exact commands: `git rev-parse HEAD`; `git status --short`;
`git diff --name-only 98c9a078f..HEAD`; provider `rev-parse HEAD` + `status --porcelain`.
No runtime/core implementation change in the delta; no provider execution.

## C3 — B2 complete invocation-path closure (line-by-line)

Trace (all FULL SOURCE READ unless noted):
HTTP/UI (`src/server.ts`) → agent (`src/agent/index.ts:447-494`
`executeTool` → `:457 this.arsenal.execute(toolCall.name, {target, parameters})`)
→ `Arsenal.execute` (`arsenal/index.ts:377-479`) → `this.tools.get(toolName)`
(`:381`) → scope gate `:394` → approval gate `:408` (not engaged: no riskTier) →
arg validation `:425-437` → `tool.handler` `:449` → `binary_sink_scan`
(`binary.ts`, full read) → `redactConfiguredSecrets` `:449` (def `:134-150`, pure) →
`executions.push`/`emit` `:439-457` → return → `agent:tool_result` `:453/:494`.

Process-execution sites and disposition:

| # | site | disposition | evidence |
|---|---|---|---|
| 1 | `server.ts:14` (`import execFile, spawn`); `:7091` `spawn` | **Codex exec readiness probe** (local-agent readiness), not on the Arsenal/`binary_sink_scan` path | FULL READ `server.ts:7078-7107` |
| 1b | `server.ts:562` `execFileAsync`; `:4534`; `:7145`; `:7167` | unrelated server tool/version-probe sites; none on the C1A path | TARGETED SEARCH (located) |
| 2 | `agent/index.ts` | **no** `child_process` import or process-execution site in the tool loop (FULL READ `:440-494`); process work lives in `local-agents.ts`/`llm/index.ts`, not the Arsenal dispatch | FULL READ + GREP |
| 3 | registry mutation | `new Arsenal()` once (`src/index.ts:387`); `registerMany` only at construction (`:397,398,442,443`); custom `register` only from `config.tools` in constructor (`:490-494`); `unregister` (`arsenal/index.ts:528`) no non-test caller | FULL READ `src/index.ts:387-495` + GREP |
| 4 | module-init subprocess | none in the traced modules | FULL READ imports |
| 5 | per-request subprocess on C1A path | none | stage trace |
| 6 | retry/error/timeout process activity | none on the C1A path (`executeTool` catch builds a JSON error; `Arsenal.execute` catch wraps `ToolError`) | FULL READ |
| 7 | post-processing | `redactConfiguredSecrets` (pure) | FULL READ |
| 8 | result serialization | `ToolResult` → `agent:tool_result` | FULL READ |
| 9 | callbacks/hooks | `setupEventForwarding` (`src/index.ts:500+`) forwards events; no subprocess | TARGETED SEARCH |

`binary.ts` contains no `child_process`/`spawn`/`exec`/dynamic-import (FULL READ).
Residual: `src/server.ts` (8300+ lines) was read at the agent seam and its
process-execution sites were located and dispositioned, but the entire file was not
read end-to-end → **UNKNOWN (low)** for any unrelated server process path; none is
on the C1A path.

## C4 — B3 `isToolAvailable` closure

Definition `arsenal/index.ts:3356` → `execFileAsync(probe, [command])` where
`probe = platform==='win32' ? 'where' : 'which'` (`:3360`).

| caller | source:line | phase | execFile? | binary | args | in first-proof session? | before/after `Arsenal.execute`? |
|---|---|---|---|---|---|---|---|
| catalog adapter handler | `adapter-tools.ts:593` | per-invocation of a **catalog adapter** | yes | `adapter.binary` | `[binary]` via `which/where` | **no** (not a catalog adapter) | n/a |
| post-ex metasploit | `post-ex.ts:62` | per-invocation post-ex | yes | `'msfconsole'` | `['msfconsole']` | **no** | n/a |
| post-ex hydra | `post-ex.ts:158` | per-invocation post-ex | yes | `'hydra'` | `['hydra']` | **no** | n/a |
| EXTERNAL nmap/nuclei/ffuf/curl | `arsenal/index.ts:3437/3476/3522/3563` | per-invocation EXTERNAL_TOOLS | yes | literal | `[literal]` | **no** | n/a |
| DI (not a call) | `src/index.ts:240,434` | injection into `buildAdapterTools`/`buildPostExTools` | no | — | — | no | n/a |
| comment only | `server.ts:4532` | — | no | — | — | no | n/a |

`getToolDefinitions` body (`arsenal/index.ts:502-523`) — **FULL READ**: it filters
by `names`/`categories` and calls `buildJsonSchema` only; **it does not call
`isToolAvailable`** and starts no process. `binary_sink_scan`'s handler
(`binary.ts`) does not call `isToolAvailable`.

**Result:** no `isToolAvailable` call can occur in the `binary_sink_scan`
first-proof session (it is a builtin; registration, `getToolDefinitions`, and
pre-dispatch start no process). **UNSUPPORTED CLAIM REMOVED:** we do **not** assert
"the execution log proves no other execution occurred" — `isToolAvailable` (and
bootstrap/readiness probes) do not transit `Arsenal.execute` and would not appear in
`getExecutions`; the C5 attestation scope is worded accordingly.

## C5 — B4 Option-B attestation specification (accepted; NOT implemented)

**Accepted no-fork design — Option B: post-hoc execution attestation.**

- **Exact attestation scope (verbatim):** *"Every RAPHAEL-observed tool_call and
  every provider-recorded execution was `binary_sink_scan`, and `params.path`
  exactly equals the fixture literal."*
- **FORBIDDEN stronger claim:** "no subprocess ran in the provider process."
  (Executions do not see `isToolAvailable`, bootstrap, readiness probes, LLM spawn,
  etc.)
- **Topology:** dedicated **single-session provider instance**; no shared Arsenal
  across unrelated operations.
- **Cross-check direction:** boundary event stream (`agent:tool_call`/
  `agent:tool_result`, RAPHAEL-observed) = **PRIMARY**; provider `getExecutions()`
  (`Arsenal` internal, provider-trusted) = **SECONDARY**.
- **Verify:** tool-name equality; exact args/`path` equality; invocation/session
  correlation; execution↔result correlation; result hash where applicable.
- **Divergence → ABORT PROOF + QUARANTINE RESULT** (never warn-and-continue).
- **Unknown-name attempts:** die at registry lookup (`index.ts:382-390`) and may
  never reach `executions.push`, but **are visible in the boundary event stream**;
  both records are required.
- **Accepted property (recorded):** post-hoc attestation **detects** a violation but
  **does not prevent** an out-of-contract attempt. Accepted for the first
  evidence-producing proof.
- **Explicit:** `getToolDefinitions` filtering alone is **NOT** authorization.

## C6 — Architecture ratification package (PROPOSED; requires authority sign-off)

```
Capability:  C1A static_file_inspect
Provider:    T3MP3ST
Implementation: binary_sink_scan
C1 static_file_manifest: NOT MET

FIRST-PROOF SCOPE (all mandatory):
  - exactly one capability
  - exactly one dedicated provider instance/session
  - single-file mode ONLY (directory mode EXCLUDED)
  - exact literal RAPHAEL-controlled fixture path; canonicalized (realpath) absolute path
  - T3MP3ST_SOURCE_ROOT set by RAPHAEL to the fixture root
  - read-only
  - network egress denied environmentally (not merely absent in binary.ts)
  - POSIX/Linux only
  - no Class-B path touched
  - deterministic RAPHAEL-authored fixture
  - pre/post fixture hash+stat
  - golden expected result
  - adapter wall-clock timeout
  - adapter response byte cap
  - M4 provider-metadata inerting/rejection
  - M1-M7 enforcement/tests for this narrow scope
  - Option-B attestation (C5)
```
**Provider metadata that must NEVER become RAPHAEL authority** — `severity`, `cwe`,
verify notes, verification claims, confidence, approval, gate state, authorization.
The adapter derives any RAPHAEL-native labels independently (note: `binary_sink_scan`
emits provider `severity`/`cwe`, `binary.ts:111-121,157,161-171` → M4 inerting).
**Directory mode EXCLUDED. Directory-mode child symlink escape = documented hardening
prerequisite before any future directory-mode authorization.**

## C7 — Taxonomy collision check

RAPHAEL capability taxonomy (`raphael_ibm_bob/contracts.py:27-38`) —
`Capability`: `READ="read"`, `LIST="list"`, `SEARCH="search"`, `WRITE="write"`,
`RUN_TEST="run_test"`; dispatch `capabilities.py:132-138`. **No `static_file_inspect`
or `static_file_manifest` ID exists** in the taxonomy.

**C7 = CLEAR** (no identifier collision). **Semantic overlap (flagged, not a
collision):** `C1A static_file_inspect` overlaps `Capability.READ`/`LIST`
(file-reading class). The architecture authority must decide the relationship
(new ID vs. mapping onto `READ`) before ratification. Evidence: FULL READ of
`capabilities.py`/`contracts.py` + GREP of the taxonomy.

## Residual register

| residual | disposition |
|---|---|
| Directory-mode child symlink escape | EXCLUDED by single-file contract; hardening prerequisite before any directory-mode authorization |
| Provider `severity`/`cwe`/verify-notes | M4 inert/reject — mandatory 2C item |
| `T3MP3ST_SOURCE_ROOT` overbreadth/hygiene | RAPHAEL-owned fixture root + positive/negative probes |
| Entry-path TOCTOU / hardlink / device nodes | bounded/moot under owned fixture |
| Bounded-regex DoS | fixed patterns + 10 MB cap + adapter wall-clock timeout |
| `server.ts` full-body process paths | UNKNOWN-low; none on the C1A path |
| U1/U2 (Decepticon internals); U3/U4 | affect provider-wide negatives / future candidates only |
| Win32 `.cmd`/`.bat` `shell:true` | out of scope; platform pinned POSIX |
| attestation is post-hoc (detects, not prevents) | accepted for first proof |

## STATUS

**PHASE 2C NOT AUTHORIZED.** This package documents evidence, the accepted Option-B
design, and the proposed ratification; it authorizes no execution and no
implementation. No provider executed; no runtime/core change. Awaiting architecture
authorization.

---

# B4 — OPTION-B ATTESTATION HARNESS (IMPLEMENTED, RAPHAEL-SIDE)

Additive; prior findings preserved. This section records the RAPHAEL-side
implementation of the accepted Option-B design. It is a static, read-only
validator. **NO provider executed. PHASE 2C: NOT AUTHORIZED.**

- **Module:** `raphael_ibm_bob/b4_attestation.py`
- **Tests:** `tests/test_b4_attestation.py` (14 cases; synthetic data only)
- **Cross-check direction (carried from C5):** RAPHAEL-observed boundary events
  (`agent:tool_call` / `agent:tool_result`) = **PRIMARY**; provider
  `getExecutions()` executions = **SECONDARY** (a `ToolExecution` lacks sufficient
  argument/session identity alone, so executions are never sufficient without the
  boundary event stream).
- **Dedicated instance:** one proof session bound to one dedicated provider
  instance; a foreign session or instance invalidates the proof.
- **Exact matching:** tool name must equal `binary_sink_scan`; `params.path` must
  equal the canonical absolute fixture literal.
- **Execution count:** observed executions must equal the expected count (1 for the
  first proof); extra, missing, or duplicated executions invalidate the proof.
- **Failure behaviour:** any mismatch → `ABORT` + `QUARANTINE`-the-candidate +
  structured failure. Never downgraded to a warning.
- **Post-hoc honesty:** attestation **DETECTS** an out-of-contract execution; it
  does **NOT PREVENT** one. The forbidden stronger claim
  ("`No subprocess ran in the provider process.`") is neither asserted nor implied.
- **Authority boundary:** the harness produces only proof attestation,
  execution-contract validation, and structured evidence. It never produces
  authorization, a VERIFIED/REFUTED finding, COMPLETE, or a Quality Gate decision,
  and it never executes a provider.

**Invariants enforced (named checks):** `single-capability`,
`expected-tool-is-binary-sink-scan`, `fixture-path-canonical-absolute`,
`single-proof-session`, `dedicated-instance`, `boundary-tool-call-observed`,
`tool-name-equality`, `exact-path-literal`, `tool-result-observed`,
`tool-results-ok`, `execution-observed`, `execution-count`,
`event-execution-correlation`, `no-duplicate-execution`,
`result-hash-correlation`.

**Residual (unchanged, carry-forward):** `getExecutions()` remains provider-trusted
and secondary; post-hoc attestation does not prevent attempts; result-hash
correlation applies only where the existing model supplies hashes.
**PHASE 2C NOT AUTHORIZED.**

---

# B4 CORRECTIVE CLOSURE (H1–H5) — ADDITIVE

Muse Spark 1.3 audited the B4 implementation (`c72c5125c`) and returned
**B4 = PARTIALLY CLOSED / Phase 2C = NO-GO**, identifying H1–H5. This note records
the corrective closure. Static, read-only. **NO provider executed. PHASE 2C NOT
AUTHORIZED.**

- **H1 — call↔execution cardinality + correlation (FIXED).** The first-proof
  contract now enforces *per-stream* cardinality and a **call-to-execution
  relationship**, not just a total count:
  `len(tool_calls) == len(tool_results) == len(provider_executions) == expected_calls`
  (first proof `expected_calls = 1`), and each boundary `call_id` must correlate to
  exactly one provider execution (set equality `{execution.call_id} == {call.call_id}`).
  The hole (2 calls + 2 results + 1 execution, or 2 calls + 2 executions) now
  INVALIDATES. Correlation key is the RAPHAEL-side `call_id` carried onto the
  `ProviderExecution` record by the RAPHAEL collector — **no provider field is
  fabricated**.
- **H2 — result cardinality (FIXED).** 1:1 enforced: extra result, missing result,
  extra execution, missing execution each INVALIDATE (`result-count`, `call-result-correlation`).
- **H3 — exact path (FIXED).** A provider execution (or boundary call) whose
  `params.path` is missing, `None`, empty, non-string, or an alternate
  normalisation now FAILS (`exact-path-literal`). Canonical fixture *setup* remains
  distinct from exact-literal *attestation*.
- **H4 — identifiers (FIXED).** `ProofSession` requires non-empty, non-whitespace
  `proof_session_id` and `instance_id` (`proof-session-id-nonempty`,
  `instance-id-nonempty`). Global uniqueness is deliberately out of scope.
- **H5 — naming (FIXED).** The `single-capability` check is renamed
  **`capability-declared`** ("the proof declares one expected capability and
  enforces it"); the invariant is unchanged in strength.

**New/renamed named checks:** `proof-session-id-nonempty`, `instance-id-nonempty`,
`capability-declared`, `call-count`, `result-count`, `call-result-correlation`,
`call-execution-correlation`; `exact-path-literal` strengthened.

**Tests:** `tests/test_b4_attestation.py` — 27 tests (14 prior + 13 new: the 9 Muse
adversarial cases, attack cases C and D, missing-result, and the H5 naming check),
all green. **M15.4 flake deliberately untouched** (unrelated shared-infrastructure
concern). **PHASE 2C NOT AUTHORIZED.**
