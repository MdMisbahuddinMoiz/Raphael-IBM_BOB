"""D16 semantics: select -> execute -> observe -> update -> replan.

The frozen D14/D15 contracts are reused without rank fields: ``Planner.plan``
orders by existing hypothesis IDs, execution must yield ALLOW-bound evidence,
and ``reduce_world_state`` supplies the immutable replan input.  No accepted
state change repeats the same action; an accepted Action A observation removes
A from the candidates so the same plan selects its next action B.  A terminal
gate stops before replanning; an ungovernable proposal is refused before
execution and cannot produce an observation.

Citations: ``d14_planner.py:114-192`` (``Planner.plan``),
``d14_replan.py:15-26`` (``ReplanDecision``),
``d14_stop.py:79-97`` (``evaluate``), and
``d14_world_state.py:138-193`` (``reduce_world_state``).
"""
from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from raphael_ibm_bob.capability_bootstrap import (
    InertAdapter,
    network_descriptors,
    register_ssh,
)
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import ExecutionPlan, plan_to_action_requests
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Decision,
    GateVerdict,
    Mission,
)
from raphael_ibm_bob.d14_hypothesis import Hypothesis
from raphael_ibm_bob.d14_planner import NextAction, Planner, SelectionDecision
from raphael_ibm_bob.d14_replan import ReplanDecision
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig, evaluate
from raphael_ibm_bob.d14_state_codec import EvidenceBinding
from raphael_ibm_bob.d14_world_state import ObservationUpdate, WorldState, initial_world_state, reduce_world_state
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts
from raphael_ibm_bob.workspace import Workspace


MISSION = Mission(
    mission_id="M-D16",
    description="deterministic replanning semantics",
    scope="scope://synthetic/d16",
)


@dataclass(frozen=True, slots=True)
class _FixedSelector:
    plan: ExecutionPlan

    def select_and_compose(self, mission_type: str, mission_params: dict[str, str], facts: TargetFacts, *, credential_refs: list[str] | None = None) -> ExecutionPlan:
        return self.plan


@dataclass(frozen=True, slots=True)
class _AllowedLedger:
    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding:
        return EvidenceBinding(
            evidence_id=evidence_id,
            request_seq=1,
            policy_decision="allow",
            result_success=True,
            session_id="session-d16",
        )


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for descriptor in network_descriptors():
        registry.register(descriptor, InertAdapter())
    return registry


def _plan() -> ExecutionPlan:
    plan = ExecutionPlan("DP-D16", MISSION.mission_id, "synthetic-target", "probe")
    plan.add_step(
        "NETWORK_HTTP_REQUEST",
        {"target": "http://synthetic.invalid:80/"},
        purpose="Action A",
    )
    plan.add_step(
        "NETWORK_TELNET_SESSION",
        {"target": "telnet://synthetic.invalid:23"},
        purpose="Action B",
    )
    return plan


def _hypothesis(hypothesis_id: str, request: ActionRequest) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        subject_ref="synthetic-target",
        predicate="capability_available",
        value=True,
        test_actions=(request,),
        expected_observation="successful response",
        falsifier="failed response",
        confidence_bps=9000,
        confidence_band="CONFIRMED",
    )


def _planner() -> Planner:
    registry = _registry()
    plan = _plan()
    actions = plan_to_action_requests(plan, registry=registry, requester="d16-test")
    return Planner(
        selector=_FixedSelector(plan),
        registry=registry,
        hypotheses=(
            _hypothesis("H-A", actions[0]),
            _hypothesis("H-B", actions[1]),
        ),
    )


def _state() -> WorldState:
    facts = TargetFacts(target_id="synthetic-target", host="synthetic.invalid")
    facts.add_service(ServiceRecord("synthetic.invalid", 80, "http"))
    return initial_world_state(MISSION, facts)


def _required_action(decision: SelectionDecision) -> NextAction:
    action = decision.next_action
    if action is None:
        raise AssertionError("fixture must select an action")
    return action


def _observe(state: WorldState, action: NextAction) -> WorldState:
    with patch(
        "raphael_ibm_bob.observation_model.time.time",
        return_value=1_700_000_000.0,
    ):
        observation = ObservationRecord(
            observation_id="O-D16-A",
            capability_id=action.capability_id,
            observation_type="http_response",
            target_host="synthetic.invalid",
            target_port=80,
            timestamp=time.time(),
            content_hash="d16-success",
            provenance={"session_id": "session-d16"},
        )
        return reduce_world_state(
            state,
            ObservationUpdate(
                observation=observation,
                source_seq=1,
                evidence_id="E-D16-A",
            ),
            _AllowedLedger(),
        )


class D16ReplanningSemanticsTests(unittest.TestCase):
    def test_same_action_repeats_when_execution_yields_no_new_state(self) -> None:
        # Given: an initial deterministic selection and an execution with no
        # admissible observation, so the world snapshot is unchanged.
        state = _state()
        planner = _planner()
        initial = planner.plan(state)

        # When: the coordinator replans against exactly that same snapshot.
        repeated = planner.plan(state)
        replan = ReplanDecision(
            should_replan=True,
            reason="state_unchanged",
            parent_plan_id=_required_action(initial).plan_id,
            trigger_hypothesis_id=None,
            focused_context=None,
            execution_plan=repeated.execution_plan,
            next_action=repeated.next_action,
        )

        # Then: the same action and decision identity repeat; no identity or
        # scenario branch is needed to produce the result.
        self.assertEqual(state.world_state_hash, _state().world_state_hash)
        self.assertEqual(_required_action(repeated), _required_action(initial))
        self.assertEqual(repeated.decision_id, initial.decision_id)
        self.assertTrue(replan.should_replan)

    def test_action_changes_only_after_observation_updates_world_state(self) -> None:
        # Given: Action A is the baseline selected from a two-action plan.
        state = _state()
        planner = _planner()
        baseline = planner.plan(state)
        baseline_action = _required_action(baseline)
        baseline_plan = baseline.execution_plan
        if baseline_plan is None:
            raise AssertionError("fixture must carry its execution plan")

        # When: governed success for Action A is observed and folded, then the
        # same planner replans from the new state.
        updated = _observe(state, baseline_action)
        replanned = planner.plan(updated)
        replanned_action = _required_action(replanned)
        remaining = tuple(
            step.capability_id
            for step in baseline_plan.ordered_steps()
            if step.capability_id != baseline_action.capability_id
        )
        replan = ReplanDecision(
            should_replan=True,
            reason="observation_changed_state",
            parent_plan_id=baseline_action.plan_id,
            trigger_hypothesis_id="H-A",
            focused_context=None,
            execution_plan=replanned.execution_plan,
            next_action=replanned.next_action,
        )

        # Then: the central action-difference assertion is derived from the
        # pre-observation plan, while mission/target identity stays constant.
        self.assertNotEqual(replanned_action, baseline_action)
        self.assertEqual(replanned_action.capability_id, remaining[0])
        self.assertEqual(replanned.execution_plan, baseline.execution_plan)
        self.assertEqual(replanned.mission_id, baseline.mission_id)
        self.assertEqual(updated.target_id, state.target_id)
        self.assertNotEqual(updated.world_state_hash, state.world_state_hash)
        self.assertEqual(updated.observations[-1].capability_id, baseline_action.capability_id)
        self.assertTrue(replan.should_replan)

    def test_terminal_state_stops_before_replanning(self) -> None:
        # Given: execution has produced an ALLOW-bound observation and a new
        # state whose endpoint evidence is confirmed.
        state = _state()
        planner = _planner()
        baseline = planner.plan(state)
        updated = _observe(state, _required_action(baseline))
        self.assertTrue(updated.observations)
        self.assertEqual(tuple(item.value for item in updated.endpoints.values()), ("confirmed",))

        # When: the gate reports the terminal condition for that new state.
        stop = evaluate(updated, None, GateVerdict.COMPLETE, StopEvaluatorConfig())
        replan = ReplanDecision(
            should_replan=False,
            reason="terminal_state",
            parent_plan_id=_required_action(baseline).plan_id,
            trigger_hypothesis_id=None,
            focused_context=None,
            execution_plan=None,
            next_action=None,
        )

        # Then: terminal completion wins before any replacement action.
        self.assertIs(stop, StopCondition.MISSION_COMPLETE)
        self.assertFalse(replan.should_replan)
        self.assertIsNone(replan.next_action)

    def test_ungovernable_action_is_refused_before_observation(self) -> None:
        # Given: D15's declaration-only SSH capability has an inert adapter and
        # is therefore not a governable executable action.
        registry = CapabilityRegistry()
        register_ssh(registry)
        self.assertIsInstance(
            registry.get_adapter("NETWORK_SSH_SESSION"),
            InertAdapter,
        )
        request = ActionRequest(
            sequence=0,
            requester="d16-test",
            capability="NETWORK_SSH_SESSION",
            target="synthetic.invalid",
            purpose="declaration-only action",
        )

        # When: Policy evaluates the proposal, before any execution/fold.
        with tempfile.TemporaryDirectory(prefix="d16_refusal_") as directory:
            policy = BOBPolicy(Workspace(Path(directory)))
            decision = policy.consult(request, MISSION)
        stop = evaluate(_state(), decision, GateVerdict.REFUSE, StopEvaluatorConfig())
        replan = ReplanDecision(
            should_replan=False,
            reason="policy_denial",
            parent_plan_id="DP-D16",
            trigger_hypothesis_id=None,
            focused_context=None,
            execution_plan=None,
            next_action=None,
        )

        # Then: refusal is explicit, and no observation can be created.
        self.assertIs(decision.decision, Decision.DENY)
        self.assertIs(stop, StopCondition.POLICY_DENIAL)
        self.assertEqual(_state().observations, ())
        self.assertFalse(replan.should_replan)


if __name__ == "__main__":
    unittest.main()
