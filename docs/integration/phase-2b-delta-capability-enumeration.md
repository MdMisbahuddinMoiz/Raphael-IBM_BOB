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
