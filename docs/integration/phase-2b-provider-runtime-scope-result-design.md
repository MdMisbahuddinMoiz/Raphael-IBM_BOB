# Phase 2B — ProviderRuntime + Scope/Result Contract Design

**STATUS: DESIGN ONLY — AUTHORIZED. IMPLEMENTATION: PROHIBITED. PROVIDER EXECUTION: PROHIBITED.**

Labels: **VERIFIED FROM SOURCE** (local/remote as noted), **INFERRED**,
**UNKNOWN / NOT VERIFIED**, **BLOCKED**, **REQUIRES LEGAL REVIEW**.

Baseline: RAPHAEL `eb794a1e9a341b7d6046b0b852ba704b5b34fefc`; audit artifact
`docs/integration/decepticon-t3mp3st-compatibility-audit.md` (Phase 1 + 2A).
Pinned providers: `PurpleAILAB/Decepticon@31e1c8e`; `elder-plinius/T3MP3ST@29824d5`.
No provider has authority over RAPHAEL findings/verification/falsification/replan/gate.
**VERIFIED FROM SOURCE.**

---

## 1. Phase 2B status

Design-only. This document defines the minimum out-of-process contract to
introduce external providers **without** granting them authority. No code is
implemented; no provider is invoked. **VERIFIED FROM SOURCE (this document).**

## 2. Architectural objective

```
ActionRequest                       (RAPHAEL-owned, unchanged)
  ↓
ProviderRuntime.invoke(...)         (NEW: out-of-process boundary)
  ↓
external provider invocation        (Decepticon / T3MP3ST — external)
  ↓
ProviderResult                      (NEW: normalized envelope, RAPHAEL-owned)
  ↓
RAPHAEL normalization               (NEW)
  ↓
Execution Result + Observation Evidence   (existing ledger kinds)
  ↓
RAPHAEL Verification / Falsification / Finding lifecycle  (unchanged)
  ↓
Quality Gate                        (unchanged, sole COMPLETE authority)
```

Immutable semantic rules (restated verbatim):

```
DECLARATION ≠ AUTHORIZATION
PROVIDER RESOLUTION ≠ AUTHORIZATION
CAPABILITY RESOLUTION ≠ EXECUTION
PROVIDER SUCCESS ≠ VERIFIED FINDING
RETEST ≠ PROOF
PROVIDER RESULT ≠ QUALITY GATE COMPLETE
```

## 3. Closed capability allow-list proposal

Principle: capabilities are **closed**, **enumerated**, and **narrow**. The
provider's own arsenal/agent surface is never exposed. Nothing here is
implemented or enabled.

| # | capability ID | purpose | candidate provider(s) | target requirements | scope requirements | input contract | bounded output contract | expected evidence | verification expectation | read-only / non-networked | acceptable for first proof | rejection reason for broader alternatives |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | `static_file_manifest` | Read-only listing/metadata of a bounded file set inside a RAPHAEL workspace | Decepticon (sandbox read), T3MP3ST (Arsenal read-only tool) | path inside approved workspace root | workspace root allow-list | `{path, depth, max_entries}` | `{entries:[{path,size,sha256?}], truncated:bool}` | observation `evidence` (producer `provider:<id>`) | RAPHAEL re-hashes / spot-checks | yes / yes | **YES (proposed first proof)** | — |
| C2 | `static_file_inspect` | Read-only content inspection of one bounded file (bounded bytes) | Decepticon (sandbox read), T3MP3ST (Arsenal read-only) | one file inside workspace | same | `{path, max_bytes}` | `{path, bytes_read, sha256, content_excerpt}` | observation `evidence` | RAPHAEL re-reads + hashes | yes / yes | yes (second) | — |
| C3 | `source_scan_static` | Static source analysis over a bounded repo subtree (no build, no network) | T3MP3ST (tree-sitter ingest) | dir inside workspace | read-only subtree | `{path, languages[], max_files}` | `{findings:[{file,line,rule,excerpt}], truncated}` | observation `evidence` | RAPHAEL Falsifier must challenge | yes / yes | later | no execution/network allowed |
| C4 | `fingerprint_banner` | Network fingerprint of an **authorized** target | T3MP3ST (recon) / Decepticon (recon) | host/URL in explicit scope | `ArsenalScope`-like explicit hosts | `{target, timeout_ms}` | `{services:[...], banners:[...]}` | observation `evidence` | RAPHAEL independent verification | no / **networked** | **no** | requires approved scope hand-off; not first proof |
| C5 | `web_probe_static` | Bounded HTTP request to an authorized URL | T3MP3ST (Playwright/HTTP) | URL in explicit scope | explicit host allow-list | `{url, method, max_bytes}` | `{status, headers, body_excerpt}` | observation `evidence` | RAPHAEL independent verification | no / networked | no | browser/network risk; later only |
| — | raw `execute_tmux` / bash / generic command | — | Decepticon | — | — | — | — | — | — | no | **NOT SUITABLE** | generic execution surface |
| — | full `Arsenal` / `Tempest` / AgentLoop / MissionControl | — | T3MP3ST | — | — | — | — | — | — | no | **NOT SUITABLE** | orchestrator/authority surface |
| — | exploitation / C2 / credential / persistence / exfiltration | — | both | — | — | — | — | — | — | no | **NOT SUITABLE** | explicitly excluded |

**First-proof candidate: `C1 static_file_manifest`** — read-only, non-networked,
bounded, deterministic, incapable of becoming generic command execution, and
incapable of changing RAPHAEL authority. **INFERRED (design selection).**

## 4. Scope hand-off schema (field-level, design)

Five concepts are kept **separate** and must never be merged:

```
AUTHORIZATION      — who approved this action (operator/Policy), opaque token
TARGET SCOPE       — exactly which target identities are in scope
CAPABILITY SCOPE   — exactly which capability id is permitted
RESOURCE SCOPE     — filesystem roots / network classes / process classes
EXECUTION TIME LIMIT — the only time budget the provider may consume
```

Proposed `ScopeHandoff` (design; not implemented):

| field | type | required | meaning | notes |
|---|---|---|---|---|
| `schema_version` | string | yes | contract version | e.g. `"2b.1"` |
| `authorization_token` | opaque string | yes | RAPHAEL-issued **reference** proving Policy ALLOW | never a provider credential; never grants provider-local authority |
| `run_id` | string | yes | RAPHAEL run identifier | stamped on every record |
| `action_request_id` | string | yes | RAPHAEL ActionRequest identity | — |
| `provider_id` | string | yes | selected provider | e.g. `decepticon`, `t3mp3st` |
| `capability_id` | string | yes | **closed** capability id (C1…) | provider must reject unknown ids |
| `target_identity` | string | yes | normalized target | opaque to provider semantics |
| `target_scope` | string[] | yes | explicit in-scope identities | exact match / explicit patterns only |
| `exclusions` | string[] | no | explicit deny list | wins over `target_scope` |
| `allowed_resource_classes` | enum[] | yes | `{filesystem_read, filesystem_write, network, process, container}` | default: read-only, no network, no process |
| `network_permission` | enum | yes | `denied` \| `explicit_hosts` | default `denied` |
| `network_allow_hosts` | string[] | cond. | required when `explicit_hosts` | — |
| `filesystem_permission` | enum | yes | `denied` \| `workspace_read` \| `workspace_write` | default `workspace_read` |
| `filesystem_roots` | string[] | cond. | roots the provider may touch | must be inside the RAPHAEL workspace |
| `data_handling_constraints` | enum[] | yes | `{no_secret_copy, redact_credentials, no_exfiltration}` | echoes provider redaction posture |
| `max_duration_ms` | integer | yes | execution time budget | maps to provider timeout |
| `cancellation_mode` | enum | yes | `cooperative` \| `unsupported` | honest |
| `artifact_constraints` | object | yes | `{max_bytes, allowed_types[]}` | references only, no new store |
| `output_size_limit_bytes` | integer | yes | bounded output | provider must truncate |
| `provenance_required` | string[] | yes | identifiers the provider must echo | run_id, action_request_id, provider_id, operation_id |

**Rule:** a provider must never infer broader authority from the target string
or its own local configuration. **VERIFIED FROM SOURCE (invariant) + design.**

## 5. ProviderRuntime contract (field-level, design)

```
ProviderRuntime.invoke(scope: ScopeHandoff, action: ActionRequest) -> ProviderResult
```

- Lives **out of process** (container/sidecar) behind HTTP/MCP.
- **Not** callable from `capability_fabric.py`; the Fabric remains resolution-only.
- Accepts only **closed capability ids**; rejects free-form commands/prompts.
- Constructs nothing that grants authority; it only carries a RAPHAEL-owned
  `ScopeHandoff` to a provider and returns a `ProviderResult`.

Proposed request envelope:

| field | type | notes |
|---|---|---|
| `scope_handoff` | `ScopeHandoff` | §4 |
| `capability_id` | string | must equal `scope_handoff.capability_id` |
| `target` | string | must be within `target_scope`, not in `exclusions` |
| `parameters` | map | capability-specific, **closed schema** per capability |
| `max_duration_ms` | integer | mirror of scope budget |
| `requested_at` | timestamp | UTC |

**Forbidden in the envelope:** API keys, provider credentials, free-form
prompts, shell strings, arbitrary URLs outside scope, unbounded file paths.
**VERIFIED FROM SOURCE (invariant).**

## 6. ProviderResult contract (field-level, design)

| field | type | required | meaning |
|---|---|---|---|
| `schema_version` | string | yes | contract version |
| `provider_id` | string | yes | must equal request provider |
| `operation_id` | string | yes | provider-assigned op id (T3MP3ST `ToolExecution.id` / Decepticon session/command id) |
| `action_request_id` | string | yes | echoed RAPHAEL identity |
| `run_id` | string | yes | echoed RAPHAEL run id |
| `capability_id` | string | yes | echoed closed capability |
| `status` | enum | yes | see below |
| `output` | bounded text | yes | truncated to `output_size_limit_bytes` |
| `artifacts` | ref[] | no | `{name, ref, sha256?, bytes?}` — references only |
| `error` | object | no | `{category, message, provider_code?}` (redacted) |
| `started_at` / `completed_at` | timestamps | yes | UTC |
| `duration_ms` | integer | yes | measured |
| `execution_metadata` | map | no | non-secret provider metadata |
| `provenance` | object | yes | echoed identifiers (§8) |
| `timeout` | object | cond. | `{limit_ms, exceeded:bool}` |
| `cancellation` | object | cond. | `{requested:bool, acknowledged:bool, supported:bool}` |
| `scope_echo` | object | yes | `{target, capability_id, network_permission, filesystem_permission}` for audit |

**Status enum (bounded, explicit):**

`success` | `failure` | `timeout` | `denied` | `unavailable` | `partial` | `cancelled`

- Additional state considered: `unsupported` (capability not supplied) — folded
  into `denied` (with `error.category=unsupported`) to keep the enum small; or
  kept explicit. **Decision: keep `denied` + `error.category` to avoid enum
  growth; mark `unsupported` via `error.category`.** **INFERRED (design).**
- **`success` means the provider completed its operation — it does NOT imply a
  RAPHAEL-verified finding.** The adapter must never translate `success` into
  VERIFIED/COMPLETE. **VERIFIED FROM SOURCE (invariant).**

## 7. Result normalization model (design)

Mapping from `ProviderResult` → RAPHAEL-native:

| ProviderResult part | RAPHAEL artifact | authority |
|---|---|---|
| (A) `status` + `output`/`error`/`timeout` | **ExecutionResult** (`success`, `output`, `error`) | RAPHAEL-owned record |
| (B) `output`, `execution_metadata`, `scope_echo` | **Observation evidence** (`ledger.append_evidence`, `producer="provider:<id>"`) | observation only |
| (C) `artifacts[]` | **Artifact reference** (`artifact_ref`) on the result/evidence | reference only; **no new artifact store** |
| (D) `error` | **Provider diagnostic** field on the observation | diagnostic only |
| (E) `provenance`, `operation_id`, timestamps | **Provenance metadata** on the evidence | audit only |

**Hard normalization boundary:**

Provider output **MAY** become: execution result, observation evidence,
artifact reference, provider diagnostic, provenance metadata.
Provider output **MUST NEVER** become: VERIFIED finding, REFUTED finding,
COMPLETE gate decision, authorization, policy approval. Promotion to a RAPHAEL
finding requires RAPHAEL `FindingStore` registration + RAPHAEL
Verifier/Falsifier; completion requires the RAPHAEL Quality Gate.
**VERIFIED FROM SOURCE (invariant) + design.**

## 8. Provenance model (design)

Chain that must remain auditable end-to-end:

```
RAPHAEL run_id
  → ActionRequest (action_request_id, capability, target, requester, plan_id, finding_id)
  → ProviderRuntime invocation (invocation_id, provider_id, scope snapshot)
  → provider operation (operation_id)
  → ProviderResult (echoed ids)
  → normalized evidence/artifacts (evidence_id, artifact_ref)
```

Identifiers that must survive every hop: `run_id`, `action_request_id`,
`provider_id`, `capability_id`, `target`, `scope snapshot`, `operation_id`,
`evidence_id`, `artifact_ref`, timestamps.

Audit must answer: who requested the action; which capability was resolved;
which provider was selected; what scope was handed off; what the provider
actually returned; how RAPHAEL interpreted the result. **INFERRED (design).**

## 9. Timeout / cancellation model (design)

Phase 2A source facts:

- **Decepticon**: per-call `timeout` on `/execute_tmux`; auto-background after
  60 s; size watchdog (>5 M chars); HTTP connection retry budget ~150 s;
  cancellation via `/kill_session`. **VERIFIED FROM SOURCE (remote/pinned).**
- **T3MP3ST**: `T3MP3ST_TASK_TIMEOUT_MS`, `T3MP3ST_GENERAL_TIMEOUT_MS`,
  `T3MP3ST_LOCAL_AGENT_TIMEOUT_MS` (default 600000); code-level cancellation
  guarantees **UNKNOWN / NOT VERIFIED**. **VERIFIED FROM SOURCE + UNKNOWN.**

RAPHAEL-side abstraction (honest, no guarantees assumed):

| situation | RAPHAEL behavior |
|---|---|
| timeout before provider starts | status `timeout`, no execution, no evidence of work |
| timeout during execution | status `timeout`; `timeout.exceeded=true`; partial output allowed with `partial` semantics |
| cancellation requested | `cancellation.requested=true` |
| cancellation acknowledged | `cancellation.acknowledged=true` |
| cancellation unsupported | `cancellation.supported=false`; RAPHAEL must not claim it stopped |
| provider unreachable | status `unavailable` |
| provider process dies | status `failure` (or `unavailable` if no op id) |
| provider may continue after RAPHAEL timeout | explicit `timeout.orphan_possible=true`; recorded in observation |

**Rule:** cancellation is **never** assumed guaranteed. If source does not
establish it, it is `UNKNOWN / NOT VERIFIED` and surfaced as such.
**VERIFIED FROM SOURCE (facts) + design.**

## 10. Provider-health model (design)

Minimal `ProviderHealth` (design): `{provider_id, capability_id?, state, checked_at, detail?}`
with `state ∈ {available, unavailable, degraded, unsupported}`.

- `available` = provider boundary reachable **and** the requested capability is
  supplied. **Does NOT imply** authorization, executability, success, or verification.
- `unsupported` = capability not supplied.
- Health is **read-only** and **side-effect-free**; no execution.
- If health cannot be established safely: `UNKNOWN / NOT VERIFIED`.
**VERIFIED FROM SOURCE (invariant) + design.**

## 11. Decepticon adapter boundary (design)

```
RAPHAEL Capability Fabric (unchanged; resolution only)
  → ActionRequest
  → ProviderRuntime
  → Decepticon Adapter        (translation/invocation/normalization ONLY)
  → Decepticon external (sandbox daemon / SDK services)
```

- The adapter maps a **closed capability id** to a **closed, named** operation.
- **Raw `/execute_tmux` is NOT an acceptable direct capability surface** — it is
  generic command execution and would violate the "no unrestricted host/network"
  rule. **VERIFIED FROM SOURCE + policy.**
- The adapter must not own orchestration, replanning, finding lifecycle,
  verification, falsification, gate, or broad target authorization.

## 12. T3MP3ST adapter boundary (design)

```
RAPHAEL Capability Fabric (unchanged)
  → ActionRequest
  → ProviderRuntime
  → T3MP3ST Adapter          (translation/invocation/normalization ONLY)
  → T3MP3ST external (MCP server / gated Arsenal / HTTP API)
```

- Closest usable boundary: **MCP `security_recon`** or a **single gated
  `Arsenal.execute` read-only tool**.
- **`Tempest` / `MissionControl` / `AgentLoop` / operator-cell semantics must not
  be imported into RAPHAEL authority.** **VERIFIED FROM SOURCE + policy.**

## 13. First-proof capability design — `C1 static_file_manifest`

Design selection only (nothing executed).

| Aspect | Design |
|---|---|
| capability ID | `static_file_manifest` |
| target shape | a path **inside an approved workspace root** (e.g. `src/`) |
| scope shape | `filesystem_permission=workspace_read`, `filesystem_roots=[<workspace>]`, `network_permission=denied`, `exclusions=[]` |
| expected ActionRequest | `Capability` must be mapped by a **new** closed capability id (not the native enum until a future contract change); `target="src/"`; bounded `purpose`; `timeout_seconds` small |
| expected ProviderResult | `status=success`, `output={entries:[...], truncated:false}`, `artifacts=[]`, full `provenance`, `scope_echo` echoing read-only/no-network |
| expected normalized evidence | one observation `ledger.append_evidence(producer="provider:<id>", payload={capability_id, operation_id, entries_count, sha256s?})`; one `ExecutionResult` |
| expected timeout behavior | if exceeded → `status=timeout`, `timeout.exceeded=true`, no claim of completion |
| expected denial behavior | target outside scope → `status=denied`, `error.category=scope_denied`, **no execution** |
| expected unavailable behavior | provider boundary unreachable → `status=unavailable` |
| expected provenance chain | run_id → action_request_id → operation_id → evidence_id |
| expected RAPHAEL verification boundary | none automatic; any *finding-shaped* output remains an **observation** and must pass RAPHAEL Verifier/Falsifier to become a finding |
| provider candidate | **Decepticon (sandbox read)** or **T3MP3ST (read-only Arsenal tool)** — choose at Phase 2C |
| why lowest risk | read-only, non-networked, bounded, deterministic, not generic exec |

**VERIFIED FROM SOURCE (provider facts) + INFERRED (design selection).**

## 14. Rejected designs

| Rejected design | Reason |
|---|---|
| In-process provider execution | shared-process coupling, no isolation, weak provenance |
| Generic subprocess execution | violates "no unrestricted host access"; generic exec surface |
| Unrestricted Decepticon `/execute_tmux` exposure | generic command execution; NOT SUITABLE |
| Unrestricted T3MP3ST Arsenal exposure | 36–111 offensive tools; NOT SUITABLE |
| Importing provider findings as RAPHAEL findings | violates finding lifecycle authority |
| Provider-owned verification | violates "PROVIDER SUCCESS ≠ VERIFIED FINDING" |
| Provider-owned authorization | violates Policy authority |
| Provider-owned Quality Gate | violates sole COMPLETE authority |
| CLI-only integration as the long-term boundary | weak provenance/contract; acceptable only as a read-only stopgap (D) |
| Embedding provider orchestration inside RAPHAEL Planner | authority inversion |

**VERIFIED FROM SOURCE (invariants) + design.**

## 15. Open questions / UNKNOWNs

- T3MP3ST code-level cancellation guarantees — **UNKNOWN / NOT VERIFIED**.
- Decepticon `/execute_tmux` timeout/auto-background internals; `DaemonSandbox`
  cancellation; KG write path — **UNKNOWN / NOT VERIFIED**.
- Whether either provider can be constrained to a **single bounded action** in
  practice — **UNKNOWN** (Phase 2A: `ADAPTER REQUIRES INTERNAL ORCHESTRATION`).
- Exact MCP `security_recon` schema; `ApprovalController` contract — **UNKNOWN**.
- New RAPHAEL capability-id representation (beyond the native enum) — **BLOCKED**
  on an approved contract change.
- Licence/Apache-2.0 vs AGPL-3.0 integration implications — **REQUIRES LEGAL REVIEW**.

## 16. Preconditions for Phase 2C (implementation)

1. Approved closed capability allow-list (proposed: C1 first).
2. Approved `ScopeHandoff` schema.
3. Approved `ProviderRuntime.invoke` contract.
4. Approved `ProviderResult` contract + status enum.
5. Approved normalization semantics (observation-only).
6. Approved timeout/cancellation semantics (honest, no assumed guarantees).
7. Approved provider-health semantics.
8. Approved provenance requirements.
9. First-proof provider + capability selected.
10. Isolation boundary selected (container + HTTP/MCP).
11. Security/legal concerns explicitly recorded (incl. **REQUIRES LEGAL REVIEW**).
12. New-capability/contract-change design approved (no native enum change without one).

## 17. Explicit STOP condition

**STOP.** This is design only. No adapters, no `ProviderRuntime` implementation,
no provider invocation, no changes to Fabric/Runtime/Broker/Policy/FindingStore/
Verifier/Falsifier/Replanner/Gate/UI, no dependencies. Phase 2C requires separate
authorization. **VERIFIED FROM SOURCE (this document).**

---

## Appendix — contract sketches (non-normative)

```text
ScopeHandoff:  schema_version, authorization_token, run_id, action_request_id,
               provider_id, capability_id, target_identity, target_scope[],
               exclusions[], allowed_resource_classes[], network_permission,
               network_allow_hosts[], filesystem_permission, filesystem_roots[],
               data_handling_constraints[], max_duration_ms, cancellation_mode,
               artifact_constraints{}, output_size_limit_bytes, provenance_required[]

ProviderResult: schema_version, provider_id, operation_id, action_request_id,
                run_id, capability_id, status, output, artifacts[], error{},
                started_at, completed_at, duration_ms, execution_metadata{},
                provenance{}, timeout{}, cancellation{}, scope_echo{}

status ∈ {success, failure, timeout, denied, unavailable, partial, cancelled}
```
