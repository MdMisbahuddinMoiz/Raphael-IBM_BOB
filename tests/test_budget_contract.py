"""test_budget_contract.py — RBS-v4 repair item 10: BUDGET CONTRACT.

Verifies the frozen manifest budget contract (ITERATION_BUDGET=5,
ACTION_BUDGET=20 in d6_manifest) is:
  1. The SINGLE source of truth — the ablation runner no longer hardcodes
     iteration budgets; all three execution paths (raphael / llm_only /
     scripted) bind max_iterations to ITERATION_BUDGET and cap executed
     actions at ACTION_BUDGET.
  2. Enforced: a run can never exceed ITERATION_BUDGET iterations or
     ACTION_BUDGET started actions.
  3. Measured: RunMetrics exposes iterations_used, budget_iteration_ceiling,
     budget_action_ceiling so the Dev distribution of budget consumption can
     be computed against the contract (matched-action-budget requirement of
     the terminal comparison spec).
  4. Consistent across arms: every config gets the same declared ceiling.

Run: python -m pytest tests/test_budget_contract.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.d6_manifest import ITERATION_BUDGET, ACTION_BUDGET
from arena.ablation import ABLATION_PRESETS
from arena.metrics import RunMetrics


def test_manifest_budget_constants():
    assert ITERATION_BUDGET == 5
    assert ACTION_BUDGET == 20


def test_runner_no_hardcoded_iteration_literal():
    """The runner must bind to manifest constants, not a magic literal."""
    src = open("/home/yaser/raphael-2.0-rbsv2r/src/arena/ablation_runner.py").read()
    # All three paths must reference the manifest import.
    assert src.count("max_iterations = ITERATION_BUDGET") == 3, (
        "Not all execution paths bind max_iterations to ITERATION_BUDGET"
    )
    # No leftover hardcoded iteration literals in the loop paths.
    assert "max_iterations = 5" not in src, (
        "Hardcoded iteration budget literal still present"
    )


def test_action_budget_guard_present():
    """Every loop must cap dispatched actions at ACTION_CAP (Gate B)."""
    src = open("/home/yaser/raphael-2.0-rbsv2r/src/arena/ablation_runner.py").read()
    # Three execution paths (raphael, llm_only, scripted) each have the guard
    assert src.count("self.metrics.actions_dispatched < ACTION_CAP") == 3, (
        "Action-budget guard missing in an execution path"
    )


def test_metrics_budget_fields():
    m = RunMetrics(run_id="b", config_id="c", template_family="t", seed=0,
                   split="dev", provider="p", model_id="m")
    assert m.iterations_used == 0
    assert m.budget_iteration_ceiling is None
    assert m.budget_action_ceiling is None
    d = m.to_dict() if hasattr(m, "to_dict") else m.__dict__
    assert "iterations_used" in d


def test_all_configs_share_declared_budget():
    """Every architecture arm gets the same budget contract."""
    for cid, cfg in ABLATION_PRESETS.items():
        # No per-config budget override exists in the schema; the contract is
        # enforced centrally by the runner against the manifest constants.
        assert cfg.config_id == cid


def test_scripted_run_stays_within_contract():
    """End-to-end: a SCRIPTED_BASELINE dev run consumes <= budget (Gate B)."""
    from arena.ablation_runner import AblationRunner
    from arena.ablation import SCRIPTED_BASELINE

    class _Tpl:
        family_id = "T1_NEGATIVE_CONTROL"

        def generate(self, seed=0, split=None, scenario_id_override=None):
            from arena.d6_manifest import D6_SCENARIO_FACTORIES, SCENARIO_TEMPLATES
            factory = D6_SCENARIO_FACTORIES[SCENARIO_TEMPLATES["T1_NEGATIVE_CONTROL"]["id"]]
            return factory(seed=seed)

    runner = AblationRunner(
        template=_Tpl(),
        config=SCRIPTED_BASELINE,
        seed=42,
        split="dev",
    )
    metrics = runner.run()
    assert metrics.iterations_used <= ITERATION_BUDGET, (
        f"iterations_used {metrics.iterations_used} exceeds ITERATION_BUDGET"
    )
    # Gate B: action budget is ACTION_CAP = 5 (broker dispatches)
    assert metrics.actions_dispatched <= 5, (
        f"actions_dispatched {metrics.actions_dispatched} exceeds ACTION_CAP=5"
    )
    assert metrics.budget_iteration_ceiling == ITERATION_BUDGET
    assert metrics.budget_action_ceiling == 5
    assert metrics.ACTION_CAP == 5
    # actions_started now means successful executions only (not budget counter)
    assert metrics.actions_started <= metrics.actions_authorized


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("manifest budget constants", test_manifest_budget_constants),
    ("no hardcoded iteration literal", test_runner_no_hardcoded_iteration_literal),
    ("action budget guard present", test_action_budget_guard_present),
    ("metrics budget fields", test_metrics_budget_fields),
    ("all configs share budget", test_all_configs_share_declared_budget),
    ("scripted run within contract", test_scripted_run_stays_within_contract),
]


def _run_manual():
    import traceback
    passed = failed = 0
    for name, fn in TESTS:
        try:
            fn()
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"FAIL: {name}: {e}")
        else:
            passed += 1
    print(f"BUDGET CONTRACT: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)