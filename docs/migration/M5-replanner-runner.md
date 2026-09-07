# M5 — Evidence-Driven Replanning + Runner

This document captures the M5 implementation in `raphael_bob/replanner.py`
and `raphael_bob/runner.py`.

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / dataclass defined and importable |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_m5_*.py` and `tests/test_seam_*.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M5)

```
raphael_bob/
├── __init__.py            # re-exports M5 symbols
├── contracts.py           # Plan / FocusedContext / GateVerdict
├── evidence_ledger.py     # M3 evidence ledger (FindingRecord, finding_id)
├── finding.py             # M4 lifecycle store
├── verifier.py            # M4 broker-mediated retest engine
├── falsifier.py           # M4 broker-mediated active challenge (M5: counter-example carries `target`)
├── replanner.py           # NEW — evidence-driven Plan B generator
├── runner.py              # NEW — control-loop orchestrator (REFUSE only)
└── adapters/legacy.py     # Replanner + Runner specs annotated as M5 IMPLEMENTED
```

## Control loop wired by M5

```
Mission
   ↓
PlannerStub.plan_a(mission) -> Plan A
   ↓
Runner submits Plan A step through Runtime -> Broker -> Policy
   ↓
candidate Finding registered in FindingStore
   ↓
Verifier.verify(finding, retest, mission) -> UNVERIFIED -> VERIFIED
   ↓
Falsifier.challenge(finding, spec, mission) -> VERIFIED -> REFUTED
   ↓
FocusedContext = FindingStore.evidence_for(finding_id) → diag.evidence + refuted_claim + mission_scope
   ↓
Replanner.replan(focused_context, plan_a) -> Plan B  (parent_plan_id set)
   ↓
Runner submits Plan B step through Runtime -> Broker -> Policy (requested_by="replanner")
   ↓
GateVerdict.REFUSE  (M6 owns COMPLETE)
```

## Replanner

`raphael_bob.replanner.Replanner.replan(focused_context, parent_plan)`:

1. Validates the trigger:
 - `refuted_claim.state == REFUTED`
 - `diagnostic_evidence` is non-empty
2. Derives the new action target:
 - Pass 1: prefer the first counter-example evidence's `target` field
 - Pass 2: fall back to the first evidence with a `target` field
 - Pass 3: fall back to `parent_plan.steps[0].target`
3. Builds `Plan B` with:
 - `parent_plan_id = parent_plan.plan_id`
 - `steps[0].requester = "replanner"`
 - `steps[0].finding_id = refuted_claim.finding_id`
 - `steps[0].purpose = "replan-after-refutation:<id>:counter-target=<target>"`
 - `steps[0].plan_id = derive_plan_b_id(parent_plan, refuted_claim.finding_id)`
4. Persists a `producer="replanner"` evidence record whose payload
   carries `parent_plan_id`, `plan_b_id`, `refuted_finding_id`, `new_target`,
   `new_step_purpose`, `mission_scope`, and `evidence_seqs`.

`derive_plan_b_id(parent_plan, refuted_finding_id)` returns a deterministic
SHA-256-based identifier; identical inputs produce identical Plan B ids.

## Runner

`raphael_bob.runner.Runner.run(mission)`:

1. Generate Plan A via `PlannerStub.plan_a(mission)`.
2. Submit Plan A's step through the Runtime.
3. Register a candidate Finding in `FindingStore`.
4. Verifier.verify → UNVERIFIED → VERIFIED.
5. Falsifier.challenge → VERIFIED → REFUTED.
6. If and only if REFUTED:
 - Build FocusedContext from `FindingStore.evidence_for(...)`.
 - Replanner.replan → Plan B.
 - Submit Plan B's step through the Runtime.
7. Return `GateVerdict.REFUSE`. M6 owns COMPLETE.

`RunnerOutcome` exposes `gate_verdict`, `plan_a`, `plan_b`, `finding`,
`mission`, `plan_a_step_runtime_seq`, `plan_b_step_runtime_seq`.

## FocusedContext construction

The Runner's `_build_focused_context(refuted, plan_a, mission)` walks
`ledger.records_for_finding(refuted.finding_id)` (sorted by ledger seq),
filters to `kind="evidence"` records, and builds a list of
`EvidenceReceipt` (with `evidence_id`, `sequence`, `producer`, and `payload`
carrying the full record). The `FocusedContext` therefore carries the
actual ledger sequence numbers that motivated the refutation.

If the chain is empty (defensive path), a single minimal
`producer="runner"` receipt is synthesized so the Replanner never sees
an empty diagnostic list.

## Plan A → Plan B causal evidence

The replan evidence record persisted by the Replanner carries:

```
{
  "parent_plan_id": "<Plan A id>",
  "plan_b_id": "<Plan B id>",
  "refuted_finding_id": "<F id>",
  "new_target": "<path>",
  "new_step_purpose": "replan-after-refutation:...",
  "mission_scope": "src/",
  "evidence_seqs": [<list of FindingRecord seqs>]
}
```

This makes the chain reconstructible: any reader of `runs/<id>/evidence.jsonl`
can answer "Why was this action executed?" with the parent → refuted → replan chain.

## Determinism

- `derive_plan_b_id(...)` is deterministic.
- `Replanner._derive_target(...)` is deterministic given the evidence chain.
- Two replan calls with the same `(focused_context, parent_plan)` produce
  byte-identical `Plan B` instances.
- The Runner does NOT use wall-clock time, random seeds, or in-memory
  mutable state across replan calls.

## Replanner action provenance

A Plan B step's `ActionRequest`:

| Field | Value |
|---|---|
| `requester` | `"replanner"` |
| `finding_id` | the REFUTED finding's id |
| `purpose` | `"replan-after-refutation:<id>:counter-target=<target>"` |
| `plan_id` | the deterministic Plan B id |
| `capability` | `ReplanStrategy.capability` (default READ) |
| `target` | the diagnostic evidence's counter-example target |

## Legacy isolation

- The Runner does NOT import `src/raphael/main.py` (Wave1 cognitive loop).
- The structural assertion `tests/test_m5_replanner_runner.Wave1Isolation`
  verifies this by grepping the package for active imports of
  `raphael.main` outside the documentation.
- The Planner in `Runner` is a stub (M5); M7 replaces it.

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner
```

| Suite | Tests |
|---|---|
| test_seam_contracts (M1..M5 anti-claim updates) | 32 |
| test_m2_boundary (M2 regression) | 21 |
| test_m3_evidence (M3 regression) | 22 |
| test_m4_verifier_falsifier (M4 regression) | 17 |
| test_m5_replanner_runner (M5 new) | 14 |
| **total** | **104** |

## Tests passed/failed

```
Ran 104 tests in 0.148s
OK
```

All pass; 0 failures.

## Legacy components reused/adapted

| Seam | Legacy module | M5 disposition |
|---|---|---|
| Replanner | `src/orchestrator/brain/strategy.py` (heuristic strategy learner) | ADAPT conceptually (Detected→UNDER_INVESTIGATION→RESOLVED pattern); **NOT imported**. M5 ships a fresh broker-mediated Replanner. |
| Replanner | `src/raphael/cognitive/planner.py:69 GreedyPlanner` (UCB step selector) | REPLACE. M5 Replanner is evidence-driven, not utility-driven. |
| Runner | `src/raphael/main.py:30` (Wave1 cognitive loop) | ISOLATE. M5 Runner is a fresh implementation. |
| Planner | `src/orchestrator/brain/action.py` (Action/Precondition/Effect) | ADAPT conceptually; M5 ships a stub Planner that emits BOB-native LIST/READ actions. |
| Verifier | unchanged from M4 | unchanged |
| Falsifier | unchanged from M4 | M5 adds `target`/`capability` to the counter-example payload so the Replanner can derive the Plan B target |
| All other seams | unchanged | `m5_status` annotated as "M5: NOT IMPLEMENTED" for reserved seams |

## Remaining gaps

- The M5 Planner is a stub. M7 will replace it with a proper Planner
  that uses the BOB-native Action / Precondition / Effect model.
- The Replanner emits exactly one Plan B step. M7 may extend to multi-step
  replans.
- No QualityGate yet. M6 owns COMPLETE.

## M6 readiness

M6 (QualityGate + final orchestration) needs:
1. A `QualityGate.evaluate(mission, findings, evidence, behavior_probe_ok,
   regression_ok)` returning `GateVerdict`.
2. The Runner (M5) currently returns `REFUSE` unconditionally. M6 will
   wire the Runner to call the gate after Plan B's verifier retest.
3. The QualityGate MUST consume real ledger evidence; no fabricated
   COMPLETE.

**M6 is AUTHORIZED** to begin, contingent on developer authorization.