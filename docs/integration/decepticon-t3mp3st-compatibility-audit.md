# Decepticon + T3MP3ST Compatibility Audit — Phase 1

**Scope:** audit only. No integration, no adapter code, no dependency changes.
Every statement is labelled:

- **VERIFIED FROM SOURCE (local)** — physically read in this workspace.
- **VERIFIED FROM SOURCE (remote)** — read from the provider's published repository.
- **INFERRED** — a conclusion drawn from verified facts.
- **UNKNOWN / NOT VERIFIED** — insufficient evidence.
- **BLOCKED** — cannot be resolved without an action requiring approval.

---

## 1. Executive summary

- RAPHAEL is the governing system. Its Capability Fabric seam (M16.1–M16.4)
  is **IMPLEMENTED** and resolves capabilities to providers read-only; it never
  executes, authorizes, or decides completion. **VERIFIED FROM SOURCE (local)**
- Both external systems are **orchestration-first autonomous offensive platforms**,
  not capability libraries. Each wants to own mission planning, task dispatch,
  execution, findings, and a notion of completion. **VERIFIED FROM SOURCE (remote)**
- Consequently the dominant risk is not "can we call a tool" but **authority
  inversion**: letting an external orchestrator decide RAPHAEL mission completion
  or assert findings as verified. **INFERRED**
- **Verdict:** both providers are *containable in principle* only behind a
  strict adapter boundary that (a) exposes a **small, explicitly enumerated set
  of action-shaped capabilities**, (b) treats all external output as
  **observations only**, and (c) never imports the external orchestrator as an
  authority. **INFERRED**
- No capability collision is currently resolvable; the external capability
  surfaces are large, overlapping, and offensive. They must **not** be exposed
  wholesale. **VERIFIED FROM SOURCE (remote) + INFERRED**
- No code was changed. This document is the only artifact. **VERIFIED FROM SOURCE (local)**

---

## 2. Repository revisions inspected

| System | Path / Origin | Revision | Branch | Working tree |
|---|---|---|---|---|
| RAPHAEL | `/home/moiz/raphael-2.0-rbsv2r` | `d1a4c9538ff910757d2e54f1f8d48fe41676e943` | `feature/raphael-harness-live-model` | CLEAN |
| Decepticon | remote `BitterSecurity/Decepticon` → resolves to `PurpleAILAB/Decepticon` content | branch `main` (commit SHA not fetched) | `main` | n/a |
| T3MP3ST | remote `elder-plinius/T3MP3ST` | branch `main` (commit SHA not fetched) | `main` | n/a |

- **LOCAL CLONE: NOT AVAILABLE** for both providers (searched `/home/moiz`,
  `/mnt/c/Users/Moiz/{Desktop,Documents,source}` — no matches). **VERIFIED FROM SOURCE (local)**
- **Discrepancy:** the audit brief names `BitterSecurity/Decepticon`; the served
  repository content identifies itself as **`PurpleAILAB/Decepticon`**. They are
  treated as the same publication target. **VERIFIED FROM SOURCE (remote)**
- **BLOCKED:** provider commit SHAs are not pinned; downstream phases must pin exact SHAs.

---

## 3. Exact files inspected

**RAPHAEL (VERIFIED FROM SOURCE (local))**
`raphael_ibm_bob/capability_fabric.py`, `skills.py`, `specialization.py`,
`contracts.py`, `planner.py`, `replanner.py`, `runtime.py`, `broker.py`,
`policy.py`, `evidence_ledger.py`, `finding.py`, `verifier.py`, `falsifier.py`,
`quality_gate.py`, `harness/providers/openai_compat.py`,
`docs/capability-fabric.md`, `docs/http-api.md`.

**Decepticon (VERIFIED FROM SOURCE (remote))**
`README.md`, `docs/architecture.md`, `docs/library-usage.md`.

**T3MP3ST (VERIFIED FROM SOURCE (remote))**
`README.md`, `package.json`, `docs/SCOPE_AND_AUTHORIZATION.md`.

**UNKNOWN / NOT VERIFIED:** all other files of either provider (source, tests,
ADRs, exact type/contract modules, CLI/server internals).

---

## 4. RAPHAEL architecture (baseline that must be preserved)

**VERIFIED FROM SOURCE (local):**

- Fixture contract: `provider_id`, `list_capabilities()`,
  `declaration(capability)`, `build_action_request(...)` (`capability_fabric.py`).
- `CapabilityFabric`: deterministic registry; `resolve(capability, provider_id=None)`;
  zero → `CapabilityNotProvidedError`, one → resolve, many → `AmbiguousCapabilityError`
  (no silent shadowing); `default_fabric()` builds a fresh native provider.
- Native provider id `raphael-native`; capabilities `read, list, search, write, run_test`.
- Adoption: `openai_compat.validate_proposal`, `planner.Planner.plan_a`,
  `replanner.Replanner.replan` all resolve through the Fabric and stop at
  `contracts.ActionRequest`.
- Authority: `ActionRequest → BOBRuntime.submit → BOBBroker.submit →
  BOBPolicy.consult → capabilities.execute_capability → EvidenceLedger →
  Verifier/Falsifier → Replanner → BOBQualityGate` (sole COMPLETE authority).
- Provider observability (M16.4) shows resolved provider id read-only.

**Authority invariants (must hold for any future provider):**

```
DECLARATION ≠ AUTHORIZATION
PROVIDER RESOLUTION ≠ AUTHORIZATION
CAPABILITY RESOLUTION ≠ EXECUTION
PROVIDER SUCCESS ≠ VERIFIED FINDING
RETEST ≠ PROOF
PROVIDER RESULT ≠ QUALITY GATE COMPLETE
```

---

## 5. Decepticon audit

**VERIFIED FROM SOURCE (remote):**

- Autonomous red-team platform; Docker + Docker Compose; two networks:
  management `decepticon-net` (LiteLLM, PostgreSQL, LangGraph, Next.js web,
  Neo4j KGStore dual-homed, BHCE sidecar) and operations `sandbox-net`
  (Kali sandbox, Sliver C2, targets).
- Orchestration: **LangGraph Platform** hosts/orchestrates all 16 agents;
  agents drive the sandbox via the **Docker socket** (`docker exec`), not TCP.
- Execution surface: `bash` tool over `DockerSandbox.execute_tmux()` — persistent
  **tmux sessions**, interactive prompt detection, background commands with
  auto-notification middleware; output truncation/scratch-file rules; a watchdog
  kills commands > ~5M chars.
- Skill layer: **Skillogy** REST skill catalog + `SkillsMiddleware` with a
  server-side `allowed_path_prefixes` hard ACL.
- Library/SDK surface (`pip install decepticon`): agent factories
  (`create_<role>_agent(**kwargs)`), factory kwargs (`llm`, `tools`, `middleware`,
  `system_prompt`, `backend`, `sandbox`, `subagents`, `recursion_limit`),
  direct composition with `langchain.create_agent`, declarative `PluginBundle`
  overrides via entry points, and a **safety gate** (`SafetyOverrideViolation`)
  for safety-critical slots/tools.
- Contracts package `decepticon-core`: `RoE`, `CONOPS`, `DeconflictionPlan`,
  `OPPLAN`, `ThreatProfile`, `CleanupPlan`, `AbortPlan`, `ContactPlan`,
  `DataHandlingPlan`, `KnowledgeGraph/Node/Edge`.
- Engagement flow: planning → RoE/ThreatProfile/CONOPS/Deconfliction/Abort/Cleanup
  → OPPLAN → specialist dispatch → tool-backed execution → findings → KG/reports.
- The library explicitly is a **client SDK**: LLM calls and sandbox execution are
  routed to runtime services over HTTP (`DECEPTICON_LLM__PROXY_URL`, `SANDBOX_URL`).

**INFERRED:**

- Decepticon is **orchestrator + agent runtime + task manager + mission
  controller**. It cannot be used as a passive tool library without deliberate
  containment: its natural unit is "run an engagement," not "perform one action."
- Decepticon findings (`KnowledgeGraph` nodes/edges, workspace findings) are
  **provider observations**, not RAPHAEL findings.

**UNKNOWN / NOT VERIFIED:** exact Python exports for the task/objective state
machine, HTTP sandbox API contract, timeout/cancellation semantics of
`HTTPSandbox`, evidence/finding record schemas, DB schemas, licence-of-record
for the SDK.

---

## 6. T3MP3ST audit

**VERIFIED FROM SOURCE (remote):**

- TypeScript/Node (≥22) multi-agent offensive framework; `t3mp3st`/`tempest` CLIs.
- Architecture: **Mission Control ↔ Target Model ↔ Arsenal(tools)**; an **agent
  cell** of 8 operators (Recon, Scanner, Exploiter, Infiltrator, Exfiltrator,
  Ghost, Coordinator, Analyst); **Evidence Vault**, credential store, findings
  ledger; OPSEC layer, comms channel, LLM backbone.
- Tooling: "36 built-in tools by default; 111 with `T3MP3ST_FULL_ARSENAL`",
  dangerous/catalog-only drivers (metasploit, hydra, pacu, frida) behind narrow
  approved paths; `security_recon` exposed over **MCP** (`src/mcp-server.ts`);
  HTTP API (`npm run server`, `POST /api/mission/start`, `GET /api/mission/status`;
  binds `127.0.0.1:3333`).
- Authority model (`SCOPE_AND_AUTHORIZATION.md`): layers = human intent →
  **scope receipt** → **tool gate** modes (`safe_command`, `receipt_required`,
  `catalog_only`, `import_only`) → **evidence ledger** → **finding ledger**
  (severity, confidence, evidence IDs, acceptance criteria) → **retest**
  (queued/passed/failed/blocked) → **memory proposal** (human-reviewed).
- Dependencies include `playwright`, `@modelcontextprotocol/sdk`, `express`,
  `undici`, `web-tree-sitter`, `conf`, `inquirer`.
- Timeouts configurable: `T3MP3ST_LOCAL_AGENT_TIMEOUT_MS`,
  `T3MP3ST_TASK_TIMEOUT_MS`, `T3MP3ST_GENERAL_TIMEOUT_MS`.
- Explicit **egress-scope containment** (default on): built-in networked tools
  refuse off-scope hosts.
- Providers: OpenRouter/Venice/Anthropic/OpenAI/xAI/Novita, or keyless local
  agent, or offline local models.

**INFERRED:**

- T3MP3ST is a **full mission orchestrator with its own evidence/finding/retest
  ledgers**. Its finding/evidence model overlaps RAPHAEL's semantically but is
  **not** RAPHAEL's authority; importing its verdicts would violate RAPHAEL
  invariants.
- The `Arsenal` tool layer is the only plausible provider surface; `MissionControl`
  / `AgentLoop` / operator cells must remain **external orchestration**.

**UNKNOWN / NOT VERIFIED:** exact TypeScript class exports (`Tempest`,
`OperatorAgent`/`OperatorCell`, `MissionControl`, `TaskQueue`, `TargetEnvironment`,
`EvidenceVault`, `Arsenal`, `AgentLoop`), typed schemas, timeout/cancellation
code-level behaviour, MCP tool schema details, sandbox/host isolation guarantees.

---

## 7. Compatibility matrix

Legend: **C** = COMPATIBLE, **A** = ADAPTER REQUIRED, **X** = ARCHITECTURAL
CONFLICT, **?** = UNKNOWN.

| RAPHAEL contract | Decepticon | T3MP3ST | Status | Required adapter |
|---|---|---|---|---|
| capability identity (`Capability` enum) | tool/skill/agent surface, far larger | Arsenal tools | **A/X** | explicit allow-list mapping only |
| skill identity (`SkillDefinition`) | Skillogy `SKILL.md` + graph | Arsenal tool ids | **A** | map a whitelisted subset; do not import catalogs |
| role mapping (`Role`) | 16 agents | 8 operators | **X** | external roles must NOT become RAPHAEL roles |
| target schema | engagement target/env | `TargetEnvironment` | **A** | normalize to RAPHAEL target string + scope check |
| purpose/input schema | free-form agent prompts | free-form tool args | **A/X** | adapter must define closed input schema |
| `ActionRequest` | none (their own action model) | none | **A** | adapter builds `ActionRequest`; stop before execution |
| provider identity | none | none | **A** | new `provider_id` per adapter (e.g. `decepticon`, `t3mp3st`) |
| provider lifecycle | services must be up | server/CLI must be up | **A** | health + readiness seam (or `?`) |
| execution | Docker socket + tmux | local subprocess/tools/browser | **X** | execution stays EXTERNAL; never in Fabric |
| timeout | watchdog/limits (informal) | explicit `*_TIMEOUT_MS` | **A/?** | map RAPHAEL `timeout_seconds` → provider budget |
| cancellation | cooperative/background sessions | task timeouts (details `?`) | **A/?** | best-effort; document partial execution |
| failure | PASSED/BLOCKED + errors | tool errors/blocked | **A** | normalize to `ExecutionResult.success/error` |
| result | LLM text + tool output | transcripts + tool output | **A** | normalize to structured observation |
| evidence | workspace + KG + ledger | Evidence Vault/ledger | **A/X** | external evidence = new `evidence` records only |
| finding | KG nodes/findings | finding ledger (sev/conf/retest) | **X** | external findings ⇒ OBSERVATION, never RAPHAEL VERIFIED |
| artifact | workspace files | evidence files/screenshots | **A** | copy references only; no new artifact store |
| provenance | spans/traces (LangSmith) | run metadata | **A** | preserve run_id, op id, provider_id, ts |
| verification | internal | retest states | **X** | RAPHAEL Verifier is the only verifier |
| falsification | none explicit | "refuter panel" (their own) | **X** | RAPHAEL Falsifier only |
| replan | internal | internal | **X** | RAPHAEL Replanner only |
| Quality Gate | none | none | **C/X** | RAPHAEL Quality Gate only; providers must never emit completion |
| sandbox | Kali container + Docker socket | host/tools/browser/containers | **X** | provider isolation is provider-internal; RAPHAEL assumes none |
| networking | internal networks + internet | scope-contained internet | **X** | no network from Fabric; provider owns its network |
| persistence | PostgreSQL/Neo4j/web DB | local files/ledgers | **A/X** | never become RAPHAEL's store |
| orchestration | LangGraph | MissionControl/AgentLoop | **X** | must remain inside provider boundary; not RAPHAEL's |
| concurrency | multi-agent parallel | swarm/cells | **?** | undefined for a single-action provider |
| configuration | env/Docker/onboard | env/conf store | **A** | out-of-band only; no keys in RAPHAEL |
| dependency footprint | Python + Docker + DBs + services | Node + Docker + browsers + tools | **X** | sidecar/container, not in-process |
| security boundary | two-network Docker isolation | scope receipts + tool gates | **X** | no unrestricted host/network via Fabric |

**No row is COMPATIBLE in the strong sense** except the Quality-Gate ownership
row (RAPHAEL owns it). Nothing maps directly without an adapter.

---

## 8. Capability map (candidates only)

Explicitly **not** exposing either full arsenal. Candidate *action-shaped*
capabilities that could be **ADAPTER REQUIRED** (subject to a future, separately
authorized design):

| Provider | External capability/tool | RAPHAEL capability (candidate) | Inputs | Target | Output | Evidence | Sandbox | Network | Timeout | Failure | Mapping status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T3MP3ST | `security_recon` (MCP) | new `recon` | target, scope | host/URL | structured recon obs | observation | external | external (scope) | `TASK_TIMEOUT_MS` | tool error | REQUIRES NEW RAPHAEL CONTRACT |
| Decepticon | bash/read over sandbox | would map to `read`/`list`/`search` semantics but via external agent | prompt | path | tool output | observation | Kali container | internal | watchdog | PASSED/BLOCKED | ADAPTER REQUIRED (heavy) |
| both | asset/service fingerprinting | new `fingerprint` | target | host | fingerprints | observation | external | external | provider | provider | REQUIRES NEW RAPHAEL CONTRACT |
| both | browser automation | new `web_probe` | URL, action | URL | response/screenshot | observation | external | external | provider | provider | REQUIRES NEW RAPHAEL CONTRACT |
| T3MP3ST | source analysis (tree-sitter) | new `source_scan` | repo path | path | findings (obs) | observation | external | none | provider | provider | ADAPTER REQUIRED |
| both | exploitation / C2 / payloads | — | — | — | — | — | — | — | — | — | **NOT SUITABLE** (explicitly excluded) |

**DIRECTLY MAPPABLE:** none.
**NOT SUITABLE:** exploitation, C2, credential theft, persistence, exfiltration,
generic command execution, scanners run against arbitrary targets.

---

## 9. Orchestration conflict analysis

**VERIFIED FROM SOURCE (remote):** both systems contain their own
orchestration (Decepticon: LangGraph + OPPLAN; T3MP3ST: MissionControl +
AgentLoop + operator cell). **INFERRED:** each wants to be planner, task
manager, agent runtime, and mission controller.

| System | Wants to be | Containable? | Classification |
|---|---|---|---|
| Decepticon | provider + orchestrator + planner + agent runtime + mission controller | only if the adapter triggers **one bounded action** and ignores its OPPLAN/engagement planning | **REQUIRES ADAPTER DESIGN** (otherwise ARCHITECTURAL CONFLICT) |
| T3MP3ST | provider + orchestrator + planner + task manager + mission controller | same | **REQUIRES ADAPTER DESIGN** |
| Both | completion authority | never | **ARCHITECTURAL CONFLICT** |

**Desired containment pattern (only acceptable shape):**

```
RAPHAEL → Provider adapter → external internal orchestration (bounded, unavoidable)
        → provider result → RAPHAEL evidence → RAPHAEL verification/falsification
        → RAPHAEL Quality Gate
```

**Undesired (must be impossible):**

```
RAPHAEL → external orchestrator → external completion → RAPHAEL trusts external verdict
```

---

## 10. Sandbox / security analysis

| Dimension | Decepticon | T3MP3ST | RAPHAEL compatibility |
|---|---|---|---|
| host access | Docker socket bind-mount (agent→sandbox); `/workspace` bind | local execution on operator host by default | **INCOMPATIBLE** if bridged into Fabric |
| filesystem | container `/workspace` + scratch | repo/evidence/reports trees | adapter may pass a RAPHAEL workspace path only |
| subprocess | `docker exec`/tmux inside sandbox | local subprocess + tools | stays **external** |
| network | two internal Docker networks + internet | scope-contained internet (egress gate default on) | Fabric opens **no** network |
| Docker | yes (management + sandbox) | optional (`docker compose`) | out of RAPHAEL's boundary |
| container | Kali sandbox + sidecars | tool container | provider-internal |
| credentials | provider API keys + BHCE HMAC on management net; sandbox isolated | keys in env/conf store; scope receipts | **never** in RAPHAEL; no key passthrough |
| browser | not indicated | Playwright | provider-internal |
| database | PostgreSQL + Neo4j (two KGs) | local files/ledgers | must not become RAPHAEL's store |
| C2 | Sliver (dynamic-spawn) | Ghost/Coordinator operators | **explicitly excluded** |
| external APIs | LLM providers, NVD/OSV/EPSS | LLM providers, MCP | provider-internal |
| persistence | DBs + workspace | evidence/reports/bench | provider-internal |

**Existing enforcement:** Decepticon — network separation + credential isolation;
T3MP3ST — scope receipts + tool gates + egress-scope containment.
**RAPHAEL compatibility:** none of these are RAPHAEL-controlled.
**Adapter containment requirement:** the adapter must never grant RAPHAEL
processes host/subprocess/network access; it may only *invoke a provider that
already owns that access*. **Unresolved risk:** a provider with host/Docker
access, if ever invoked with attacker-influenced targets, becomes an
uncontained capability — this is an operational/authorization concern that
RAPHAEL's Policy cannot see inside the provider.

---

## 11. Evidence normalization

**VERIFIED FROM SOURCE (local):** RAPHAEL ledger kinds are
`request/decision/result/evidence/finding/gate` with sequence/ts/digest.

A provider operation can legitimately produce, at most:

| RAPHAEL record | Legitimate provider mapping |
|---|---|
| ACTION REQUEST | adapter builds the `ActionRequest` (RAPHAEL-owned) |
| POLICY DECISION | RAPHAEL Policy only |
| EXECUTION RESULT | normalized provider terminal outcome (success/error/timeout) |
| OBSERVATION (`evidence` kind, producer=`provider:<id>`) | provider output/artifact references |
| FINDING | **only** via RAPHAEL `FindingStore` lifecycle; provider input is a candidate |
| VERIFICATION / FALSIFICATION / REFUTATION | RAPHAEL only |
| GATE | RAPHAEL Quality Gate only |

**Must be preserved:** `run_id`, ActionRequest identity/sequence, `provider_id`,
provider operation id, target, timestamp, execution state, structured
stdout/error, artifact references, provider metadata.
**Must never be converted:** external severity/confidence → RAPHAEL finding
state; external "verified" → RAPHAEL VERIFIED; external "complete" → gate.

---

## 12. Finding compatibility

- RAPHAEL lifecycle: `UNVERIFIED → VERIFIED | REFUTED`, `VERIFIED/REFUTED → SUPERSEDED`,
  enforced by `FindingStore` (`finding.py`). **VERIFIED FROM SOURCE (local)**
- Decepticon findings live in its workspace + `KnowledgeGraph`. T3MP3ST findings
  live in its finding ledger with severity/confidence/retest. **VERIFIED FROM SOURCE (remote)**
- **INFERRED:** neither can be imported as RAPHAEL findings. They can only enter
  as **provider observations** attached to an execution result; promotion to a
  RAPHAEL finding requires RAPHAEL registration + verifier/falsifier.
- **Can external findings be independently falsified?** Only if the adapter
  supplies a reproducible target/evidence reference; otherwise **UNKNOWN**.
- **Do not** map external severity/confidence into RAPHAEL semantics (no contract).

---

## 13. Timeout / cancellation

| Aspect | Decepticon | T3MP3ST | RAPHAEL translation |
|---|---|---|---|
| timeout | watchdog + output limits; `recursion_limit` | `T3MP3ST_{LOCAL_AGENT,TASK,GENERAL}_TIMEOUT_MS` | `ActionRequest.timeout_seconds` → provider budget; **map explicitly** |
| cancellation | cooperative; background sessions continue | task timeouts (mechanism `?`) | best-effort; no guarantee of instant stop |
| partial execution | background commands + notifications | tool-level | must be reported honestly (`success=False`/timeout) |
| persistent sessions | tmux sessions persist | agent sessions | **outside** RAPHAEL's model; adapter must bound |
| interactive tools | first-class | possible | **not** representable as a single ActionRequest |

**UNKNOWN / NOT VERIFIED:** code-level cancellation guarantees for either provider.

---

## 14. Provider lifecycle

- Initialization/availability/health/startup/shutdown/authentication of either
  provider are **UNKNOWN / NOT VERIFIED** at the contract level.
- RAPHAEL's Fabric has **no health model**; M16.4 deliberately avoids fake
  availability states. **VERIFIED FROM SOURCE (local)**
- Any future adapter health representation must be `UNKNOWN / NOT VERIFIED`
  unless a real, side-effect-free readiness probe is defined.

---

## 15. Dependency / packaging analysis

| Provider | Runtime | Heavy dependencies | In-process feasible? |
|---|---|---|---|
| Decepticon | Python 3.x SDK + LangGraph/LangChain + Docker + LiteLLM + PostgreSQL + Neo4j + services | very large; **requires running services** | **No** |
| T3MP3ST | Node ≥22 | Playwright, MCP SDK, Express, browsers, security tools, Docker | **No** |

**INFERRED:** neither can be imported in-process into RAPHAEL's stdlib-only
governed core without violating RAPHAEL's dependency discipline (`pip install`
is not even available in this environment). Both require an **out-of-process
boundary**.

---

## 16. Integration shape options

| Option | Isolation | Complexity | Latency | Provenance | Timeout | Cancel | Dependency coupling | Failure containment | Security | Debugging | Reproducibility |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A. In-process adapter** | very low | low | low | weak (shared process) | hard | hard | very high | poor | poor | easy | poor |
| **B. Sidecar service/provider** | medium | medium | low | medium | medium | medium | low | good | medium | medium | medium |
| **C. Containerized provider** | high | high | medium | medium | medium | medium | low | excellent | high | medium | high |
| **D. CLI/subprocess provider** | medium | medium | medium | medium | medium | weak | low | good | medium | easy | medium |
| **E. HTTP/MCP provider** | high | medium | medium | strong (explicit contract) | good | medium | low | good | high | medium | high |

No single "best" score. **INFERRED recommendation:** prefer **C (containerized
provider) reachable via E (HTTP/MCP boundary)** — highest isolation, explicit
contract, best failure containment and reproducibility; accept the added
complexity. Reject **A** outright (shared-process coupling and no isolation).
D is acceptable only for read-only, non-networked capabilities.

---

## 17. Recommended adapter boundary (design-level only)

Smallest viable adapter surface, derived from RAPHAEL's fixture contract plus a
provider-invocation boundary:

- `provider_id` — new, distinct per provider.
- `list_capabilities()` — a **closed, explicitly enumerated** subset.
- `declaration(capability)` — RAPHAEL-owned declaration (never external metadata).
- `build_action_request(...)` — RAPHAEL-owned request construction.
- **NEW seam (required):** an *invocation* contract inside the provider boundary
  (`invoke(request) → normalized_result`) that is **not** part of the Fabric and
  **must not** grant execution authority. RAPHAEL's Fabric stops at `ActionRequest`;
  the adapter's invocation runs in the provider boundary and returns an
  observation that RAPHAEL treats as an execution result.
- `normalize_result()` — map provider output to `ExecutionResult`-shaped data +
  evidence records (producer=`provider:<id>`).
- `health()` / `shutdown()` — optional; `UNKNOWN / NOT VERIFIED` if unavailable.

**Already fits:** `provider_id`, `list_capabilities`, `declaration`, `build_action_request`.
**Requires translation:** target/purpose schemas; result/evidence normalization; timeouts.
**Requires a new seam:** `invoke`/`normalize_result` + health.
**Must remain outside the adapter:** orchestration, execution authority,
finding/evidence lifecycle, verification/falsification, Quality Gate.

---

## 18. Future multi-provider rules

- If both providers claim the same capability, **never** silently select one.
  Reuse the existing `AmbiguousCapabilityError` behaviour; require explicit
  `provider_id`. **VERIFIED FROM SOURCE (local)**
- **Capability collisions (identified, not to be exposed yet):** reconnaissance,
  web testing, browser automation, source analysis, cloud analysis, binary
  analysis, and (excluded) exploitation.
- This phase does **not** add any of these as RAPHAEL capabilities.

---

## 19. Required future contract changes (not implemented)

1. A **provider invocation boundary** (out-of-process) distinct from the Fabric.
2. An **observation/execution-result normalization contract** for external output.
3. An explicit **timeout/cancellation translation** contract.
4. A **scope/target authorization hand-off** so RAPHAEL Policy can bound external
   targets (today Policy sees only RAPHAEL `ActionRequest`s).
5. A **provider health** representation that is honest when unknown.

---

## 20. Proposed implementation sequence (for later authorization)

1. Pin provider SHAs; clone locally (read-only); verify claims in §5/§6.
2. Write a **DESIGN-ONLY** adapter contract document; obtain approval.
3. Build a **read-only, non-networked** provider (lowest-risk capability) first.
4. Add containerized/HTTP boundary; prove isolation + no authority leakage.
5. Only then consider any networked/action capability — each separately authorized.

---

## 21. Blockers

- **BLOCKED:** provider SHAs not pinned; provider repos not cloned locally.
- **BLOCKED:** exact provider invocation contracts (HTTP/MCP schemas, sandbox API)
  unverified.
- **BLOCKED:** no approved RAPHAEL scope hand-off mechanism for external targets.

## 22. Unknowns

- Decepticon `HTTPSandbox`/service API contracts; finding/KG schemas; cancellation.
- T3MP3ST exact TS classes (`Tempest`, `MissionControl`, `Arsenal`, `AgentLoop`),
  MCP tool schemas, timeout/cancellation internals, sandbox guarantees.
- Whether either provider can perform a **single bounded action** without
  escalating to its own engagement orchestration.
- Provider licences' compatibility for adapter use (Decepticon Apache-2.0 stated;
  T3MP3ST AGPL-3.0 stated) — legal review **UNKNOWN / NOT VERIFIED**.

## 23. Code changes made

- **NONE to RAPHAEL's governed core, the Capability Fabric, ActionRequest,
  Broker, Policy, Runtime, or Quality Gate.**
- The only artifact is this documentation file.

## 24. Exact files changed

- `docs/integration/decepticon-t3mp3st-compatibility-audit.md` — **NEW** (this document).

---

## 25. Final verdict

| Question | Answer |
|---|---|
| Can Decepticon become a RAPHAEL provider without bypassing authority? | **Only** behind a containerized/HTTP adapter that exposes a tiny closed capability set and never lets its orchestrator or findings act as authority. **INFERRED** |
| Can T3MP3ST? | Same, via its MCP/HTTP surface, with observations-only findings. **INFERRED** |
| Direct in-process integration? | **No** (dependencies, isolation, authority). **INFERRED** |
| Any directly mappable capability today? | **None.** |
| Any excluded surfaces? | Exploitation, C2, credential theft, persistence, exfiltration, generic command execution. **VERIFIED FROM SOURCE (remote) + policy** |
| Recommended shape? | Containerized provider behind an HTTP/MCP boundary; Fabric stays resolution-only. **INFERRED** |

**STOP.** No adapters implemented. Next phase requires separate authorization.

---

# Phase 2A — Pinned Repository / Deep Contract Audit

Labels as Phase 1: **VERIFIED FROM SOURCE** (local clone/pinned),
**VERIFIED FROM SOURCE (remote)**, **INFERRED**, **UNKNOWN / NOT VERIFIED**,
**BLOCKED**, **REQUIRES LEGAL REVIEW**.

## Pinned revisions and clone paths

| System | Source | Branch | HEAD SHA (pinned) | Local path | Working tree |
|---|---|---|---|---|---|
| RAPHAEL | `/home/moiz/raphael-2.0-rbsv2r` | `feature/raphael-harness-live-model` | `cc1524c3e2da4f2c0c6ad33c8e16329167d03b10` | local | CLEAN |
| Decepticon | `https://github.com/PurpleAILAB/Decepticon` | `main` | `31e1c8e786c83bb20f5c3d9ebc482cf9fb8ffa06` | `/home/moiz/audit-repos/Decepticon` | CLEAN |
| T3MP3ST | `https://github.com/elder-plinius/T3MP3ST` | `main` | `29824d5625ede419ac8cdae418c8f4c72c6270f7` | `/home/moiz/audit-repos/T3MP3ST` | CLEAN |

Both providers were cloned read-only (shallow, `--single-branch`). **No provider
file was modified.** **VERIFIED FROM SOURCE.**

### Corrected Decepticon repository identity

`git ls-remote https://github.com/BitterSecurity/Decepticon` and
`git ls-remote https://github.com/PurpleAILAB/Decepticon` return **identical
refs** (identical `HEAD` = `31e1c8e…` and identical branch list). **VERIFIED
FROM SOURCE.** Conclusion: `BitterSecurity/Decepticon` and
`PurpleAILAB/Decepticon` are the same repository (rename/redirect). The
authoritative clone target is `PurpleAILAB/Decepticon`. **INFERRED.**

### RAPHAEL invariant check (M16.3/M16.4 still true)

- `capability_fabric.py`: `CapabilityProvider` protocol (`provider_id`,
  `list_capabilities`, `declaration`, `build_action_request`); `CapabilityFabric`
  (`register`, `list_providers`, `get_provider`, `providers_for`, `resolve`);
  `default_fabric()` → single `raphael-native` provider; capabilities
  `read, list, search, write, run_test`. **VERIFIED FROM SOURCE (local).**
- Adoption holds: `planner.Planner.plan_a`, `replanner.Replanner.replan`,
  `harness/providers/openai_compat.validate_proposal` all call
  `.resolve(capability)` / `build_action_request`; none construct `ActionRequest`
  directly. **VERIFIED FROM SOURCE (local).**
- M16.4 provider observability present in `capability_arsenal.py`
  (`default_fabric().list_providers()/providers_for`). **VERIFIED FROM SOURCE (local).**

## Exact files and symbols inspected

### Decepticon (`/home/moiz/audit-repos/Decepticon`, SHA `31e1c8e`)

| File | Symbols |
|---|---|
| `packages/decepticon/decepticon/backends/http_sandbox.py` | `SandboxError(RuntimeError)`, `HTTPSandbox(BaseSandbox)`, `HTTPSandbox.execute_tmux(command, session, timeout, is_input, workspace_path) -> str`, `execute_tmux_async(...)`, endpoint `/read_session_log_diff` |
| `packages/decepticon/decepticon/backends/factory.py` | `build_sandbox_backend(config=None) -> HTTPSandbox`; `SANDBOX_URL`/`SANDBOX_TOKEN`; resolution order run-config → LangGraph `get_config()` → env |
| `packages/decepticon/decepticon/sandbox_server/app.py` | FastAPI routes: `GET /healthz`, `POST /execute`, `/upload_files`, `/download_files`, `/execute_tmux`, `/start_background`, `/poll_completion`, `/kill_session`, `/read_session_log_diff`, `/reset_session_log_offset`; `_verify_token(authorization)` bearer auth |
| `packages/decepticon/decepticon/sandbox_kernel/{base.py,daemon.py,tmux.py,jobs.py,egress.py}` | `SandboxBase(BaseSandbox)`, `DaemonSandbox(SandboxBase)`, `execute_tmux`, tmux/PS1 protocol |
| `packages/decepticon/decepticon/tools/bash/bash.py` | bash tool wrapping `HTTPSandbox.execute_tmux`; INLINE ≤15K, OFFLOAD 15K–100K to `.scratch/`, HARD_LIMIT >5M; ANSI strip + line compression |
| `packages/decepticon/decepticon/agents/build.py` | `build_middleware`, `build_tools`, `SafetyOverrideViolation`, `DECEPTICON_ALLOW_SAFETY_OVERRIDES` |
| `packages/decepticon/decepticon/agents/standard/*.py` | `create_decepticon_agent`, `create_soundwave_agent`, `create_exploit_agent`, … (16 factories) |
| `packages/decepticon/decepticon/capabilities/evidence.py` | `EvidenceValidation`, `validate_evidence(success_output, negative_output, success_patterns, negative_patterns)` — promotion via positive vs negative control, not exit status/confidence |
| `packages/decepticon-core/decepticon_core/types/engagement.py` | `RoE`, `CONOPS`, `DeconflictionPlan`, `OPPLAN`, `ThreatProfile`, `CleanupPlan`, `AbortPlan`, `ContactPlan`, `DataHandlingPlan`, `Objective`, `ObjectiveStatus`, `ObjectivePhase` (Pydantic) |
| `packages/decepticon-core/decepticon_core/types/kg.py` | `Node`, `Edge`, `KnowledgeGraph` (Pydantic) |

### T3MP3ST (`/home/moiz/audit-repos/T3MP3ST`, SHA `29824d5`)

| File | Symbols |
|---|---|
| `src/index.ts` | `interface Tempest`, `createTempest(config: TempestConfig): Tempest`, `class TempestCommand extends EventEmitter<CommandEvents>` |
| `src/types/index.ts` | `interface Finding` (severity, targetId, operatorId, phase, cvss/cve/cwe, `evidence: Evidence[]`, `verifyGate{passed,provenance:'none'|'context'|'tool',reasons}`, `assertedSeverity`), `interface Evidence {type:'screenshot'|'log'|'request'|'response'|'file'|'command'|'output', content, timestamp, metadata}`, `TargetStatus`, `Mission.status: 'planning'|'active'|'paused'|'completed'|'aborted'`, `Task.status: 'pending'|'assigned'|'in_progress'|'completed'|'failed'|'skipped'`, `TempestConfig` |
| `src/arsenal/index.ts` | `interface ToolExecution {id,toolName,startedAt,completedAt?,result?,error?}`, `class Arsenal.extend(EventEmitter)` with `register`, `execute(toolName, context): Promise<ToolResult>`, `setScope(ArsenalScope)`, `setApprovalController(ApprovalController)`; `ArsenalScope`, `scopeViolation` (egress gate before handler), `ToolErrorCategory` |
| `src/arsenal/catalog.ts` | `type ToolExecutionMode = 'safe_command'|'receipt_required'|'import_only'|'catalog_only'`; per-tool `execution` modes |
| `src/evidence/index.ts` | `class EvidenceVault.extend(EventEmitter)`; `redactCredential`, `RedactedCredential`; dedup by normalized title+target; `hasPassedVerificationGate` (`verifiedAt` + `verifyGate.passed`); events `finding:added/updated/verified/gate-blocked` |
| `src/mission/index.ts` | `class TaskQueue`, `class MissionControl` (`createMission`, `startMission`, `generateTasksForTarget`) |
| `src/operators/index.ts` | `class OperatorAgent`, `class OperatorCell` |
| `src/agent/index.ts` | `class AgentLoop` |
| `src/agent/local-agents.ts` | `T3MP3ST_LOCAL_AGENT_TIMEOUT_MS` (default 600000), ping timeout |
| `src/index.ts` / `src/server.ts` | `T3MP3ST_TASK_TIMEOUT_MS`, `T3MP3ST_GENERAL_TIMEOUT_MS`; Express API incl. `/api/missions`, `/api/approvals/*` (request/approve/reject/authorize-target), `/api/arsenal/*`, `/api/events`, `/health` |
| `src/mcp-server.ts` | MCP server entry (`security_recon`) |
| `src/target/index.ts` | `class TargetEnvironment.addTarget(...)` / update / setStatus |

## Deep contract analysis — Decepticon

- **Public/library seam is HTTP to a sandbox daemon** (`HTTPSandbox(base_url,
  token, timeout)` → `decepticon.sandbox_server` FastAPI), plus agent factories
  and Pydantic engagement contracts. **VERIFIED FROM SOURCE.**
- **Execution primitive:** `execute_tmux(command, session, timeout, is_input,
  workspace_path) -> str` (output text). Timeouts per call; output truncation;
  auto-background after 60 s; size watchdog. **VERIFIED FROM SOURCE.**
- **No RAPHAEL-shaped action/result types.** Provider work is expressed as
  agent prompt→bash session commands; results are strings/large outputs and
  offloaded scratch files. **VERIFIED FROM SOURCE.**
- **Its own evidence semantics exist** (`validate_evidence` positive vs
  negative control) and its own KG/OPPLAN objective lifecycle. These must map to
  RAPHAEL Verifier/Falsifier, never replace them. **VERIFIED FROM SOURCE + INFERRED.**
- **Scope model:** `RoE`/`OPPLAN`/`Objective` (Pydantic) — richer than RAPHAEL's
  mission/problem; no RAPHAEL→Decepticon scope hand-off exists. **VERIFIED FROM SOURCE.**

**Cleanest adapter boundary:** the **sandbox daemon HTTP surface**
(`/execute`, `/execute_tmux`, `/upload_files`, `/download_files`,
`/start_background`, `/poll_completion`, `/kill_session`,
`/read_session_log_diff`) — but invoking it directly would be a *generic command
execution* surface, which RAPHAEL policy explicitly excludes. A safe adapter can
only expose a **closed, named, non-arbitrary operation** (e.g. a read-only file
inspection) — not raw bash. **INFERRED.**

## Deep contract analysis — T3MP3ST

- **`Tempest` is a monolithic module bundle** (command, cell, mission, targetEnv,
  vault, arsenal, approval, opsec, comms, analysis, llm, general, exploit,
  scanner, browser, benchmark, reasoning, cognition, swarm, cloud, persistence,
  learning, knowledge, protocols, evasion, reporting, workflow). It is an
  **orchestrator + agent runtime + mission controller**, not a tool library.
  **VERIFIED FROM SOURCE.**
- **`Arsenal.execute(toolName, context): Promise<ToolResult>`** is the closest
  action primitive; it enforces a **hard egress-scope gate before any handler**
  and an **approval gate** for intrusive tools. `ToolExecution` records
  `{id, toolName, startedAt, completedAt?, result?, error?}`. **VERIFIED FROM SOURCE.**
- **Its own finding/evidence lifecycle:** `Finding` carries severity/CVSS/CVE/CWE,
  `evidence[]`, and a `verifyGate{passed, provenance}` that *downgrades unverified
  severity*. `EvidenceVault.hasPassedVerificationGate` requires `verifiedAt` +
  `verifyGate.passed`. **This is T3MP3ST verification authority and must not
  become RAPHAEL verification authority.** **VERIFIED FROM SOURCE.**
- **Mission/task model:** `MissionControl` (planning/active/paused/completed/aborted),
  `TaskQueue` (pending/assigned/in_progress/completed/failed/skipped),
  `TargetEnvironment`. **VERIFIED FROM SOURCE.**

**Cleanest adapter boundary:** the **MCP `security_recon`** surface or a bounded
subset of `Arsenal.execute` for read-only/non-networked tools. Full `Tempest`
must remain external. **INFERRED.**

## Single-bounded-action feasibility

| Provider | Can it run ONE RAPHAEL ActionRequest without owning the mission? | Classification |
|---|---|---|
| Decepticon | Only via the sandbox daemon, which is **arbitrary command execution**; a bounded *read-only* op is feasible but must be a closed command, not model-chosen. Agent factories assume an engagement/OPPLAN. | **ADAPTER REQUIRES INTERNAL ORCHESTRATION** for agent-level ops; bounded sandbox op feasible **with a closed allow-list** |
| T3MP3ST | `Arsenal.execute(toolName, context)` is a single bounded tool call with scope+approval gates. But `Tempest`/MissionControl assume mission/operator context; findings promote through its own gate. | **ADAPTER REQUIRES INTERNAL ORCHESTRATION** unless restricted to a single gated Arsenal tool |

Neither can be safely invoked as "just a tool" without a **closed capability
allow-list** and an explicit "external result is an observation" rule.
**INFERRED.**

## Scope / authorization hand-off

| Dimension | RAPHAEL input | Decepticon input | T3MP3ST input | Status |
|---|---|---|---|---|
| target | `ActionRequest.target` (string) | engagement target / sandbox workspace | `TargetEnvironment` target address/type/zone | **TRANSLATION REQUIRED** |
| authorized scope | `Mission.scope` (string substring rule in Policy) | `RoE` + `DeconflictionPlan` (Pydantic) | `ArsenalScope{allowedHosts,allowLoopback,allowPrivate}` + scope receipts | **MISSING** (RAPHAEL scope ≠ provider scope) |
| exclusions | not modelled | DeconflictionPlan | scope receipts/approvals | **MISSING** |
| operation window | `ActionRequest.timeout_seconds` | per-call timeout | `*_TIMEOUT_MS` | **TRANSLATION REQUIRED** |
| allowed capability | `Capability` enum | tool set per agent | Arsenal tool + `ToolExecutionMode` | **TRANSLATION REQUIRED** |
| allowed network | none (Fabric opens no network) | sandbox-net (internal) | egress-scope gate | **CONFLICT** (RAPHAEL cannot express this) |
| allowed filesystem | workspace scope rule | `/workspace` bind | host/repo/evidence paths | **CONFLICT** |
| data handling | not modelled | `DataHandlingPlan` | redaction posture | **MISSING** |
| provider RoE | n/a | full RoE/OPPLAN | rules + approvals | **provider-internal** |

No unified schema is proposed here. **VERIFIED FROM SOURCE + INFERRED.**

## Timeout / cancellation mapping

| RAPHAEL | Decepticon | T3MP3ST |
|---|---|---|
| `ActionRequest.timeout_seconds` → provider budget | per-call `timeout` on `/execute_tmux`; auto-background after 60 s; watchdog >5M chars; connection retry budget ~150 s | `T3MP3ST_TASK_TIMEOUT_MS`, `T3MP3ST_GENERAL_TIMEOUT_MS`, `T3MP3ST_LOCAL_AGENT_TIMEOUT_MS` (600000 default) |
| hard vs soft | soft/stepwise (tmux session can persist) | per-task/agent timers |
| cancellation | `/kill_session` | task status control (mechanism code-level **UNKNOWN / NOT VERIFIED**) |
| partial result | session log diff | task result/error |
| orphan risk | **HIGH** — persistent tmux sessions + background jobs | **MEDIUM** — local agent sessions |

**VERIFIED FROM SOURCE (timeout surfaces/symbols).** Code-level cancellation
guarantees: **UNKNOWN / NOT VERIFIED.**

## Result / error normalization (minimum fields derived from source)

From `ToolExecution`/`ToolResult` (T3MP3ST) and `execute_tmux`→str + artifact
offload (Decepticon), the minimum RAPHAEL-normalizable fields are:

```
provider_id        # adapter-assigned ("decepticon" | "t3mp3st")
operation_id       # T3MP3ST ToolExecution.id ; Decepticon session/command id
status             # success | failure | timeout | denied | unavailable | partial | cancelled
output             # bounded text (already truncated by provider where applicable)
artifacts          # references only (Decepticon .scratch/ ; T3MP3ST evidence files)
error              # provider error string (ToolError category / SandboxError)
metadata           # provider-specific, non-secret
started_at/completed_at
```

This is a **derived minimum**, not an assumed type. It maps to RAPHAEL's
`ExecutionResult` + `ledger.append_evidence(producer="provider:<id>")`.
**INFERRED from source.**

## Evidence normalization

| External output | RAPHAEL mapping |
|---|---|
| execution output / stderr | `ExecutionResult` + observation `evidence` |
| logs, screenshots, files | artifact references (no new artifact store) |
| tool receipts (T3MP3ST `ToolExecution`) | observation `evidence` with `operation_id` |
| findings (Decepticon KG/`Finding`; T3MP3ST `Finding`+`verifyGate`) | **observation only**; never RAPHAEL VERIFIED |
| target metadata | `evidence` metadata |
| provider state | `evidence` metadata |

**PROHIBITED direct mappings:** provider `VERIFIED`, provider `COMPLETE`,
provider `REFUTED`, T3MP3ST `verifyGate.passed`, Decepticon
`EvidenceValidation.validated` → RAPHAEL authority. **VERIFIED FROM SOURCE +
policy.**

## Provenance contract

| Provider identifier | Exists? | RAPHAEL mapping |
|---|---|---|
| operation id | T3MP3ST `ToolExecution.id`; Decepticon session/command | → evidence `operation_id` |
| task id | T3MP3ST `TaskQueue` task | → evidence metadata |
| session id | Decepticon tmux session | → evidence metadata |
| artifact id | both (file refs) | → `artifact_ref` |
| finding id | T3MP3ST `Finding.id`; Decepticon KG node | → evidence metadata only |
| agent id | Decepticon factory role; T3MP3ST `operatorId` | → evidence metadata |
| run_id / ActionRequest id | **RAPHAEL-assigned** | adapter must stamp these on every record |

**Provenance gap:** providers have no notion of RAPHAEL `run_id` or
`ActionRequest` identity; the adapter must inject/stamp them. **VERIFIED FROM
SOURCE + INFERRED.**

## Sandbox / security boundary (source-grounded)

| Concern | Decepticon | T3MP3ST |
|---|---|---|
| where Docker socket is used | **NOT in the SDK path**; SDK talks HTTP to `sandbox_server`; Docker socket lives with the daemon/sandbox (architecture doc) | Docker optional (`docker compose`), binds `127.0.0.1:3333` |
| where commands execute | inside the sandbox container via daemon (`/execute_tmux`) | host or container; Playwright; child processes |
| network | sandbox-net vs management-net (isolated) | egress-scope gate (`ArsenalScope`) before handler |
| credential visibility | provider keys/BHCE token on management net; sandbox isolated | redaction (`redactCredential`); keys in env/conf store |
| filesystem | `/workspace` bind; `.scratch` offload | repo/evidence/reports paths |
| what RAPHAEL would invoke | HTTP commands to daemon (**arbitrary exec**) | a single gated `Arsenal.execute` tool |

**Critical:** because the Decepticon daemon is a **generic command surface**,
exposing it to RAPHAEL would create the very "unrestricted host/network access"
the brief forbids. Any Decepticon adapter must therefore expose **only a closed,
named, non-arbitrary operation**. **VERIFIED FROM SOURCE + policy.**

## License / packaging

- Decepticon: **Apache-2.0** (stated in README + `LICENSE`). **VERIFIED FROM SOURCE (remote).**
- T3MP3ST: **AGPL-3.0** (`package.json` `license: AGPL-3.0-or-later`, `LICENSE`). **VERIFIED FROM SOURCE.**
- Technical note: RAPHAEL would **not** link either in-process (out-of-process
  HTTP/MCP/container boundary), which reduces but does not eliminate obligations.
- **REQUIRES LEGAL REVIEW.** This audit makes **no** legal conclusion.

## Integration shape re-evaluation (source-level)

| Option | Isolation | Reproducibility | Dependency coupling | Timeout | Cancellation | Provenance | Security | Failure containment | Observability | Complexity |
|---|---|---|---|---|---|---|---|---|---|---|
| A in-process | very low | low | very high | weak | weak | weak | poor | poor | weak | low |
| B sidecar | medium | medium | low | medium | medium | medium | medium | good | medium | medium |
| C containerized | high | high | low | medium | medium | strong | high | excellent | medium | high |
| D CLI/subprocess | medium | medium | low | medium | weak | medium | medium | good | easy | medium |
| E HTTP/MCP | high | high | low | good | medium | strong | high | good | strong | medium |

**Source-level finding reinforces Phase 1:** Decepticon's **SDK already speaks
HTTP to a sandbox daemon**, and T3MP3ST exposes **MCP + HTTP + a gated
`Arsenal.execute`**. Therefore **C (containerized provider) reached via E
(HTTP/MCP)** remains the recommendation: it bounds both providers out-of-process,
gives explicit contracts, and preserves RAPHAEL's authority. **INFERRED.**

## Candidate capability matrix (smallest possible)

| Provider | Candidate | Classification |
|---|---|---|
| Decepticon | closed read-only sandbox file inspection (NOT raw bash) | **REQUIRES NEW RAPHAEL CONTRACT** (and a closed command allow-list) |
| Decepticon | raw `/execute_tmux` / bash | **NOT SUITABLE** (generic exec) |
| T3MP3ST | MCP `security_recon` (scope-gated) | **REQUIRES NEW RAPHAEL CONTRACT** |
| T3MP3ST | single gated `Arsenal.execute` read-only tool | **ADAPTER REQUIRED** |
| T3MP3ST | source analysis (tree-sitter ingest) | **ADAPTER REQUIRED** |
| both | exploitation / C2 / credential / persistence / exfiltration | **NOT SUITABLE** |

**DIRECTLY MAPPABLE: none.** **VERIFIED FROM SOURCE + policy.**

## Proposed adapter boundary (Phase 2A, design-level)

Keep RAPHAEL's Fabric unchanged:
`provider_id` / `list_capabilities()` / `declaration()` / `build_action_request()`.

Add, **outside the Fabric**, a provider-runtime boundary:

```
RAPHAEL ActionRequest
   ↓ (adapter, out-of-process)
ProviderRuntime.invoke(action_request) -> ProviderResult
   ↓
ProviderResult -> RAPHAEL ExecutionResult + observation evidence
   ↓
RAPHAEL Runtime → Broker → Policy (unchanged authority)
```

- `ProviderRuntime` lives in the **provider boundary** (container/sidecar),
  reached over HTTP/MCP; it **must not** be callable from `capability_fabric.py`.
- `invoke` accepts **only closed capability ids**, never free-form commands or prompts.
- `normalize_result` emits `ProviderResult` (fields per §Result normalization);
  the adapter converts it to RAPHAEL `ExecutionResult` + observation evidence.
- **Must remain outside the adapter:** orchestration, execution authority,
  finding/evidence lifecycle, verification/falsification, Quality Gate.
- **Required new RAPHAEL seams:** out-of-process invocation boundary,
  observation/result normalization, timeout/cancellation translation,
  scope/target authorization hand-off, honest provider health.

## Blockers

- **BLOCKED:** no approved RAPHAEL scope/target hand-off for external targets.
- **BLOCKED:** both providers' natural surface (agent factories / `Tempest` /
  command execution) is broader than a bounded action; a closed allow-list must
  be designed and approved before any adapter.
- **BLOCKED:** cancellation guarantees unverified at code level.

## Remaining unknowns

- Decepticon: exact `/execute_tmux` timeout/auto-background code semantics;
  `DaemonSandbox` cancellation; KG write path.
- T3MP3ST: `AgentLoop`/`MissionControl` cancellation internals; MCP tool schema
  for `security_recon`; `ApprovalController` contract.
- Whether either can be restricted to a **single bounded action** in practice.
- Legal: **REQUIRES LEGAL REVIEW** (Apache-2.0 vs AGPL-3.0).

## Exact future implementation sequence (for separate authorization)

1. Approve the closed capability allow-list + scope hand-off contract.
2. Design-only `ProviderRuntime` contract doc (no code).
3. Build the lowest-risk **read-only, non-networked** provider in a container behind HTTP/MCP.
4. Prove isolation + no authority leakage (tests + governance audit).
5. Only then consider any networked/action capability, each separately authorized.

## Code changes

**NONE** to RAPHAEL's governed core, the Capability Fabric, ActionRequest,
Broker, Policy, Runtime, or Quality Gate, and **NONE** to either provider.
Artifact changed: this document only.

## Audit artifact revision

- `docs/integration/decepticon-t3mp3st-compatibility-audit.md` — **UPDATED** (this
  Phase 2A section). Commit SHA recorded in the Phase 2A report.

**STOP.** Phase 2A is audit/design only. No adapters implemented. Phase 2B/3
requires separate authorization.
