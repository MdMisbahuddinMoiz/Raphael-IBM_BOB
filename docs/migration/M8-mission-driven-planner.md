# M8 — Mission-Driven Planner + Control-Loop Hardening

This document captures the M8 implementation:
- `raphael_bob/planner.py` (Planner now reads target from Mission)
- `raphael_bob/contracts.py` (Mission gains `problem: Dict[str, Any]`)
- `demos/authkit_hero.py` (Runner passes only the Mission; no target kwarg)
- `tests/test_m8_planner.py` (13 new tests)

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / module / fixture / demo defined |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_m8_*.py` and `demos/authkit_hero.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## What changed in M8

Before M8 (M7 hidden dependency):

```python
planner = Planner(symptom_target="fixtures/authkit/login.py")  # Runner injects
plan_a = planner.plan_a(mission)
```

After M8 (mission-driven):

```python
mission = Mission(
    mission_id="M-authkit",
    description="...",
    scope="fixtures",
    criteria=[...],
    problem={"symptom_target": "fixtures/authkit/login.py"},  # <- here
)
planner = Planner()                                          # <- no args
plan_a = planner.plan_a(mission)                            # <- only mission
```

The Planner now refuses to plan if `mission.problem["symptom_target"]` is missing. This is the M8 architectural rule: the Runner cannot secretly inject the target.

## Mission contract change

`raphael_bob.contracts.Mission` gains an optional `problem: Dict[str, Any]` field (default `{}`). The Planner inspects:

| Key | Required | Default | Meaning |
|---|---|---|---|
| `symptom_target` | YES | (none) | The file the Plan A READ targets |
| `capability` | no | `"read"` | BOB-native capability |
| `purpose` | no | `"plan-a:probe:<target>"` | Free-text purpose line |

All other M2..M7 tests construct `Mission` without a `problem` field, and they continue to work (the field defaults to `{}`).

## Planner changes

`raphael_bob.planner.Planner`:

- No more constructor arguments. `Planner()` only.
- `plan_a(mission)` reads `mission.problem["symptom_target"]`, `["capability"]`, and `["purpose"]`.
- Raises `ValueError` if `mission.problem` is not a dict, if `symptom_target` is missing, or if `capability` is not a valid BOB Capability.
- Plan A id remains deterministic: `P-<12 hex>` from SHA-256(canonical(mission_id, "plan-a")).
- Does NOT import Runtime, Broker, or Policy.
- Does NOT invoke the legacy Wave1 loop.
- Does NOT generate Plan B (that is the Replanner's job).

## Demo change

`demos/authkit_hero.py`:

- Removed `Planner(symptom_target="...")`.
- Replaced with `Planner()`.
- Mission now carries `problem={"symptom_target": ..., "actual_defect_target": ..., "capability": "read", "purpose": "..."}`.
- The Replanner's `ReplanStrategy(preferred_target="...")` (the M5 contract) is unchanged — the Replanner still has its own override because the M5 brief required the Replanner to know where to look when the counter-example lacks an explicit target.

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner
```

| Suite | Tests |
|---|---|
| test_seam_contracts (M1..M8 anti-claim updates) | 33 |
| test_m2_boundary (M2 regression) | 21 |
| test_m3_evidence (M3 regression) | 22 |
| test_m4_verifier_falsifier (M4 regression) | 17 |
| test_m5_replanner_runner (M5 regression) | 14 |
| test_m6_quality_gate (M6 regression) | 14 |
| test_m7_hero (M7 regression) | 15 |
| test_m8_planner (M8 new) | 13 |
| **total** | **147** |

## Tests passed/failed

```
Ran 147 tests in 4.113s
OK
```

All pass; 0 failures.

## Proof that Runner no longer supplies target directly

`tests/test_m8_planner.HeroRegressionAfterM8`:

- `test_runner_does_not_construct_planner_with_target` — source-level: demo must call `Planner()` (no args) and must contain a `problem=` dict with `symptom_target`. Demo must NOT contain `Planner(symptom_target` or `planner.symptom_target`.
- `test_hero_runner_uses_only_mission` — runtime-level: extracts the `plan_a(...)` call from the demo source and asserts its argument list contains only `mission` (no `symptom_target`, no `login.py`).
- `test_demo_runs_twice_with_deterministic_plan_a_id` — runs the demo twice and asserts both runs print `plan_id=P-f5947b0c1d42` (same mission -> same plan id).

## Mission-driven Planner test

`test_different_missions_produce_different_targets` — `Mission("M-1", problem={"symptom_target": "src/a.py"})` and `Mission("M-2", problem={"symptom_target": "src/b.py"})` produce plans with different targets via the same Planner instance. This proves the Planner is not returning a constant.

## Determinism test

`test_planner_is_deterministic` — 5 calls to `Planner().plan_a(mission)` with the same Mission produce identical `plan_id` and identical target. SHA-256(canonical(mission_id, "plan-a")) is deterministic.

## M7 hero regression

`test_hero_still_reaches_complete` — runs the full M7 hero demo via subprocess; asserts `COMPLETE` appears in stdout. The M7 hero still reaches `QualityGate.COMPLETE` with all 7 conditions satisfied.

## Plan B separation

`test_replanner_remains_only_plan_B_generator`:

- `Planner` source: does NOT contain the string `"plan_b"`.
- `Replanner` source: DOES contain `"plan_b"`.

## Legacy components reused/adapted

| Seam | Legacy module | M8 disposition |
|---|---|---|
| Planner | `src/orchestrator/brain/action.py` (Action/Precondition/Effect) | ADAPT conceptually; **NOT imported**. M8 Planner uses `mission.problem` as its world model. |
| Planner | `src/raphael/cognitive/planner.py` (GreedyPlanner, UCB) | REPLACE. M8 Planner is mission-driven. |
| Mission | (none — Mission was a M1 dataclass) | EXTENDED at M8 with the `problem` field. |
| All other seams | unchanged | `m8_status` annotated for sealed specs; Runner / Replanner / Verifier / Falsifier / QualityGate unchanged. |

## Remaining M9/M10 gaps

- **M9 (multi-replan loop)**: the Runner is still single-pass. If the v2 fix also fails, no second replan fires. M9 owns this.
- **M10 (metrics + submission)**: no `metrics.json` aggregation, no `PROVENANCE.md`, no `submission-checklist.md`, no `demo-runbook.md` yet. M7 saves `evidence.jsonl` + `artifacts/` per run.

**M8 proves:** the initial Plan A is genuinely generated from Mission information; the Runner cannot secretly inject the target; the Planner remains deterministic; the Plan B/Replan separation is preserved; the M7 hero still passes end-to-end.