# D17 Adversarial Hardening Audit: the complete autonomous loop (D12.2-D16)

Status: audit document. It changes no code, grants no capability, and touches no frozen seam. It records what the adversarial review of the autonomous loop examined, what is blocked by landed code with passing tests, and what remains as documented residuals.

Scope note: this document describes a **generic governed autonomous security-assessment agent for authorized/CTF targets**. It does not describe a fully autonomous hacker. No new offensive capability is added here, and none is claimed.

Related: `docs/D16_AUTONOMOUS_VERIFICATION_REPLANNING.md` (the loop semantics this audits), `docs/D15_CAPABILITY_EXPANSION.md` (two-tier model and Barrier B target), `docs/D13_CAPABILITY_FABRIC.md` (fabric), `docs/PROVENANCE.md` (attribution).

## 0. Audit basis and a note on ORACLE findings

Every blocking claim below cites the landed module and the passing test that pins it. Where a claim rests on code reading rather than a fresh test run, it says so.

A search of `docs/` for D17 or ORACLE material found no dedicated D17 ORACLE findings artifact in this checkout (no `docs/D17*` file exists; the only D17 pointers are the handoff in D16 sections 11 and 12). So the audit basis is the landed code in `raphael_ibm_bob/` plus the D16 claim inventory (D16 section 10) and the D15 executability matrix (D15 section 8.5). No ORACLE verdict is invented here. If a separate ORACLE review lands later, its findings should be appended in section 8 and any residual below that it closes should be struck with the test command that closed it.

Provenance of the read: `raphael_ibm_bob/d16_autonomous.py`, `d14_loop.py`, `d14_stop.py`, `d14_planner.py`, `d14_world_state.py`, `d14_state_codec.py`, `d14_ledger_view.py`, `d14_replan.py`, `d15_observation.py`, `d15_capability_catalogue.py`, `observation_model.py`, `credential_provenance.py`, `capability_prerequisites.py`, `broker.py`, `policy.py`, `quality_gate.py`, `c1a_authorization.py`, plus `tests/test_d16_replanning_semantics.py`, `tests/test_d16_autonomous_loop.py`, `tests/test_d14_autonomy.py`, `tests/test_d14_autonomous_episode.py`, `tests/test_d15_capability_catalogue.py`, and `tests/test_d15_executability_matrix.py`.

## 1. Scope: what was audited

The complete autonomous loop as landed from D12.2 through D16:

```text
select -> execute -> observe -> update -> verify/falsify -> replan -> stop
```

| Layer | Landed authority | Audited for |
|---|---|---|
| `SELECT` | `d14_planner.py` (`Planner.plan`) | Deterministic, non-executing proposal; no target-name branching |
| `REQUEST` / `EXECUTE` | `runtime.py` → `broker.py` → `policy.py` | The only execution path; mediation inviolability |
| `OBSERVE` | `observation_model.py` + `d15_observation.py` + `d14_state_codec.py` (`EvidenceBinding`, `ExecutionBinding`) | Bounded normalized observations bound to one ALLOWed execution |
| `UPDATE_WORLD` | `d14_world_state.py` (`reduce_world_state`, `reduce_state_transition`) | Pure fold gated on ALLOW, success, session, freshness, seq binding |
| `VERIFY` / `FALSIFY` | `verifier.py`, `falsifier.py`, `finding.py` | Broker-mediated transitions only on observed evidence |
| `REPLAN` | `d14_replan.py` (`ReplanDecision`); finding-level `replanner.py` | State-driven reselect vs refutation-driven Plan B (see residual R2) |
| `COORDINATE` | `d16_autonomous.py` (`AutonomousLoop`) | No direct execution, no verdict construction |
| `STOP` | `d14_stop.py` (`evaluate`, `StopCondition`) | Pure, side-effect-free, first-match-wins termination |
| Verdict | `quality_gate.py` (`BOBQualityGate.evaluate`, conditions A-G) | Sole COMPLETE authority |
| Vocabulary | `d14_loop.py` (`AutonomyState`) | Phase names only, never completion verdicts |
| Selection substrate | `capability_registry.py`, `capability_selector.py`, `capability_prerequisites.py`, `target_service_model.py`, `credential_provenance.py` | Proposal only; prerequisites tri-state and fail-closed |

Out of scope (not audited here, not claimed): the legacy offensive substrate in `src/`, `arena/`, `cli/`, `evaluations/`, and related residue. It is not imported by the governed runtime and not shipped in the product package. Live targets, Breakout/VulnHub execution, and multi-scenario generality are also out of scope and unchanged from the README limits.

## 2. Attack classes examined: BLOCKED

Each row names the attack, the landed defense, and the test that pins it. All episodes below use synthetic targets on the governed seams.

### 2.1 Ungoverned capability execution (Tier-1 SSH, SMB, TLS, DNS, banner)

Blocked at three independent layers. `InertAdapter.execute` raises `AdapterNotBoundError` (`capability_bootstrap.py:35-47`). `plan_to_action_requests` raises `ValueError` for any step id with no `contracts.Capability` enum member, so no `ActionRequest` can even be built. The Policy allow-list holds only existing enum members, so a hand-built request dies with `capability-not-allowed`. Pinned by `tests/test_d15_executability_matrix.py` (6 tests; Ran 12 OK with the catalogue suite) and the D16 refusal test (`test_ungovernable_action_is_refused_before_observation`), which asserts `Decision.DENY` on the hand-built SSH request.

### 2.2 Execution outside Broker mediation

Blocked by construction. The planner, the world-state reducer, the stop evaluator, and `ReplanDecision` import no broker, runtime, or policy execution path and perform no invocation (D16 section 9). `AutonomousLoop.submit_next` submits only through the injected `RuntimeBoundary.submit` (`d16_autonomous.py:102-108`); `propose` returns a proposal without authorization or execution. `MediatedAdapter` builds an ordinary `ActionRequest` and calls `runtime.submit`; it never sees the ledger, never consults Policy, and never executes directly (D15 section 5).

### 2.3 Folding a DENY, a failure, or a sessionless result as an observation

Blocked in `_validate_ingestion` (`d14_world_state.py:278-302`). The update's `evidence_id` is mandatory and must resolve through the read-only ledger view to a decision record plus a result record for the same `request_seq`. `policy_decision` must read `allow` (case-insensitive) and `result_success` must be true, or the fold raises and the state is untouched. Empty session bindings are rejected before any fold. The stricter `reduce_state_transition` path additionally requires a D16 `ExecutionBinding` and cross-checks `evidence_id`, `source_seq` against `result_seq`, `request_seq`, `decision_seq`, session, and capability (lines 228-250).

### 2.4 Cross-session or stale observation injection (the generalized D12 stale-prompt fix)

Blocked by `ProvenanceValidator.validate_fresh` (`observation_model.py:105-115`): the observation's `provenance["session_id"]` must equal the binding's session id (mismatch rejects cross-session observations), and `time.time() - timestamp` must sit within 300 seconds. The canonical state hash deliberately excludes `timestamp` and `discovered_at` (`d14_state_codec.py:318-329`), so determinism and freshness do not fight each other. Freshness is enforced by the validator, not the hash.

### 2.5 Duplicate or replayed observations

Blocked by `applied_observation_ids`: re-ingestion of a known `observation_id` returns the prior snapshot unchanged (`d14_world_state.py:178-179`), a case the first D16 test pins. On the `reduce_state_transition` path, a `source_seq` that is not newer than `last_source_seq` raises `StaleObservationError`. The C1A authorization binding separately seals its identity fields with HMAC-SHA256 and treats invocation ids as single-use (`c1a_authorization.py:1-18`).

### 2.6 Evidence/binding mismatch (right session, wrong execution)

Blocked by the seq-level cross-checks in `reduce_state_transition` and `associate_observation` (`d15_observation.py:151-198`): observation session must match the runtime session binding, observation capability must match the governed execution (case-insensitive), the observation must carry normalized metadata, and a conflicting pre-existing execution association is rejected. A verification result that names the wrong observation, omits the observation's evidence id, or cites untrusted evidence is rejected by `AutonomousLoop._validate_verification` (`d16_autonomous.py:131-139`).

### 2.7 Verification or falsification without evidence

Blocked in both engines and the coordinator. `VerificationResult` cannot exist with empty `evidence_ids` (`d16_autonomous.py:35-40`). The verifier promotes `UNVERIFIED` to `VERIFIED` only on positive retest evidence through the runtime, and stays put on DENY, failed execution, or output mismatch. The falsifier demotes `VERIFIED` to `REFUTED` only on a real observed counter-example (`predicate` first, else `forbidden_substring`, else no counter-example); absence of a counter-example is not proof. Denial or failure leaves state unchanged and stays durable in the ledger (D16 section 3).

### 2.8 Forged completion

Blocked structurally. Only `BOBQualityGate.evaluate` may emit `COMPLETE`, against ledger-backed conditions A-G with causal binding (`_causally_bound`: probe and regression records must tie to an ALLOWed successful execution, `quality_gate.py:208-228`). `AutonomousLoop` constructs `ReplanDecision` descriptors and `SelectionDecision`s only. `AutonomyState` phase names are vocabulary, never verdicts. D16 pins the terminal-before-replan case: on `GateVerdict.COMPLETE`, the coordinator stops with `ReplanDecision(should_replan=False, reason="terminal_state", next_action=None)` and carries no replacement action.

### 2.9 Unbounded looping

Blocked by the pure stop evaluator (`d14_stop.py:79-97`), checked before any replan, first match wins. See section 5 for the full guarantee table.

### 2.10 Credential exfiltration through evidence

Blocked by the vault discipline (`credential_provenance.py:1-18`). Plaintext lives only in the process-local vault, `to_evidence_dict` serializes everything except plaintext, and `is_authorized_for` is an exact per-target per-protocol check that fails closed. Unknown prerequisite kinds return false, never an exception that could be misread as permission.

### 2.11 Raw protocol bytes, banners, or secrets smuggled in as observations

Blocked by the D15 normalized builders. No builder accepts raw protocol output, credentials, configuration values, or file contents. Text is capped at 128 chars, lists at 32 items, counts at 1,000,000, ports range-checked; references must match a bounded safe pattern; banners are stored as hashes, never raw text (`d15_observation.py:36-107, 277-288`). Family observation types stay separate and are never merged into one generic blob.

### 2.12 Target-name branching or scenario-specific selection

Blocked by construction. There is no `if target == X` in the selection path. Discovery matches descriptor protocols against open services in `TargetFacts`; ordering is the frozen `_selection_order_key` over lifecycle priority, confidence, hypothesis id, capability id, and canonical params (`d14_planner.py:271-280`). The D16 difference proof holds mission and target constant while the hash delta binds to the new observation (D16 section 5).

## 3. Provenance and session binding model

Identity flows one way, from the governed boundary outward. The Broker stamps dense ledger sequences per request. The C1A authorization binding seals the authoritative execution identity (`run_id`, `mission_id`, `decision_seq`, `request_seq`, `invocation_id`, `proof_session_id`, `lifecycle_id`, `sandbox_id`, `capability_id`, `provider_id`, `target`, `fixture_path`) with HMAC-SHA256 over one canonical serialization shared by creation and verification. `ExecutionBinding.from_runtime_result` (`d14_state_codec.py:72-125`) ties one observation receipt to one ALLOWed, successful, sequenced execution plus an `AuthoritativeSessionBinding` issued by the governed runtime. `associate_observation` attaches that link to the normalized observation under `provenance["execution_binding"]` with a deterministic `D16-` observation id. Ingestion (`_validate_ingestion`) then demands ALLOW plus success plus a non-empty session plus session match plus 300-second freshness, with command binding available where a command applies (`validate_command_binding` ties output to the exact command, not a buffer or prompt).

## 4. The binding limit (residual R1, the central honesty point)

The model above binds **execution identity**, not **observation content**. Nothing in the landed code cryptographically ties an observation's `content_hash` or its normalized metadata payload to the bytes the bound execution actually produced. Concretely: an adapter that holds a valid ALLOW binding for request R could submit plausible but false normalized content under R's session and seqs, and `reduce_world_state` would fold it, because the checks compare ids, seqs, sessions, and capability names, never content against output.

This does not block release, and here is why. Adapters are trusted code inside the boundary, not remote principals; the threat is a bug or a compromised adapter, not a normal caller. Four landed layers blunt that threat: observations are bounded and normalized (hashes, caps, no raw bytes, per-family types), so a lying adapter cannot smuggle arbitrary content; verification and falsification retest through independent broker-mediated executions rather than trusting the first observation; finding transitions persist `FindingRecord`s with evidence seqs and the finding-level replanner rejects cross-finding diagnostics and authority keys; and the QualityGate demands causally bound probe, regression, and test evidence before `COMPLETE`, so one false observation cannot by itself complete a mission. Content binding (sealing `content_hash` into the execution binding at the mediator, verified at ingestion) is D18 work. It is recorded as D18 item 1, not claimed as done.

## 5. Stop-condition guarantees

`evaluate(world_state, last_runtime_result, gate_evaluation, config)` is pure and side-effect-free. Order is fixed; the first match wins:

| Order | Condition | Trigger | Default | Provenance |
|---|---|---|---|---|
| 1 | `MISSION_COMPLETE` | Gate evaluation is `GateVerdict.COMPLETE` | n/a | `quality_gate.py` A-G |
| 2 | `POLICY_DENIAL` | Last result carries `Decision.DENY` | n/a | Broker decision |
| 3 | `NO_APPLICABLE_CAPABILITY` | Rationale holds `NO_APPLICABLE_CAPABILITY` with `next_action is None` | n/a | Planner outcome |
| 4 | `MAX_STEPS` | `step_count >= max_steps` | 5 | `harness/loop.py:113-128` |
| 5 | `MAX_REPLANS` | `replan_count >= max_replans` | 1 | `runner.py:170-214` |
| 6 | `MAX_FAILURES` | `failure_count >= max_failures` | 5 | New, not yet ratified |
| 7 | `NO_PROGRESS` | Last `no_progress_window` states share one `(hash, token)` | 3 | New, not yet ratified |
| 8 | `CONFIDENCE_THRESHOLD` | Result `confidence_bps >= threshold` | 2000 | New, not yet ratified |

Guarantees that hold today: completion always wins over replanning (D16 terminal test); denial stops before any observation exists (the refusal test asserts `observations == ()`); the coordinator persists nothing itself, stop and finalize payloads are built but never persisted by D14 (`d14_stop.py:100-130`), and the outer coordinator owns persistence; the gate stays the sole completion authority above all stops. Rows 6-8 are implemented with fail-closed defaults but are flagged not-yet-ratified in code (`d14_stop.py:14-19`); D16 exercises none of them directly. That is residual R3, and it does not block release because rows 1-5, all pinned by passing tests, already bound every landed episode.

## 6. Security boundary: what did not change

Policy, Broker, and QualityGate semantics are byte-identical in behavior to before the D13-D16 work (D15 section 2). Concretely unchanged: Policy authorization stays an explicit deterministic ALLOW/DENY with string reasons, and DENY performs nothing; the Broker stays the sole invoker with the canonical request, decision, policy receipt, result, execution receipt chain; scope matching stays exact host, port, and protocol against the mission-bound `TargetProfile`, plus method and command allow-lists and positive timeouts; evidence stays producer-tagged, append-only, digest-identified, with provider and network output marked untrusted; verification and falsification stay independent retest and counter-example search, with no binding meaning no verified findings; only `BOBQualityGate.evaluate` emits `COMPLETE`; the finding lifecycle stays `UNVERIFIED` to `VERIFIED` or `REFUTED`, `VERIFIED` to `REFUTED` or `SUPERSEDED`, `REFUTED` to `SUPERSEDED`, with `UNVERIFIED` to `SUPERSEDED` rejected and replan evidence required after refutation. Fail-closed rules carried forward: unregistered means refusal, descriptor-only means `AdapterNotBoundError`, and there is no generic just-run-it adapter. Barrier B (the registry-backed generic bridge in D15 section 8) is a target design, not landed code; until its generic consult, dispatch, and expectation paths land with tests, the five-touchpoint promotion rule still governs and any layer disagreement resolves to DENY.

## 7. Documented residuals (none blocking release)

R1. **Observation content is not bound to the bound execution's evidence.** Stated fully in section 4. Mitigated in depth; fix is D18 item 1.

R2. **State-driven reselect is proven; end-to-end refutation closure in the autonomous rig is not.** The `ReplanDecision(reason="observation_changed_state")` path is pinned by passing tests, but `VERIFIED` to `REFUTED` (falsifier with a synthetic counter-example) into `Replanner.replan` into re-execution with `parent_plan_id` linkage and a `producer="replanner"` receipt inside a multi-step episode is D16 section 11 item 1 and remains open. Not blocking: the finding-level path is landed and covered by the M5/M9 suites; the autonomous rig correctly scopes itself to reselect and documents the Plan B path for handoff rather than invoking it.

R3. **Single-observation episode; unratified bounds unexercised.** Only one fold (A to B) is demonstrated in the D16 module; multi-step chains, `conflicted` banding, failure-kind folds, and `NO_PROGRESS` over the D16 rig are unexercised, and `MAX_FAILURES`, `NO_PROGRESS_WINDOW`, and `CONFIDENCE_THRESHOLD_BPS` are implemented but not yet ratified. Not blocking: rows 1-5 of the stop table are pinned and bound every landed episode; the unratified rows ship as fail-closed defaults.

R4. **D16 folds through a stub ledger view.** The D16 module uses an `_AllowedLedger` stub, not a persisted `EvidenceLedger`; real-seam ingestion is covered only by the adjacent D14 episode test. Not blocking: the adjacent episode (`tests/test_d14_autonomous_episode.py`, Ran 1 OK) proves the seam wiring with a real runtime, and the stub is test-scoped.

R5. **Discovery trusts protocol labels.** `discover_for_target` matches descriptor protocols against target facts, so a mislabeled service proposes the wrong family. Not blocking: selection is a proposal only and Policy still gates execution, but D18 should treat protocol strings as untrusted input (D15 section 7 item 5).

R6. **Barrier B is design, not code.** Policy, Broker, and QualityGate still branch on capability names. Not blocking: documented as intent, and the partial-change case is defined as a defect that fails closed.

R7. **Credential fingerprint and wipe limits.** The fingerprint is the full SHA-256 of the secret, a correlation handle that must never be treated as proof of possession, and short secrets could be brute-forced from a ledger copy; `wipe()` drops references without overwriting allocator memory. Not blocking: both limits are stated in the module itself, no plaintext reaches the ledger, and the vault is process-local.

R8. **No live target; synthetic hosts only.** The D16 module opens no socket, and Breakout/VulnHub scope limits in the README are unchanged. Not blocking: a scope statement, not a security hole, and it constrains what any hardening claim may borrow.

R9. **No D17 ORACLE findings artifact in this checkout.** Recorded in section 0. Not blocking for this document because the audit rests on landed code and passing tests, but any future ORACLE review should be appended and should close residuals explicitly rather than by implication.

## 8. ORACLE findings log

Empty at the time of writing. No D17 ORACLE findings file was found in this checkout (see section 0). Append entries here with the finding text, the affected module and lines, the disposition (blocked or residual), and the test command that pins the fix.

## 9. D18 handoff

No code is changed by this document. Suggested D18 scope, in priority order:

1. **Bind observation content to execution evidence.** Seal `content_hash` (and the canonical normalized payload) into the execution binding at the mediator and verify it at ingestion, so a valid ALLOW binding cannot carry false content. Pin with a test that mutates content under a valid binding and asserts rejection.
2. **Close the refutation loop in the autonomous rig** (D16 section 12 item 1): drive `VERIFIED` to `REFUTED` into `Replanner.replan` into re-execution, asserting Plan B linkage and the replanner receipt inside a multi-step episode, reusing `replan_count` and `MAX_REPLANS=1` accounting.
3. **Multi-fold episode with conflict** (D16 section 12 item 2): extend the rig to A to B to C with a conflicting third observation; assert `conflicted` banding and `NO_PROGRESS` / `NO_APPLICABLE_CAPABILITY` termination.
4. **Real-ledger D16** (D16 section 12 item 3): replace the stub ledger view with `EvidenceLedgerView` over a temp `EvidenceLedger` so the ALLOW binding is persisted, not stubbed.
5. **Ratify or remove the three unratified bounds** (D16 section 12 items 4-5, this doc R3): decide `MAX_FAILURES`, `NO_PROGRESS_WINDOW`, and `CONFIDENCE_THRESHOLD_BPS` plus hypothesis-band dynamics, and pin `_selection_order_key` behavior with a dedicated test either way.
6. **Gate closure on the ledger** (D16 section 12 item 5): run the episode to `BOBQualityGate.evaluate` and assert condition G (refuted-followed-by-replan) green.
7. **Treat protocol labels as untrusted input** in discovery (this doc R5; D15 section 7 item 5), and land Barrier B's generic consult/dispatch/expectation paths with matrix tests before any Tier-1 promotion (D15 section 8).

Constraints carried forward: modify no frozen D14/D15 seam semantics; add no new offensive capabilities; no target-name branching; no fully-autonomous-hacker framing (this stays a generic governed autonomous security-assessment agent for authorized/CTF targets); every new claim ships with its passing test command in a claim inventory.
