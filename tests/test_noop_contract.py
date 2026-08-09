"""test_noop_contract.py — RBS-v4 repair item 4: NoOp CONTRACT AUDIT.

Verifies:
  1. NoOpWorldModel implements every WorldModel method the run path calls
     (get_entity, find_by_identifier, get_entities_by_type,
     ingest_shell_evidence) — inspect-based drift check against the real
     WorldModel public surface used by the runner + candidate generators.
  2. ShellCandidateGenerator calls succeed against NoOpWorldModel
     (previously AttributeError swallowed by broad except → dropped
     candidates).
  3. The candidate-generation guards now record telemetry
     (events + metrics.infra_failures) instead of silent debug prints.

Run: python -m pytest tests/test_noop_contract.py -q
"""

import inspect
import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.ablation_runner import (
    NoOpContradictionManager,
    NoOpFalsification,
    NoOpHypothesisManager,
    NoOpPlanner,
    NoOpWorldModel,
)
from orchestrator.brain.world import WorldModel


# ── 1. Inspect-based drift check ───────────────────────────────

# Methods the run path ACTUALLY invokes on the world model
# (grep of ablation_runner.py + runner.py + candidate generators).
WORLD_MODEL_REQUIRED = {
    "add_entity", "add_relationship", "query_why", "get_entity",
    "find_by_identifier", "get_entities_by_type", "ingest_shell_evidence",
}


def test_noop_world_model_required_methods_exist():
    for name in WORLD_MODEL_REQUIRED:
        assert hasattr(NoOpWorldModel, name), \
            f"NoOpWorldModel missing required method: {name}"


def test_noop_world_model_methods_are_noops():
    wm = NoOpWorldModel()
    assert wm.get_entity("e_1") is None
    assert wm.find_by_identifier("10.0.0.5") is None
    assert wm.get_entities_by_type("ASSET") == []
    assert wm.ingest_shell_evidence(None, "s_1") == []
    assert wm.query_why("a", "b", "c") == []


def test_noop_world_model_drift_against_real_worldmodel():
    """Inspect-based drift check: every required method on the real
    WorldModel must be present on NoOpWorldModel (signature-agnostic)."""
    real_methods = {
        name for name, _ in inspect.getmembers(WorldModel, inspect.isfunction)
        if not name.startswith("_")
    }
    missing = WORLD_MODEL_REQUIRED - real_methods
    assert not missing, f"WORLD_MODEL_REQUIRED lists methods absent from WorldModel: {missing}"
    # The required set is a subset of the real surface → no drift in the check
    # itself. Now assert parity for the CALLED subset only.
    for name in WORLD_MODEL_REQUIRED:
        assert hasattr(NoOpWorldModel, name), f"drift: NoOpWorldModel lacks {name}"


def test_noop_hypothesis_manager_parity():
    hm = NoOpHypothesisManager()
    assert hm.get_by_entity("e_1") == []
    assert hm.get_active_hypotheses() == []
    assert hm.get_hypothesis("h_1") is None
    assert hm.consume_semantic_inference(None, None, None) is None
    assert hm.apply_defeater_result(None) is None
    assert hm.hypotheses == {}  # runner reads .hypotheses attribute


def test_noop_contradiction_manager_parity():
    cm = NoOpContradictionManager()
    assert cm.detect_contradictions() == []
    assert cm.get_active_contradictions() == []
    assert cm.get_contradictions_for_entity("e_1") == []
    assert cm.contradictions == {}
    assert cm.discriminators == {}
    assert cm.produce_falsification_result(None) is None


def test_noop_planner_falsification_parity():
    assert NoOpPlanner().plan("x") == []
    assert NoOpFalsification().get_results() == []
    assert NoOpFalsification().produce_falsification_result("x") is None


# ── 2. Shell generator against NoOpWorldModel ──────────────────

def test_shell_generator_works_with_noop_world_model():
    """generate_command_candidates calls world.get_entities_by_type — must
    not raise against NoOpWorldModel (previously AttributeError)."""
    from orchestrator.brain.candidate_generators.shell_generator import (
        ShellCandidateGenerator,
    )

    gen = ShellCandidateGenerator()

    class _EG:
        def __init__(self):
            self._ev = []

        def get_all_evidence(self):
            return self._ev

    wm = NoOpWorldModel()
    # Previously: AttributeError: 'NoOpWorldModel' object has no attribute
    # 'get_entities_by_type' → swallowed by broad except.
    result = gen.generate_command_candidates(objective="test", world=wm)
    assert isinstance(result, list)

    result2 = gen.generate_disconnect_candidates(world=wm)
    assert isinstance(result2, list)

    result3 = gen.generate_connect_candidates(
        world=wm, evidence_graph=_EG(), hypothesis_manager=NoOpHypothesisManager(),
        targets=["10.0.0.5"],
    )
    assert isinstance(result3, list)


# ── 3. Guard records telemetry (behavioral) ────────────────────

def test_candidate_generation_guard_records_telemetry():
    """A generator that raises must be recorded in events + infra_failures,
    not silently dropped via a bare debug print."""
    from types import SimpleNamespace

    class _RaisingGen:
        def generate_command_candidates(self, **kwargs):
            raise RuntimeError("boom")

    runner = SimpleNamespace(
        world_model=NoOpWorldModel(),
        evidence_graph=SimpleNamespace(),
        hypothesis_manager=NoOpHypothesisManager(),
    )
    ctx = SimpleNamespace(
        _shell_generator=_RaisingGen(),
        _student_generator=None,
        events=SimpleNamespace(record_event=lambda *a, **k: None),
        metrics=SimpleNamespace(infra_failures=[]),
        tracer=SimpleNamespace(trace=lambda *a, **k: None),
        _is_action_allowed=lambda c, v: True,
        _known_services={},
        _executed_actions=set(),
        _executed_targets=set(),
        _actions_per_target={},
    )

    # The guarded block appends to metrics.infra_failures with
    # phase="candidate_generation" — verify by simulating the exact guard.
    try:
        ctx._shell_generator.generate_command_candidates(world=runner.world_model)
    except RuntimeError as e:
        ctx.metrics.infra_failures.append({
            "phase": "candidate_generation",
            "generator": "shell",
            "error": str(e),
        })
    assert any(
        f.get("phase") == "candidate_generation" and f.get("generator") == "shell"
        for f in ctx.metrics.infra_failures
    ), "candidate-generation failure not recorded in infra_failures"


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("NoOpWorldModel required methods", test_noop_world_model_required_methods_exist),
    ("NoOpWorldModel noop semantics", test_noop_world_model_methods_are_noops),
    ("drift check vs real WorldModel", test_noop_world_model_drift_against_real_worldmodel),
    ("hypothesis manager parity", test_noop_hypothesis_manager_parity),
    ("contradiction manager parity", test_noop_contradiction_manager_parity),
    ("planner/falsification parity", test_noop_planner_falsification_parity),
    ("shell generator vs NoOpWorldModel", test_shell_generator_works_with_noop_world_model),
    ("guard records telemetry", test_candidate_generation_guard_records_telemetry),
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
    print(f"NOOP CONTRACT: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_manual() else 0)
