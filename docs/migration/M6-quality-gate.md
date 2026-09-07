# M6 — QualityGate + Final Orchestration

This document captures the M6 implementation in `raphael_bob/quality_gate.py`
and the M6 changes to `raphael_bob/runner.py` and
`raphael_bob/evidence_ledger.py`.

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / dataclass defined and importable |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_m6_*.py` and `tests/test_seam_*.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M6)

```
raphael_bob/
├── __init__.py            # re-exports M6 symbols
├── contracts.py           # GateVerdict, Finding, Mission
├── evidence_ledger.py     # M3 ledger + M4 FindingRecord + M6 GateRecord
├── finding.py             # M4 lifecycle store
├── verifier.py            # M4 broker-mediated retest engine
├── falsifier.py           # M4 broker-mediated active challenge
├── replanner.py           # M5 evidence-driven Plan B generator
├── runner.py              # M5 control loop + M6 final gate delegation
├── quality_gate.py        # NEW — sole COMPLETE authority
└── adapters/legacy.py     # QualityGate spec marked M6 IMPLEMENTED
```

## Gate contract

`BOBQualityGate.evaluate(inputs: GateInputs) -> GateEvaluation`

| Field | Type | Meaning |
|---|---|---|
| `verdict` | `GateVerdict` | `COMPLETE` or `REFUSE` (the gate's verdict; persisted) |
| `passed` | `Tuple[str, ...]` | condition names that passed |
| `failed` | `Tuple[str, ...]` | condition names that failed |
| `reasons` | `Tuple[str, ...]` | human-readable failure reasons |
| `evidence_refs` | `Tuple[str, ...]` | real `evidence_id`s from the ledger |
| `finding_refs` | `Tuple[str, ...]` | real `finding_id`s referenced |

Every call writes a `GateRecord` (kind="gate") to the ledger so the final
decision is reconstructible.

## Seven conditions

| ID | Name | Rule |
|---|---|---|
| A | mission-criterion | `mission.criteria` is non-empty |
| B | required-tests | `regression_ok=True` AND at least one `RUN_TEST` capability invocation in the ledger |
| C | regression | `regression_ok=True` AND ≥ 2 distinct capabilities invoked |
| D | independent-behavior-probe | `behavior_probe_ok=True` AND a `producer="probe"` evidence record with `allowed=True` |
| E | scope | every request target is inside the mission scope; no DENY+result pair |
| F | evidence | ledger contains request, decision, result, AND evidence records |
| G | finding-state | no UNVERIFIED finding; REFUTED findings must have a subsequent replan evidence record |

ANY condition failing → `GateVerdict.REFUSE`. Failure produces reasons.
Missing evidence (empty ledger, missing probe record, etc.) → REFUSE.

## Sole COMPLETE authority proof

- Only `BOBQualityGate.evaluate()` may produce `COMPLETE` under M6 conditions.
- The Runner reads the gate's verdict and propagates it via
  `RunnerOutcome.gate_verdict`. The Runner never references
  `GateVerdict.COMPLETE` (verified by `test_runner_does_not_construct_complete_directly`).
- The structural test `test_only_quality_gate_constructs_complete` greps every
  other module in the package and asserts `GateVerdict.COMPLETE` does not
  appear.

## Anti-bypass mechanism

The Runner is the only caller of the gate, but the gate enforces
provenance internally:

- `behavior_probe_ok=True` is only honored when a `producer="probe"`
  evidence record (with `allowed=True`) is in the ledger.
- `regression_ok=True` is only honored when at least one `RUN_TEST`
  capability invocation is in the ledger.

The Runner persists these proof records (when the corresponding bool
is True) just before calling the gate. A caller cannot fake
`behavior_probe_ok=True` without leaving a real probe evidence record.

## Final orchestration

```
Mission
   ↓
PlannerStub.plan_a(mission) -> Plan A
   ↓
Runtime.submit(Plan A step) -> Finding registered
   ↓
Verifier.verify  -> UNVERIFIED -> VERIFIED
   ↓
Falsifier.challenge -> VERIFIED -> REFUTED
   ↓
FocusedContext from ledger.records_for_finding(...)
   ↓
Replanner.replan -> Plan B
   ↓
Runtime.submit(Plan B step) -> corrected action
   ↓
Verifier.verify again
   ↓
persist regression + probe proof records
   ↓
BOBQualityGate.evaluate(mission, findings, regression_ok, behavior_probe_ok)
   ↓
GateRecord (kind="gate") persisted
   ↓
GateVerdict.COMPLETE or GateVerdict.REFUSE
```

## False-success negative paths (the M6 critical proofs)

| Test | What it proves |
|---|---|
| `IndependentProbeFailure.test_named_test_passes_but_probe_fails` | Even with a passing RUN_TEST, if `behavior_probe_ok=False`, the gate returns REFUSE. |
| `MissingEvidenceRefuses.test_empty_ledger_refuses` | An empty ledger with `regression_ok=True` and `behavior_probe_ok=True` still REFUSES (condition E, F fail). |
| `UnverifiedFindingRefuses.test_unverified_finding_blocks_complete` | An UNVERIFIED finding that affects the mission blocks COMPLETE. |
| `RefutedWithoutReplanRefuses.test_refuted_finding_without_replan_blocks` | A REFUTED finding without a replan evidence record blocks COMPLETE. |

## Positive path

`PositiveComplete.test_runner_with_required_test_completes`:
injects a passing `RUN_TEST`, runs the loop without refutation, and
asserts `outcome.gate_verdict == GateVerdict.COMPLETE`.

`FullControlLoop.test_plan_a_refuted_plan_b_complete`:
runs the full Plan A → REFUTED → Replan → Plan B loop, then injects a
RUN_TEST and re-evaluates the gate to COMPLETE. The ledger chain
(Plan A → Verifier → Falsifier → Replan → QualityGate) is
reconstructible.

## Gate decision persistence

Every `evaluate()` call writes a `GateRecord` (kind="gate") to the
ledger. The record carries:
- `decision` ("complete" or "refuse")
- `run_id` (the ledger run directory name)
- `mission_id`
- `checks` (tuple of condition names)
- `evidence_refs` (real evidence_ids from the ledger)
- `finding_refs` (real finding_ids)
- `reasons` (human-readable failure reasons)
- `digest` (SHA-256 of the canonical payload)

Verified by `GateDecisionPersisted` and `GateReadsRealLedger`.

## Determinism

- `BOBQualityGate.evaluate()` does NOT depend on wall-clock time or randomness.
- Two calls with the same `(mission, findings, regression_ok, behavior_probe_ok)`
  produce the same verdict and the same sets of passed/failed conditions
  (the *order* of `evidence_refs` may shift because the gate captures the
  most recent 8 evidence records, but the SETS are equal).
- Verified by `GateDeterminism.test_two_evaluations_produce_identical_verdict`.

## Legacy isolation

- The Runner does NOT import `src/raphael/main.py` (Wave1 cognitive loop).
  Verified by `Wave1Isolation.test_main_py_not_imported` in M5.
- `src/arena/conclusion.py` (RBS arena evaluator) is NOT used as the BOB
  QualityGate. The BOB gate is `raphael_bob.quality_gate.BOBQualityGate`.

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate
```

| Suite | Tests |
|---|---|
| test_seam_contracts (M1..M6 anti-claim updates) | 33 |
| test_m2_boundary (M2 regression) | 21 |
| test_m3_evidence (M3 regression) | 22 |
| test_m4_verifier_falsifier (M4 regression) | 17 |
| test_m5_replanner_runner (M5 regression) | 14 |
| test_m6_quality_gate (M6 new) | 14 |
| **total** | **118** |

## Tests passed/failed

```
Ran 118 tests in 0.702s
OK
```

All pass; 0 failures.

## Legacy components reused/adapted

| Seam | Legacy module | M6 disposition |
|---|---|---|
| QualityGate | `(none)` | REPLACE → M6 IMPLEMENTED as `BOBQualityGate` |
| Runner | `src/raphael/main.py` | ISOLATE → M6 still ISOLATE; M6 Runner is the new orchestrator |
| All other seams | unchanged | `m6_status` annotated as "M6: unchanged" or "M6: NOT IMPLEMENTED" for reserved seams |

## Remaining gaps

- The M5 Planner is still a stub. M7 replaces it with a real Planner.
- The QualityGate does not yet know about specific mission criteria semantics
  (e.g. "all named tests pass"). The M6 gate checks structural conditions
  (test count, probe presence); M7 wires the specific test names.
- The M7 hero fixture will exercise the gate on the authkit scenario.

## M7 readiness

M7 (Hero fixture + metrics + submission) needs:
1. A real `Planner` that emits Plan A targeting the candidate defect.
2. A real `Runner` configuration (or runner kwargs) that targets the
   authkit-style `src/login.py` (the wrong target) for Plan A and
   `src/session.py` (the actual defect) for Plan B.
3. The QualityGate is already authoritative; M7's hero will demonstrate
   the COMPLETE path on a clean authkit-style scenario.

**M7 is AUTHORIZED** to begin, contingent on developer authorization.