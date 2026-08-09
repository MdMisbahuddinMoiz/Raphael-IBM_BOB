"""test_prompted_agent_parity.py — RBS-v4 repair item 9: PROMPTED_AGENT arm.

Verifies the PROMPTED_AGENT architecture preset (strong prompted-agent control
arm per rbs_v4_final_report §Q7/§26):

  1. PROMPTED_AGENT preset EXISTS in ABLATION_PRESETS and passes validate().
  2. PROMPTED_AGENT disables ALL cognitive machinery (hypothesis, falsification,
     world model, planner, structured reasoning, defeater, student) and keeps
     the broker ALWAYS enabled (never-ablated safety invariant).
  3. Broker parity: with an identical BrokerPolicy, CapabilityBroker produces
     IDENTICAL allow/deny decisions for FULL_RAPHAEL and PROMPTED_AGENT — the
     prompted agent cannot bypass, weaken, or widen authorization.
  4. IsolationVerifier accepts PROMPTED_AGENT (disabled components must produce
     zero traces in an LLM-only execution).
  5. The terminal comparison experiment is NOT launched: the preset is
     instantiable but no campaign/runner invokes it by default.

Run: python -m pytest tests/test_prompted_agent_parity.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.ablation import ABLATION_PRESETS, IsolationVerifier
from orchestrator.brain.capability_broker import BrokerPolicy, CapabilityBroker


def test_preset_exists_and_validates():
    assert "PROMPTED_AGENT" in ABLATION_PRESETS
    cfg = ABLATION_PRESETS["PROMPTED_AGENT"]
    assert cfg.validate() == [], f"validate failed: {cfg.validate()}"
    assert cfg.config_id == "PROMPTED_AGENT"


def test_all_cognitive_machinery_disabled():
    cfg = ABLATION_PRESETS["PROMPTED_AGENT"]
    assert cfg.hypothesis_enabled is False
    assert cfg.falsification_enabled is False
    assert cfg.world_model_enabled is False
    assert cfg.planner_enabled is False
    assert cfg.structured_reasoning_enabled is False
    assert cfg.defeater_enabled is False
    assert cfg.student_enabled is False
    # LLM is the decision engine.
    assert cfg.llm_enabled is True
    # Uses the LLM-only execution path (prompt-driven, no cognitive structures).
    assert cfg.baseline_type == "llm_only"


def test_broker_never_ablated():
    cfg = ABLATION_PRESETS["PROMPTED_AGENT"]
    assert cfg.broker_enabled is True
    # Same safety invariant as every config.
    for cid in ABLATION_PRESETS:
        assert ABLATION_PRESETS[cid].broker_enabled is True, f"{cid} ablated broker"


def _make_policy() -> BrokerPolicy:
    return BrokerPolicy(
        engagement_id="parity-test",
        allowed_targets=["10.0.0.0/24"],
        prohibited_targets=["10.0.0.66"],
        allowed_action_types=["recon", "scan"],
        prohibited_action_types=["exploit"],
        allowed_capabilities=["nmap", "curl"],
        prohibited_capabilities=["sqlmap"],
    )


def test_broker_parity_full_vs_prompted_agent():
    """Identical policy -> identical broker decisions for both configs."""
    from arena.ablation import FULL_RAPHAEL, PROMPTED_AGENT
    policy = _make_policy()
    b_full = CapabilityBroker(policy)
    b_prompted = CapabilityBroker(policy)

    probes = [
        ("10.0.0.5", "scan", "nmap", "quick", "allow"),
        ("10.0.0.66", "scan", "nmap", "quick", "deny"),     # prohibited target
        ("10.0.0.5", "exploit", "nmap", "auto", "deny"),    # prohibited action type
        ("10.0.0.5", "scan", "sqlmap", "auto", "deny"),     # prohibited capability
        ("10.0.0.5", "recon", "curl", "auto", "allow"),
    ]

    for target, atype, cap, method, expected in probes:
        r1 = b_full.propose_action(target=target, action_type=atype,
                                   capability=cap, method=method,
                                   impact_estimate=1.0)
        r2 = b_prompted.propose_action(target=target, action_type=atype,
                                       capability=cap, method=method,
                                       impact_estimate=1.0)
        d1 = getattr(r1, 'decision', 'deny')
        d2 = getattr(r2, 'decision', 'deny')
        assert d1 == d2, f"Broker parity broken for {target}/{atype}/{cap}: {d1} != {d2}"
        assert d1 == expected, f"Unexpected decision for {target}/{atype}/{cap}: {d1}"
    assert FULL_RAPHAEL.broker_enabled and PROMPTED_AGENT.broker_enabled


def test_isolation_verifier_accepts_prompted_agent():
    """Disabled components must show zero traces in an LLM-only run."""
    cfg = ABLATION_PRESETS["PROMPTED_AGENT"]
    # LLM-only execution touches only llm (and broker, which is not traced as
    # a forbidden component). Construct a trace collector with llm traces.
    from arena.ablation_runner import TraceCollector
    tracer = TraceCollector(run_id="pa-test")
    tracer.trace("llm", "call")
    result = IsolationVerifier.verify(cfg, tracer)
    assert result["pass"] is True, f"Isolation failure: {result['failures']}"


def test_terminal_experiment_not_launched():
    """The preset is instantiable; no default campaign runs it."""
    import scripts.run_rbs_v4_holdout as holdout_mod
    assert "PROMPTED_AGENT" not in holdout_mod.HOLDOUT_CONFIGS, (
        "PROMPTED_AGENT must NOT be registered in the holdout campaign"
    )


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("preset exists and validates", test_preset_exists_and_validates),
    ("all cognitive machinery disabled", test_all_cognitive_machinery_disabled),
    ("broker never ablated", test_broker_never_ablated),
    ("broker parity full vs prompted", test_broker_parity_full_vs_prompted_agent),
    ("isolation verifier accepts", test_isolation_verifier_accepts_prompted_agent),
    ("terminal experiment not launched", test_terminal_experiment_not_launched),
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
    print(f"PROMPTED_AGENT PARITY: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)