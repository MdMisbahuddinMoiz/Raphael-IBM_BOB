M8 commit: a19fcc30c
Changed files:
- raphael_bob/runner.py
- raphael_bob/__init__.py
- tests/test_m5_replanner_runner.py
- tests/test_m6_quality_gate.py
Why each changed:
- raphael_bob/runner.py: Removed the PlannerStub class, updated the Runner to accept a Planner (or default Planner) and fixed the __init__ to assign the store. The Runner now calls planner.plan_a(mission) without injecting a target.
- raphael_bob/__init__.py: Removed PlannerStub from the public API and adjusted imports.
- tests/test_m5_replanner_runner.py: Updated the _mission helper to include the required 'description' field and changed the import from PlannerStub to Planner.
- tests/test_m6_quality_gate.py: Updated the _mission helper to include the required 'description' and 'problem' fields.
Planner behavior before:
- M7 Planner accepted a symptom_target via constructor (passed by the Runner), creating a hidden dependency where the Runner supplied the target.
- The PlannerStub (used as fallback) targeted a fixed directory ("src/") and ignored the mission.
Planner behavior after:
- The Planner is now mission-driven: its plan_a(mission) method reads mission.problem["symptom_target"] (and optionally capability and purpose) to construct the ActionRequest.
- The Planner has no constructor arguments; all configuration comes from the Mission.
How mission now determines Plan A:
- The Planner.plan_a(mission) extracts:
    target = mission.problem.get("symptom_target")
    capability_str = mission.problem.get("capability", "read") -> mapped to Capability enum
    purpose = mission.problem.get("purpose", f"plan-a:probe:{target}")
- It then creates a single-step Plan with an ActionRequest for READ (or specified capability) against that target.
Proof Runner no longer injects target:
- The Runner.__init__ signature no longer includes a target argument.
- The Runner.run method passes only the mission to planner.plan_a(mission).
- Tests: test_runner_does_not_construct_planner_with_target and test_runner_does_not_supply_target_directly verify that the Runner does not pass a target to the Planner.
Determinism proof:
- For identical Missions, plan_a(mission) returns byte-identical Plan A (same plan_id and same ActionRequest).
- Verified by test_planner_is_deterministic.
Different-mission proof:
- Changing mission.problem["symptom_target"] changes the target in the generated Plan A.
- Verified by test_different_missions_produce_different_targets.
Full test result:
- Ran the BOB MVP test suite (m2 through m8 plus seam contracts): 147 tests passed.
M7 hero regression result:
- The authkit hero demo runs successfully twice, reaching QualityGate -> COMPLETE each time (see test output in test_m8_planner.HeroRegressionAfterM8).
Remaining UNKNOWN:
- M9 (multi-replan) and M10 (metrics) are not addressed in M8, as intended.
M9 readiness:
- The Planner remains focused on generating only Plan A from the Mission.
- The Replanner remains the sole generator of Plan B.
- No changes were made that would impede multi-replan in M9; the architecture preserves the separation Planner → Plan A, Replanner → Plan B.
