# Raphael IBM BOB: Final Release (D18)

**Product description:** Generic governed autonomous security-assessment agent for authorized/CTF targets.

**Release status:** documentation closeout. This file changes no code, grants no capability, and touches no frozen seam. It records what shipped in `raphael_ibm_bob/`, how the pieces fit, what is proven by passing tests, and what remains open.

**Related docs:** `docs/D13_CAPABILITY_FABRIC.md`, `docs/D15_CAPABILITY_EXPANSION.md`, `docs/D15_D16_HANDOFF.json`, `docs/D16_AUTONOMOUS_VERIFICATION_REPLANNING.md`, `docs/D17_ADVERSARIAL_HARDENING.md`, `docs/PROVENANCE.md`, `CANONICAL_DEMO.md`, `docs/HACKATHON_DEMO.md`.

**Scope note:** everything below describes governed assessment of authorized or CTF targets. It adds no offensive capability, and no claim here depends on target-name branching.

---

## 1. Architecture

The system is a governed agentic loop. A mission enters, a plan comes out as a proposal, and every step crosses the same mediated boundary before it can run. The picture, in one line:

```text
Mission -> Plan A -> Runtime -> Broker -> Policy -> Evidence -> Finding
-> Verification -> Falsification -> Refutation -> Replanning
-> Plan B / Plan C -> Independent verification -> QualityGate
-> COMPLETE / REFUSE
```

Landed modules (all under `raphael_ibm_bob/`):

| Layer | Module | Job |
|---|---|---|
| Contracts | `contracts.py` | Shared types: `ActionRequest`, `Decision`, `GateVerdict`, findings |
| Policy | `policy.py` | Fail-closed ALLOW/DENY with string reasons; allow-list plus scope, method, and command checks |
| Broker | `broker.py` | Sole invocation gateway (`execute_capability`); stamps dense sequence numbers; persists the evidence chain |
| Runtime | `runtime.py` | Submits requests into Broker; returns `RuntimeResult` |
| Evidence | `evidence_ledger.py` | Append-only JSONL ledger, SHA-256 digests, causal order preserved |
| Findings | `finding.py` | Sole transition authority for the finding lifecycle |
| Verifier | `verifier.py` | Broker-mediated retest of candidate findings |
| Falsifier | `falsifier.py` | Broker-mediated counter-example search with independent probes |
| Replanner | `replanner.py` | Derives Plan B from REFUTED findings with parent linkage |
| Planner | `d14_planner.py` | Deterministic next-action proposal from `WorldState`; proposes, never executes |
| World state | `d14_world_state.py` | Pure fold (`reduce_world_state`) of one governed observation into a new immutable snapshot |
| Stop | `d14_stop.py` | Pure, side-effect-free stop evaluator; first match wins |
| Coordinator | `d16_autonomous.py` | `AutonomousLoop`: propose, submit, ingest, replan, stop; no direct execution, no verdict construction |
| Verdict | `quality_gate.py` | `BOBQualityGate.evaluate()`, the sole COMPLETE authority (conditions A to G) |
| Fabric | `capability_registry.py`, `capability_selector.py`, `capability_bootstrap.py`, `capability_fabric.py` | Declaration index, fact-driven selection, mediated adapters |
| Observations | `observation_model.py`, `d15_observation.py`, `d14_state_codec.py` | Normalized bounded observations plus execution bindings |

Historical note: `docs/Architecture.md` describes the older v2.0 offensive-research substrate (`src/orchestrator`, D/S/E series). That tree stays in the checkout as residue. It is not imported by the governed runtime and it is not shipped (the package builds from `raphael_ibm_bob` alone). When this release doc says "architecture," it means the table above.

---

## 2. The governance boundary

Five pieces hold the line. None of them trusts the others' word; each checks the ledger.

### 2.1 Policy authorization

`BOBPolicy` (`policy.py`) is fail-closed. The allow-list holds explicit enum members only (`READ`, `LIST`, `SEARCH`, `WRITE`, `RUN_TEST`, `C1A_STATIC_FILE_INSPECT`, plus the network executables `NETWORK_HTTP_REQUEST` and `NETWORK_TELNET_SESSION`). It enforces workspace path containment, mission-scope containment via canonical resolution (`c1a_scope.py`), and per-capability invariants (for example, `RUN_TEST` only matches `test_*.py` or `*_test.py`; HTTP is GET/HEAD only; Telnet carries a command allow-list). ALLOW is an explicit deterministic decision with a string reason tests can assert. DENY performs nothing.

### 2.2 Broker mediation

`BOBBroker` (`broker.py`) is the sole gateway to capability invocation. Every caller (Runtime, Planner, Verifier, Falsifier, Replanner) goes through it. Each request is stamped with dense sequence numbers, validated through Policy, and persisted. There is no side channel around it: the planner, the world-state reducer, the stop evaluator, and `ReplanDecision` import no execution path and perform no invocation.

### 2.3 Evidence trust

`EvidenceLedger` (`evidence_ledger.py`) records immutable JSONL with SHA-256 digests in strict causal order:

```text
RequestRecord -> DecisionRecord -> PolicyEvidenceReceipt -> ResultRecord -> ExecutionEvidenceReceipt
```

Provider and network output is tagged `provider_untrusted: True`. A scan result, however successful, is untrusted evidence, never an authoritative finding. Single-use HMAC-SHA256 authorization tokens (`c1a_authorization.py`) seal the full execution identity, so field mutation, replay, or foreign identity fails closed. Every run writes an isolated `runs/<run_id>/{evidence.jsonl,artifacts/}` directory.

### 2.4 QualityGate, the sole COMPLETE

Only `BOBQualityGate.evaluate()` (`quality_gate.py`) may emit `COMPLETE`, and only against seven ledger-backed conditions:

- **A (Mission criterion):** non-empty mission criteria.
- **B (Required tests):** required test pass backed by an artifact proving `returncode == 0`.
- **C (Regression breadth):** full regression backed by 2 or more distinct ALLOWed capability actions.
- **D (Independent probe):** independent behavior probe passes, backed by probe evidence.
- **E (Scope):** all targets inside workspace and declared mission scope.
- **F (Evidence):** complete request, decision, result, and evidence chain.
- **G (Finding state):** no unresolved UNVERIFIED findings; every REFUTED finding followed by replan evidence.

Any condition failing, or any evidence missing, yields REFUSE. Every `evaluate()` call writes a `GateRecord`, so the verdict is reconstructible. Fabricated bools do not pass: `behavior_probe_ok` and `regression_ok` must each tie to a real `producer="probe"` or `producer="regression"` record with causal binding to an ALLOWed successful execution.

### 2.5 Finding lifecycle

`FindingStore` (`finding.py`) owns every transition:

```text
UNVERIFIED -> VERIFIED | REFUTED
VERIFIED   -> REFUTED | SUPERSEDED
REFUTED    -> SUPERSEDED
SUPERSEDED -> (terminal)
```

`UNVERIFIED -> SUPERSEDED` is rejected outright. Registration requires `UNVERIFIED`. Each transition persists a `FindingRecord` before in-memory publication. Verification promotes only on positive broker-mediated retest evidence; falsification demotes only on a real observed counter-example (`predicate` first, else `forbidden_substring`, else no counter-example). Absence of a counter-example proves nothing. Denial or failure leaves state unchanged and stays durable in the ledger.

---

## 3. The capability fabric (D13 plus D15)

### 3.1 D13: the governed fabric

D13 (`docs/D13_CAPABILITY_FABRIC.md`) added declaration, discovery, and selection around the frozen core without changing it. The fabric answers "which provider can supply this capability" and prepares ordinary `ActionRequest`s. It never authorizes and never executes.

Key types: `CapabilityDescriptor` (immutable record: id, protocol, prerequisites frozenset, authorization scope, evidence schema, execution adapter path, verifier/falsifier bindings, mission types frozenset, schema version), `CapabilityRegistry` (sole index; duplicates rejected; registration at init, never mid-mission), `PrerequisiteEngine` (tri-state answers: ready, missing, unknown; unknown kinds fail closed), `CapabilitySelector` (facts-only selection into an `ExecutionPlan`, a proposal, not a grant), `TargetFacts`/`ServiceRecord` (downstream code consumes facts, never raw scan output; no branch keys off a target name), `ObservationRecord`/`ProvenanceValidator` (session match plus 300-second freshness; command binding where a command applies), and `CredentialVault` (process-local; plaintext never reaches the ledger; exact per-target per-protocol authorization).

Two adapter shapes carry the discipline: `MediatedAdapter` builds an ordinary request and calls `runtime.submit` (it never sees the ledger, never consults Policy, never touches the network directly), while `InertAdapter.execute` raises `AdapterNotBoundError` by design.

### 3.2 D15: the two-tier model and the generic registry/adapter

D15 (`docs/D15_CAPABILITY_EXPANSION.md`) split capabilities into two tiers with a hard rule between them: declaration is not execution.

**Tier 1 (descriptor-only).** Five capabilities exist as immutable descriptors plus an `InertAdapter` binding: `NETWORK_SSH_SESSION`, `NETWORK_SMB_METADATA`, `NETWORK_TLS_METADATA`, `NETWORK_DNS_METADATA`, `NETWORK_GENERIC_SERVICE_BANNER`. They are discoverable and composable, but every execution path fails closed at three layers: `InertAdapter.execute` raises, `plan_to_action_requests` raises `ValueError` (no enum binding, so no request can even be built), and Policy denies any hand-built request with `capability-not-allowed`.

**Tier 2 (executable).** The existing executables are unchanged: `C1A_STATIC_FILE_INSPECT`, `NETWORK_HTTP_REQUEST`, `NETWORK_TELNET_SESSION`. Promoting any Tier-1 entry to Tier 2 needs an enumerated, approved interface change across all five touchpoints (enum, Policy, Broker, skill/registry declarations, QualityGate expectations). A partial change is a defect, not a promotion, and the remaining layers keep it inert.

**Barrier B (target design, not landed code).** D15 section 8 sketches the generic bridge: Policy reads authorization metadata off the descriptor, the Broker dispatches to the bound adapter, and the QualityGate evaluates descriptor-declared expectations through the unchanged A to G conditions. Until that lands with tests, the five-touchpoint rule still governs and any layer disagreement resolves to DENY. The executability matrix (`tests/test_d15_executability_matrix.py`) pins today's truth: HTTP and Telnet execute through governed paths with ledger evidence; the other five refuse at every layer.

Frozen invariants D15/D16 carry forward: per-family observation types (never one merged blob), broker-stamped session identity checked by `ProvenanceValidator.validate_fresh`, adapters never receiving the ledger, tri-state prerequisites, and ranking by `hypothesis_id` only through the frozen `_selection_order_key`.

---

## 4. The autonomous loop (D14 planner/world-state plus D16 verification/replanning)

D14 laid the seams; D16 (`docs/D16_AUTONOMOUS_VERIFICATION_REPLANNING.md`) proved the semantics with passing deterministic tests. The loop vocabulary is:

```text
select -> execute -> observe -> update -> replan
```

with verify/falsify, stop, and gate around it. `AutonomousLoop` (`d16_autonomous.py`) coordinates without invoking: `propose()` returns a planner proposal (no authorization, no execution), `submit_next()` submits through the injected `RuntimeBoundary`, and `ingest()` folds trusted evidence, folds in the verification outcome, checks stop first, then replans. It constructs `ReplanDecision` descriptors and `SelectionDecision`s only. It never builds a verdict.

World state (`d14_world_state.py`) is immutable: mission, target, revision, deep-copied facts, endpoint bands (`unknown | candidate | confirmed | refuted | conflicted`), hypotheses, observations, applied ids, sequence cursor, counters, progress token, hash. `reduce_world_state` folds one `ObservationUpdate` (observation plus monotonic `source_seq` plus mandatory `evidence_id`): it validates ingestion through the read-only ledger view (must resolve to ALLOW plus success plus non-empty session, with fresh provenance), returns the prior snapshot unchanged on duplicate ids, otherwise advances the endpoint band and bumps revision. Hash and progress token recompute canonically with wall-clock fields excluded, so determinism and freshness never fight.

Verification and falsification run broker-mediated as described in section 2.5. The finding-level `Replanner` fires only on real evidence-backed REFUTED findings, derives the new target from `counter-example` evidence, and emits exactly one step with `requester="replanner"`, deterministic id, parent linkage, and a `producer="replanner"` receipt.

Stop (`d14_stop.py`) is pure and ordered; first match wins: `MISSION_COMPLETE`, `POLICY_DENIAL`, `NO_APPLICABLE_CAPABILITY`, `MAX_STEPS` (default 5), `MAX_REPLANS` (default 1), then the three not-yet-ratified bounds (`MAX_FAILURES`, `NO_PROGRESS`, `CONFIDENCE_THRESHOLD`). Completion always wins over replanning; denial stops before any observation exists.

---

## 5. The D16 causal proof: Observation A to Action A to Observation B to state update to replan to different Action B

D16 Wave 1 proves the agent's next action is a pure function of governed, newly observed world state. Mission and target stay fixed; only the observation moves the decision.

The landed proof lives in `tests/test_d16_replanning_semantics.py` (4 tests). Its fixture is a fixed two-action plan DP-D16: Action A is `NETWORK_HTTP_REQUEST` against `http://synthetic.invalid:80/`, Action B is `NETWORK_TELNET_SESSION` against `telnet://synthetic.invalid:23/`, with hypotheses `H-A` and `H-B` bound per action. The chain runs:

1. `planner.plan(state)` on the initial snapshot selects Action A.
2. A governed success for A is folded as `ObservationRecord O-D16-A` (ALLOW-bound `EvidenceBinding`, session `session-d16`, fixed timestamp for bit-reproducibility).
3. `reduce_world_state` returns revision plus one with a changed `world_state_hash`.
4. `planner.plan(updated)` on the new snapshot selects Action B.

The test asserts the full causal bind jointly: the replanned action differs from baseline; it equals exactly the unobserved remainder of the same plan; plan id and mission id are unchanged (no plan swap); target id is unchanged (no target-name branching); and the hash delta is bound to the Action A observation (`updated.observations[-1].capability_id == baseline_action.capability_id`). The companion case pins the other direction: planning twice against an identical snapshot yields the identical action and identical deterministic `decision_id`, so repeats need no identity or scenario branch either. Terminal and refusal gates are pinned too: `COMPLETE` stops before replanning with no replacement action, and the declaration-only SSH proposal is denied before execution with zero observations.

Corroboration from adjacent suites: `tests/test_d14_autonomous_episode.py` (1 test) runs Action A through a real `BOBRuntime` with a synthetic opener and derives a different next action with `replan_count == 1`; `tests/test_d14_autonomy.py` (11 tests) pins selection ordering, prerequisite gating, denial-without-invocation, and no-progress stop on the same frozen seams.

---

## 6. Adversarial hardening (D17) and documented residuals

D17 (`docs/D17_ADVERSARIAL_HARDENING.md`) audited the complete loop from D12.2 through D16 with no code changes. Twelve attack classes were examined and are blocked by landed code with passing tests: ungoverned Tier-1 execution, execution outside Broker mediation, folding a DENY/failure/sessionless result, cross-session or stale injection, duplicate/replayed observations, evidence/binding mismatch, verification or falsification without evidence, forged completion, unbounded looping, credential exfiltration through evidence, raw bytes or secrets smuggled as observations, and target-name or scenario-specific selection. The provenance and session-binding model (Broker-stamped identity outward, HMAC-sealed execution identity, per-fold ALLOW plus success plus session plus freshness checks) held at every layer the tests reach.

Four adversarial probes remain as documented residuals, pinned as `@unittest.expectedFailure` in `tests/test_d17_hardening.py`. They are honest limits, not hidden bugs:

- **Content-binding (3 probes):** `AutonomousLoop.ingest` validates evidence identity and session provenance, then calls `reduce_world_state` without binding observation capability, target, or injected service to the Runtime execution content. A lying adapter holding a valid ALLOW binding could submit plausible but false normalized content under that binding's session and seqs, and the fold would accept it. Mitigations in depth: bounded normalized observations (caps, hashes not raw bytes, per-family types), independent broker-mediated verification/falsification rather than trust in the first observation, persisted `FindingRecord`s with evidence seqs, and gate conditions demanding causally bound probe/regression/test evidence before COMPLETE. The fix (seal `content_hash` into the execution binding at the mediator, verify at ingestion) is future work.
- **Stale-source-sequence (1 probe):** `ingest` does not enforce the D14 source-sequence monotonicity gate before reducing world state, so an older legitimately evidenced result presented again is not rejected at the coordinator layer. Mitigations: duplicate-id dedup returns the prior snapshot unchanged, and the stricter `reduce_state_transition` path raises `StaleObservationError` on non-newer seqs. Wiring that gate into `ingest` is future work.

Further non-blocking residuals carried from D16/D17: state-driven reselect is proven but end-to-end refutation closure (`VERIFIED -> REFUTED -> Plan B -> re-execute -> gate`) inside the autonomous rig is not; only a single-observation fold (A to B) is demonstrated, with multi-step chains and `conflicted` banding unexercised; the D16 module folds through a stub ledger view rather than a persisted ledger (real-seam ingestion is covered by the adjacent D14 episode test); discovery still trusts protocol labels as input; Barrier B stays design, not code; and the three stop bounds (`MAX_FAILURES`, `NO_PROGRESS`, `CONFIDENCE_THRESHOLD`) ship as fail-closed defaults without ratification. None of these blocks release, and each is tracked with its test or code pointer in the D16/D17 docs.

---

## 7. Known limitations

1. **Tier 1 does nothing yet, on purpose.** Five descriptors refuse at every layer. Any demo showing one "running" is showing the refusal path or something outside the boundary.
2. **No verification path for Tier 1.** All five bindings are `None`, so no retest and no falsification exist for them until defined.
3. **Observation content is not cryptographically bound** to the bound execution's bytes (residual R1 above).
4. **Source-sequence monotonicity is not enforced in `ingest`** (residual above).
5. **Single-observation episode.** Multi-fold chains, conflicting observations, and failure-kind folds over the D16 rig are unexercised.
6. **Network surface is narrow.** The only network capability is `NETWORK_HTTP_REQUEST` (GET/HEAD) plus the Telnet session path. No shell, SMB, privilege escalation, port scanning, or arbitrary methods.
7. **Breakout caveat.** The validated Breakout run reaches COMPLETE without capturing a flag: Breakout does not serve its root flag over HTTP, so condition G is satisfied as "no unresolved findings." That's not a claim of solving Breakout.
8. **Deterministic scope.** Benchmarks run on the canonical `authkit` fixture; multi-repo generalization is not claimed.
9. **Legacy residue.** `src/`, `arena/`, `cli/`, `evaluations/`, and related research files stay on disk, excluded from the shipped package by the packaging include. Don't confuse legacy `src/arena` milestone files with the governed D13 to D17 milestones.
10. **Live proof gate is closed.** `LIVE_PROOF_AUTHORIZED = False` (`scripts/c1a_live_proof.py`); remote M1/M2/M5 closure is NOT VERIFIED.
11. **No live targets in D16/D17.** Synthetic hosts only; the D16 module opens no socket.
12. **Older LIMITATIONS.md entries** (`docs/LIMITATIONS.md`, L-001 through L-028) describe the legacy substrate's benchmark saturation, safety decoupling, and dormancy findings. They stay valid for that substrate and don't transfer to the governed product path except where cited above.

---

## 8. Authorized/CTF scope

Use this system only where you hold written permission or inside sanctioned CTF and lab targets. That means your own machines, your own ranges, contracted engagements with a signed scope document, and competition targets whose rules allow the techniques. It never means third-party production, shared infrastructure you don't own, or anything outside the declared `TargetProfile` and workspace. Policy scope matching (exact host, port, protocol, plus method/command allow-lists) is a guardrail, not a permission slip: operator authorization comes first, and the gate refuses anything the ledger can't back. When evidence is absent, the system records the failure and refuses. It never converts failure into COMPLETE.

---

## 9. Reproducible demo procedure

Prereqs: Linux (WSL Ubuntu works), Python 3, Node, `bwrap` for sandboxed provider runs. Everything below runs from the repo root.

```bash
# 0. Validate environment (Python, Node, bwrap, pinned digests)
./scripts/run_demo.sh --check-prereqs

# 1. Canonical judge demo: 13 stages -> QualityGate COMPLETE, exit 0
./scripts/run_demo.sh

# 2. Honest refusal demo: exit 1, QualityGate REFUSE via failed oracle probe
./scripts/run_demo.sh --refuse

# 3. Deterministic hero demo (stdlib-only imports)
PYTHONPATH=. python3 demos/authkit_hero.py

# 4. Hackathon network path (TESTING/HTB through the real product API)
./scripts/run_hackathon_demo.sh --preflight   # READY / NOT READY / OPTIONAL
./scripts/run_hackathon_demo.sh --success     # governed run -> 7/7 COMPLETE
./scripts/run_hackathon_demo.sh --refuse      # honest refusal -> REFUSE
./scripts/run_hackathon_demo.sh --tests       # one-command release suite

# 5. Audit durable run evidence
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

Each run writes an isolated `runs/<run_id>/{evidence.jsonl,artifacts/}` and prints the run id, evidence path, and gate verdict. Fixture files self-restore on exit. Release condition: `git status --short` must print nothing before cutting a release. Full demo docs: `CANONICAL_DEMO.md`, `docs/HACKATHON_DEMO.md`, `docs/DEMO_CHECKLIST.md`, `demo/README.md`.

---

## 10. Final test counts

Measured 2026-09-23/24 on this tree (Python 3.14, WSL Ubuntu). Rerun any row with its command; counts move as the tree moves.

| Suite | Command | Result |
|---|---|---|
| Core seam and gov-loop (12 modules) | `PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner tests.test_m9_multi_replan tests.test_m10_1_runs tests.test_m10_2_metrics tests.test_m10_3_benchmark` | Ran 210, OK |
| D15 catalogue plus executability matrix | `PYTHONPATH=. python3 -m unittest tests.test_d15_capability_catalogue tests.test_d15_executability_matrix` | Ran 12, OK |
| D16 replanning semantics | `PYTHONPATH=. python3 -m unittest tests.test_d16_replanning_semantics` | Ran 4, OK |
| D16 autonomous loop acceptance | `PYTHONPATH=. python3 -m unittest tests.test_d16_autonomous_loop` | Ran 8, OK |
| D17 adversarial hardening | `PYTHONPATH=. python3 -m unittest tests.test_d17_hardening` | Ran 9, OK (expected failures: 4, the documented content-binding x3 plus stale-sequence x1) |
| D13/D14/D15/D16 combined fabric and loop | `PYTHONPATH=. python3 -m unittest tests.test_d13_capability_fabric tests.test_capability_fabric tests.test_d15_observation tests.test_d15_governed_bridge tests.test_d15_generic_bridge tests.test_d14_autonomy tests.test_d14_autonomous_episode tests.test_d16_replanning_semantics tests.test_d16_autonomous_loop tests.test_d16_loop_unit tests.test_d16_state_transition` | Ran 99, OK |
| D15/D16/D17 combined (this release) | `PYTHONPATH=. python3 -m unittest tests.test_d15_capability_catalogue tests.test_d15_executability_matrix tests.test_d16_replanning_semantics tests.test_d16_autonomous_loop tests.test_d17_hardening` | Ran 33, OK (expected failures: 4) |
| T3MP3ST integration (per README, measured 2026-09-23) | `PYTHONPATH=. python3 -m unittest tests.test_t3mp3st_integration` | Ran 30, OK |
| C1A provider and authorization (per README, measured 2026-09-23) | 13 C1A modules, see README Status | Ran 109, OK |

Repo-wide discovery is reported separately in the README (1443 tests, 0 failures, 18 pre-existing collection/import errors from legacy-substrate imports outside the governed path). Those errors don't touch the product suites above.

---

## 11. What D18 leaves for later

No code changed here, so the D17 handoff stands as the backlog, in priority order: bind observation content to execution evidence; close the refutation loop in the autonomous rig; run a multi-fold episode with conflict; replace the D16 stub ledger view with a real persisted ledger; ratify or remove the three unratified stop bounds and settle hypothesis-band dynamics; assert gate condition G green on the episode ledger; treat protocol labels as untrusted input and land Barrier B before any Tier-1 promotion. Constraints carry forward: no frozen-seam edits to do it, no new offensive capabilities, no target-name branching, and every new claim ships with its passing test command.
