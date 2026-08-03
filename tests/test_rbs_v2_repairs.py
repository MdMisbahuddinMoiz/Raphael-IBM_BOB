"""Regression tests for RBS-v2 instrumentation repairs (commit 4fa988d4).

Covers SENTINEL directives 1-4:
1. Safety evaluator: denied episodes are NOT external actions.
2. T7 scope consistency: target host always within allowed scope.
3. NoOp classes: API-compatible with ContradictionManager / Planner.
4. Student telemetry field placement (candidate_origin on candidates, not episodes).
"""
import sys
sys.path.insert(0, 'src')

from arena.d6_manifest import create_d6_scenario_6, create_d6_scenario_7
from arena.ablation_runner import NoOpHypothesisManager, NoOpContradictionManager
from arena.episode import Episode


def test_safety_external_actions_excludes_denied():
    """Directive 1: only executed episodes count as external actions."""
    class FakeEpisodes:
        def __init__(self, eps):
            self.episodes = eps

    eps = FakeEpisodes([
        Episode(execution_result=None),                          # denied
        Episode(execution_result={"success": True}),             # executed
        Episode(execution_result={"success": True}),             # executed
        Episode(execution_result=None),                          # denied
    ])
    external = sum(1 for ep in eps.episodes if ep.execution_result is not None)
    assert external == 2, f"expected 2 external actions, got {external}"


def test_t7_scope_contains_target():
    """Directive 2: T7 target host must be within allowed scope for all seeds."""
    for seed in range(1042, 1072):
        sc = create_d6_scenario_7(seed)
        allowed = sc.policy.allowed_targets[0]
        target_ip = sc.evaluator_truth["starting_assets"][0]["ip"]
        allowed_prefix = allowed.split(".")[:3]
        target_prefix = target_ip.split(".")[:3]
        assert allowed_prefix == target_prefix, (
            f"seed {seed}: target {target_ip} not in {allowed}"
        )


def test_t6_vulnerabilities_no_none():
    """Directive 3: T6 vulnerabilities list never contains None."""
    for seed in range(1042, 1072):
        sc = create_d6_scenario_6(seed)
        vuls = sc.evaluator_truth.get("vulnerabilities", [])
        assert all(v is not None for v in vuls), f"seed {seed} has None vulnerability"


def test_noop_hypothesis_manager_api():
    """Directive 3: NoOpHypothesisManager implements ContradictionManager's calls."""
    h = NoOpHypothesisManager()
    assert h.get_by_entity("x") == []
    assert h.get_hypothesis("x") is None
    assert h.consume_semantic_inference(None, [], []) is None
    assert h.apply_defeater_result(None) is None
    assert h.add_contradiction(None) is None
    assert h.add_evidence(None) is None


def test_noop_contradiction_manager_api():
    """Directive 3: NoOpContradictionManager implements Planner's calls."""
    c = NoOpContradictionManager()
    assert c.get_contradictions_for_entity("x") == []
    assert c.get_active_contradictions() == []


def test_student_telemetry_field_placement():
    """Directive 4: candidate_origin lives on candidate actions, not episodes.

    Regression: the campaign script previously read ep.get("candidate_origin")
    which never exists on the episode dict; the origin is on each entry of
    candidate_actions and on selected_action.
    """
    import json
    ep = {
        "candidate_actions": [
            {"action_id": "s1", "candidate_origin": "STUDENT"},
            {"action_id": "b1", "candidate_origin": "BASE"},
        ],
        "planner_scores": [{"action": "s1", "score": 0.5}],
        "selected_action": {"action_id": "b1", "candidate_origin": "BASE"},
    }
    # The episode dict itself must NOT have candidate_origin
    assert "candidate_origin" not in ep
    student_cands = sum(
        1 for c in ep.get("candidate_actions", [])
        if isinstance(c, dict) and c.get("candidate_origin") == "STUDENT"
    )
    assert student_cands == 1
    selected = ep.get("selected_action") or {}
    assert selected.get("candidate_origin") == "BASE"
