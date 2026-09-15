# M9 — Bounded Multi-Replan + Evidence/Gate Hardening

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / module / fixture / demo defined |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_m9_*.py` and the suite below |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## What changed in M9

M9 closes the gaps found by the physical checkpoint audit:

1. **M8 completed first** (`7ebcca046`): the mission-driven Planner
   (`Mission.problem`, no-arg `Planner()`) is committed separately
   from all M9 work. The prior HEAD (`a19fcc30c`) had updated M5/M6
   tests to the `Mission(problem=...)` shape without shipping the
   contracts/planner change, so HEAD was internally inconsistent.
2. **`raphael_bob/runner.py`** — bounded recovery loop
   (`max_replans`, default 1 preserves M5/M6 behavior exactly):
   each iteration replans from the REFUTED finding and registers a
   NEW finding for the new plan (`F-<plan[2:8]>`, `supersedes` set),
   because the M4 lifecycle forbids re-verifying REFUTED findings.
   Every recovery step goes through Runtime -> Broker -> Policy.
   Per-iteration `challenge_specs` override the legacy challenger
   triple; `verification_tests` run broker-mediated RUN_TESTs before
   the gate. No debug output on the hot path.
3. **`raphael_bob/quality_gate.py`** — conditions B/C repaired:
   B requires RUN_TEST + ALLOW + successful result + artifact with
   `returncode == 0` (DENIED/failed tests never count); C requires a
   `producer="regression"` record plus >= 2 distinct ALLOWed
   capabilities (DENIED requests contribute no breadth).
4. **`demos/authkit_hero.py`** — remediation side channels closed:
   v1/v2 installs are broker-mediated WRITEs, Plan B is executed
   through Runtime -> Broker -> Policy, and test runs are
   broker-mediated RUN_TESTs on slash paths (ALLOW + real
   returncode). The independent probe stays an external subprocess.
5. **`tests/test_m9_multi_replan.py`** — rewritten mock-free: 17
   tests over a deterministic 3-candidate workspace drive the real
   stack (no monkey-patching, no plan-ID rewriting).
6. **`tests/test_m6_quality_gate.py`** — 5 new §17 regression tests
   (denied/failed/successful RUN_TEST, C breadth both ways) plus one
   intent-preserving update: `test_plan_a_refuted_plan_b_complete`
   now gives F2 an explicit benign challenge (its title scenario —
   "Plan B complete" — requires F2 to survive, which the M9 loop
   makes explicit instead of implicit).

## Lifecycle model (M9)

```text
Plan A -> F1 -> verify -> falsify -> F1 REFUTED
  -> replan -> Plan B (parent A) -> F2 (new id, supersedes F1)
  -> verify -> falsify -> F2 REFUTED
  -> replan -> Plan C (parent B) -> F3 (new id, supersedes F2)
  -> verify -> falsify -> VERIFIED or REFUTED
  -> QualityGate
```

`outcome.finding` remains F1 (M5 compatibility); `outcome.findings`
carries the full sequence; `outcome.plan_c` is set from the second
replan on. The loop never exceeds `max_replans`; exhaustion with a
REFUTED terminal finding yields REFUSE via condition G.

## Tests executed

```text
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts \
  tests.test_m2_boundary tests.test_m3_evidence \
  tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner \
  tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner \
  tests.test_m9_multi_replan
```

```text
Ran 169 tests in ~3.6s
OK
```

152 (M1–M8: 147 prior + 5 new §17 gate tests) + 17 (M9) = 169.
The M7 hero reaches COMPLETE with identical plan IDs across runs;
its 63-record ledger now contains WRITE remediation, Plan B
execution, and ALLOWed RUN_TEST evidence.

## Known warts (not hidden)

- Replanner evidence payload key `plan_b_id` also names Plan C's id
  on the second replan (M5 test pins the key; renaming would churn
  M5 for no behavioral gain).
- The demo rewrites one Finding's summary/target via direct store
  access after its VERIFIED transition (pre-existing M7 behavior,
  preserved; the transition records themselves are intact).
- Hero run dirs remain ephemeral `/tmp/authkit_hero_run_*/`
  (durable `runs/` aggregation is M10's job, explicitly not started).
