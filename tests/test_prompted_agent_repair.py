"""test_prompted_agent_repair.py — SENTINEL REPAIR-DEV-01 acceptance tests (A–J).

Verifies that PROMPTED_AGENT now uses the REAL LLMService/provider path
(no TracedLLM simulation, no candidates[0] fallback) with provider-reported
token telemetry and broker-gated dispatch.

Acceptance mapping (SENTINEL mandate):
  A. Real-call proof wiring: llm_calls > 0, provider-reported tokens > 0
  B. Model identity: FULL.model_id == PROMPTED.model_id == amended default
  C. Broker parity: same CapabilityBroker implementation/authorization path
  D. Environment parity: same scenario + initial observations for matched seed
  E. Cognitive isolation: no WorldModel/Planner/Hypothesis/Student/Falsification
  F. Action accounting: actions_dispatched <= 5 and == authorized + denied
  G. Parser failure: malformed LLM output -> model_failure, NO deterministic
     fallback (no dispatch), iteration consumed
  H. Token accounting: provider usage == RunMetrics token totals
  I. Forced-denial: denial returned as textual observation, consumes action
  J. Regression suite green (run separately: python -m pytest tests -q)

Network isolation: LLM-enabled runs use a FakeLLMService (deterministic,
zero network) injected via runner.llm_service. Model identity tests only
construct runners (LLMService ctor performs no network I/O).

Run: python -m pytest tests/test_prompted_agent_repair.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

import pytest
from types import SimpleNamespace

from arena.ablation import ABLATION_PRESETS
from arena.ablation_runner import (
    AblationRunner,
    NoOpWorldModel,
    NoOpHypothesisManager,
    NoOpContradictionManager,
)
from arena.llm_service import SemanticInferenceSuccess, SemanticInferenceFailure
from arena.semantic_inference import InferenceCategory
from arena.metrics import RunMetrics
from arena.runner import SCENARIO_EVALUATORS as _GLOBAL_EVALUATORS
from arena.d6_manifest import D6_SCENARIO_EVALUATORS
from arena.environment import ScenarioEnvironment
from orchestrator.brain.capability_broker import CapabilityBroker
from orchestrator.brain.world import WorldModel
from orchestrator.brain.hypothesis import HypothesisManager
from orchestrator.brain.contradiction import ContradictionManager

# Register D-6 scenario evaluators (same as campaign runners) so _evaluate()
# scores template scenarios with the architecture-blind structural evaluator.
_GLOBAL_EVALUATORS.update(D6_SCENARIO_EVALUATORS)

AMENDED_MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
AMENDED_PROVIDER = "nvidia"

VALID_ACTION = {
    "action_type": "recon",
    "target": "PLACEHOLDER",  # replaced with in-scope target in fixtures
    "capability": "nmap",
    "method": "quick",
}


class _Tpl:
    """Native T1_NEGATIVE_CONTROL template (real scenario + real policy)."""
    family_id = "T1_NEGATIVE_CONTROL"

    def generate(self, seed=0, split=None, scenario_id_override=None):
        from arena.d6_manifest import D6_SCENARIO_FACTORIES, SCENARIO_TEMPLATES
        factory = D6_SCENARIO_FACTORIES[SCENARIO_TEMPLATES["T1_NEGATIVE_CONTROL"]["id"]]
        return factory(seed=seed)


class FakeLLMService:
    """Deterministic LLMService stand-in: same interface, zero network.

    Records per-call observation_text so tests can assert that denials and
    failures are returned to the LLM as textual context.
    """

    def __init__(self, responses, input_per_call=100, output_per_call=20,
                 model_id=AMENDED_MODEL_ID, provider=AMENDED_PROVIDER):
        self.responses = list(responses)
        self.input_per_call = input_per_call
        self.output_per_call = output_per_call
        self.call_count = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.provider_failures = 0
        self.envelope_failures = 0
        self.config = SimpleNamespace(model_id=model_id, provider=provider)
        self.calls = []  # (observation_text, source_evidence_ids, run_id)

    def run_inference(self, observation_text, source_evidence_ids, run_id=""):
        self.call_count += 1
        self.input_tokens += self.input_per_call
        self.output_tokens += self.output_per_call
        self.calls.append((observation_text, source_evidence_ids, run_id))
        if self.responses:
            item = self.responses.pop(0)
        else:
            item = {"claim": VALID_ACTION_JSON(), "category": "state_description", "confidence": 0.9}
        if item == "PROVIDER_FAILURE":
            self.provider_failures += 1
            return SemanticInferenceFailure(
                attempt_id=f"si_fail_{self.call_count:08x}",
                source_evidence_ids=tuple(source_evidence_ids),
                failure_type="provider_timeout",
                provider=self.config.provider,
                model_id=self.config.model_id,
                timestamp=0.0,
                diagnostic_detail="fake timeout",
            )
        if isinstance(item, dict) and "claim" in item:
            return SemanticInferenceSuccess(
                inference_id=f"si_test{self.call_count:08x}",
                source_evidence_ids=tuple(source_evidence_ids),
                model_id=self.config.model_id,
                provider=self.config.provider,
                timestamp=0.0,
                claim=item["claim"],
                category=InferenceCategory.STATE_DESCRIPTION,
                confidence=0.9,
            )
        raise AssertionError(f"unhandled fake response item: {item!r}")


def VALID_ACTION_JSON(target=None):
    d = dict(VALID_ACTION)
    if target:
        d["target"] = target
    import json as _json
    return _json.dumps(d)


def _scenario():
    tpl = _Tpl()
    return tpl.generate(seed=0), tpl


def _in_scope_target(scenario):
    view = scenario.engagement_view()
    allowed = view.get("allowed_scope", [])
    if isinstance(allowed, str):
        return allowed
    return allowed[0]


def _make_runner(config_id, scenario, tpl, seed=0, fake=None):
    runner = AblationRunner(
        template=tpl,
        config=ABLATION_PRESETS[config_id],
        seed=seed,
        split="dev",
    )
    if fake is not None:
        runner.llm_service = fake  # injected before run(); _run_llm_only reads it
    return runner


# ── A. Real-call proof (wiring) ─────────────────────────────────────────
def test_A_real_calls_and_provider_tokens():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService([{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert fake.call_count > 0, "PROMPTED_AGENT must call the LLM service"
    assert metrics.llm_calls > 0
    assert metrics.input_tokens > 0 and metrics.output_tokens > 0
    assert metrics.provider_failures == 0


# ── B. Model identity ────────────────────────────────────────────────────
def test_B_model_identity_matches_amended_default():
    scenario, tpl = _scenario()
    # Constructor-only: LLMService ctor performs no network I/O.
    r_full = _make_runner("FULL_RAPHAEL", scenario, tpl)
    r_prompted = _make_runner("PROMPTED_AGENT", scenario, tpl)
    assert r_full.llm_service.config.model_id == AMENDED_MODEL_ID
    assert r_prompted.llm_service.config.model_id == AMENDED_MODEL_ID
    assert r_full.llm_service.config.model_id == r_prompted.llm_service.config.model_id
    assert r_full.llm_service.config.provider == r_prompted.llm_service.config.provider == AMENDED_PROVIDER
    # After a run, metrics.model_id comes from the real service config (sync path).
    target = _in_scope_target(scenario)
    fake = FakeLLMService([{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert metrics.model_id == AMENDED_MODEL_ID
    assert metrics.provider == AMENDED_PROVIDER


# ── C. Broker parity ─────────────────────────────────────────────────────
def test_C_broker_parity():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService([{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    runner.run()
    assert isinstance(runner._broker_for_safety, CapabilityBroker), \
        "PROMPTED_AGENT must dispatch through the identical CapabilityBroker"


# ── D. Environment parity ───────────────────────────────────────────────
def test_D_environment_parity_matched_seed():
    scenario_a, _ = _scenario()
    scenario_b, _ = _scenario()
    va, vb = scenario_a.engagement_view(), scenario_b.engagement_view()
    assert va["objective"] == vb["objective"]
    assert va["allowed_scope"] == vb["allowed_scope"]
    oa = ScenarioEnvironment(scenario_a).create_initial_observations()
    ob = ScenarioEnvironment(scenario_b).create_initial_observations()
    assert [o.raw_output for o in oa] == [o.raw_output for o in ob], \
        "matched seed must yield identical initial observations"


# ── E. Cognitive isolation ──────────────────────────────────────────────
def test_E_cognitive_isolation():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService([{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    ar = runner.arena_runner
    assert isinstance(ar.world_model, NoOpWorldModel)
    assert isinstance(ar.hypothesis_manager, NoOpHypothesisManager)
    assert isinstance(ar.contradiction_manager, NoOpContradictionManager)
    for comp in ["hypothesis", "falsification", "world_model", "planner", "student"]:
        assert metrics.component_traces.get(comp, 0) == 0, \
            f"PROMPTED_AGENT touched forbidden component: {comp}"
    assert metrics.isolation_pass is True


# ── F. Action accounting ────────────────────────────────────────────────
def test_F_action_accounting():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService([{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert metrics.actions_dispatched <= 5
    assert metrics.actions_dispatched == metrics.actions_authorized + metrics.actions_denied
    assert metrics.actions_dispatched == metrics.ACTION_CAP == 5


# ── G. Parser failure: NO deterministic fallback ────────────────────────
def test_G_malformed_output_no_fallback():
    scenario, tpl = _scenario()
    malformed = {"claim": "I think we should try harder with the scanning thing",
                 "category": "state_description", "confidence": 0.5}
    fake = FakeLLMService([malformed] * 5)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert fake.call_count > 0, "LLM must be consulted even when it fails to parse"
    assert metrics.model_failures > 0, "malformed output must be counted as model failure"
    assert metrics.actions_dispatched == 0, \
        "malformed LLM output MUST NOT fall back to a deterministic action"
    assert metrics.actions_denied == 0 and metrics.actions_authorized == 0
    assert metrics.iterations_used == 5, "5 malformed outputs consume the 5 iterations"
    # No action evidence was created beyond the initial observations.
    ev_created = metrics.pipeline_coverage.get("evidence_creation_count", 0)
    init_count = len(ScenarioEnvironment(scenario).create_initial_observations())
    assert ev_created <= init_count, "no action may execute from malformed output"


# ── H. Token accounting: provider usage == RunMetrics totals ────────────
def test_H_token_accounting_matches_provider():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService(
        [{"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 5,
        input_per_call=100, output_per_call=20,
    )
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert fake.call_count == 5
    assert metrics.input_tokens == fake.input_tokens == 500
    assert metrics.output_tokens == fake.output_tokens == 100
    assert metrics.llm_calls == fake.call_count


# ── I. Forced-denial: textual observation + consumes action ─────────────
def test_I_forced_denial_returned_as_text():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    # First action targets an out-of-scope address -> broker denies.
    deny_action = {"claim": VALID_ACTION_JSON("10.99.99.99"),
                   "category": "state_description", "confidence": 0.9}
    allow_action = {"claim": VALID_ACTION_JSON(target),
                    "category": "state_description", "confidence": 0.9}
    fake = FakeLLMService([deny_action, allow_action, allow_action, allow_action, allow_action])
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert metrics.actions_denied == 1
    assert metrics.actions_dispatched >= 1
    assert metrics.actions_dispatched == metrics.actions_authorized + metrics.actions_denied
    # The denial must be visible to the LLM in the NEXT call's text.
    assert len(fake.calls) >= 2
    assert "DENIED" in fake.calls[1][0], \
        "denial must be returned to the LLM as textual observation"


# ── Provider failure separation (supports item 12) ──────────────────────
def test_provider_failure_separate_from_model_failure():
    scenario, tpl = _scenario()
    target = _in_scope_target(scenario)
    fake = FakeLLMService(["PROVIDER_FAILURE"] + [
        {"claim": VALID_ACTION_JSON(target), "category": "state_description", "confidence": 0.9}] * 4)
    runner = _make_runner("PROMPTED_AGENT", scenario, tpl, fake=fake)
    metrics = runner.run()
    assert metrics.provider_failures == 1
    assert metrics.model_failures == 0
    assert fake.provider_failures == metrics.provider_failures


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
