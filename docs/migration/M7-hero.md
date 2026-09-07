# M7 — Real Planner + Authkit Hero

This document captures the M7 implementation:
- `raphael_bob/planner.py` (real Planner replacing M5's PlannerStub)
- `fixtures/authkit/` (the authkit-style hero fixture)
- `probes/auth_behavior_probe.py` (independent behavior probe)
- `demos/authkit_hero.py` (the end-to-end hero demo)

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / module / fixture / demo defined |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_m7_*.py` and `demos/authkit_hero.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M7)

```
raphael_bob/
├── __init__.py            # re-exports Planner
├── planner.py             # NEW — real Planner (replaces PlannerStub)
├── ...                    # M2..M6 unchanged
└── adapters/legacy.py     # Planner spec annotated as M7 IMPLEMENTED

fixtures/authkit/          # NEW — authkit-style hero fixture
├── __init__.py
├── store.py               # in-memory user/token state
├── session.py             # THE ACTUAL DEFECT lives here
├── login.py               # the SYMPTOM / DECOY
├── test_login.py          # the NAMED test (passes under both v1 and v2)
└── test_auth.py           # the INVARIANT test (fails under v1, passes under v2)

probes/
└── auth_behavior_probe.py # NEW — independent behavior probe

demos/
└── authkit_hero.py        # NEW — the end-to-end hero demo

tests/
└── test_m7_hero.py        # NEW — 15 M7 tests
```

## Authkit fixture (Failure Class 2 + Recovery)

```
store.py   ->  in-memory USERS, TOKENS with `expired` flag
session.py ->  THE BUGGY validate_session (ignores expiration and user binding)
login.py   ->  plausible-but-wrong fix surface (the decoy)
test_login.py -> 4 tests; all pass for both v1 broken and v2 fixed
test_auth.py  -> 4 tests; v1 broken FAILS, v2 fixed PASSES
```

The defect is deterministic and reproducible: `validate_session` only
checks that the claimed user is known, not that the token is bound to
them or non-expired.

## Independent behavior probe

`probes/auth_behavior_probe.py` is independently authored from the
test_login.py / test_auth.py test suite:

- It does not subclass `unittest.TestCase`.
- It does not import any `test_*` module.
- It is callable both as a script (exit code 0/2) and as a library
  function (`run_probe() -> ProbeResult`).
- It runs 10 scenarios covering expired tokens, cross-user tokens,
  fresh tokens, unknown tokens, and empty tokens.

On the BUGGY session.py: `ProbeResult(ok=False, failures=[...])`,
exit code 2.
On the V2 FIXED session.py: `ProbeResult(ok=True, failures=[])`, exit 0.

## Real Planner

`raphael_bob.planner.Planner` replaces the M5 `PlannerStub`:

- `plan_a(mission) -> Plan`:
- Single BOB-native READ action against `symptom_target` (default
 `fixtures/authkit/login.py`).
 - `mission_id` linked.
 - Deterministic Plan A id (`P-<12 hex>` from SHA-256).
- `Planner` does NOT import Runtime, Broker, or Policy.
- `Planner` does NOT emit a Plan B (that is the Replanner's job).
- `Planner` does NOT invoke the Wave1 cognitive loop.

## Hero flow (12 steps)

| # | Step |
|---|---|
| 01 | Planner -> Plan A (decoy target: login.py) |
| 02 | Plan A executed via Runtime -> Broker -> Policy (ALLOW) |
| 03 | Candidate Finding registered (UNVERIFIED) |
| 04 | **Failure Class 1** — Forbidden action: RUN_TEST on non-test file -> Policy DENY (no side effect) |
| 05 | Diagnostic discovery: READ session.py + login.py |
| 06 | v1 fix installed on login.py; named test_login.py PASSES |
| 07 | Independent behavior probe FAILS under v1 (probe returns failures) |
| 08 | Falsifier -> REFUTED (predicate observed the probe's failure) |
| 09 | Replanner -> Plan B (target=session.py, requester="replanner") |
| 10 | v2 fix installed on session.py (real defect corrected) |
| 11 | Final verification: test_login PASS, test_auth PASS, probe PASS |
| 12 | **QualityGate -> COMPLETE** (all 7 conditions pass) |

## Plan A -> Plan B causal evidence

The ledger at `runs/<run_id>/evidence.jsonl` records, in causal order:

```
seq=1   request  (Plan A step, READ login.py)
seq=2   decision (ALLOW)
seq=3   evidence (policy receipt, allowed=true)
seq=4   request  (FC1: RUN_TEST on login.py)
seq=5   decision (DENY, run_test-name-pattern)
seq=6   evidence (policy receipt, allowed=false)
seq=7   request  (READ session.py)
seq=8   decision (ALLOW)
seq=9   request  (READ login.py)
seq=10  decision (ALLOW)
...     (falsifier's challenge evidence + counter-example)
seq=N   finding   (UNVERIFIED -> VERIFIED -> REFUTED)
seq=N+1 evidence  (replanner, parent=plan_a_id, plan_b=plan_b_id, new_target=session.py)
seq=N+2 request  (Plan B step, READ session.py, requested_by="replanner")
...     (final verification: test_login, test_auth, probe, regression)
seq=M   gate      (decision=complete, passed=[A..G], failed=[])
```

## QualityGate final result

```
[12] QualityGate -> COMPLETE
     passed=['A:mission-criterion', 'B:required-tests', 'C:regression',
             'D:independent-behavior-probe', 'E:scope', 'F:evidence',
             'G:finding-state']
     failed=[]
```

All 7 conditions (A..G) are satisfied using only the durable ledger.

## Anti-bypass proof

- The Runner does NOT reference `GateVerdict.COMPLETE` anywhere
  (verified by `test_demo_produces_human_readable_output`).
- The Runner does NOT construct a `COMPLETE` outcome itself; it reads
  the gate's verdict and propagates it.
- The structural grep in M5's `Wave1Isolation` still passes (no
  `from raphael.main` import).
- The M6 `test_only_quality_gate_constructs_complete` still passes (no
  other module in `raphael_bob/` constructs `GateVerdict.COMPLETE`).

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero
```

| Suite | Tests |
|---|---|
| test_seam_contracts (M1..M7 anti-claim updates) | 33 |
| test_m2_boundary (M2 regression) | 21 |
| test_m3_evidence (M3 regression) | 22 |
| test_m4_verifier_falsifier (M4 regression) | 17 |
| test_m5_replanner_runner (M5 regression) | 14 |
| test_m6_quality_gate (M6 regression) | 14 |
| test_m7_hero (M7 new) | 15 |
| **total** | **134** |

## Tests passed/failed

```
Ran 134 tests in 2.846s
OK
```

All pass; 0 failures.

## Reproducibility

The hero is reproducible: two consecutive `python3 demos/authkit_hero.py`
runs both produce `[12] QualityGate -> COMPLETE`, and the
`fixtures/authkit/session.py` file is restored to its canonical BUGGY
state after each run unless `--keep` is passed.

## Legacy components reused/adapted

| Seam | Legacy module | M7 disposition |
|---|---|---|
| Planner | `src/orchestrator/brain/action.py` (Action/Precondition/Effect) | ADAPT conceptually; **NOT imported**. M7 ships a fresh BOB-native Planner. |
| Planner | `src/raphael/cognitive/planner.py` (GreedyPlanner, UCB) | REPLACE. M7 Planner is mission-driven, not utility-driven. |
| Hero fixture | (none) | NEW. All fixture modules are fresh. |
| Independent probe | (none) | NEW. Independently authored; not derived from test_login.py / test_auth.py. |

## Remaining gaps

- The Planner is hard-coded to one symptom target per call. M8 could
  introduce a real `Planner` that inspects the mission and selects the
  target from the mission description. (The current planner takes the
  symptom target as a constructor arg, which the hero Runner passes
  directly.)
- The runner's policy for re-running after a refutation is single-pass.
  M8 could introduce a multi-replan loop if the v2 fix also fails.
- The metrics capture (M10) is not yet implemented; M7 saves
  `evidence.jsonl` + `artifacts/` but does not yet aggregate
  quantitative metrics.
- PROVENANCE.md / submission-checklist.md are M10 work.