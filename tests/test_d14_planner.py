from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import ExecutionPlan
from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.d14_hypothesis import Hypothesis, HypothesisStore
from raphael_ibm_bob.d14_planner import NextAction, Planner
from raphael_ibm_bob.d14_world_state import (
    EvidenceBinding,
    ObservationUpdate,
    WorldState,
    initial_world_state,
)
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts


def _state() -> WorldState:
    mission = Mission(mission_id="M-14", description="d14", scope="scope")
    facts = TargetFacts(target_id="T-14", host="198.51.100.14")
    facts.add_service(ServiceRecord(host=facts.host, port=80, protocol="http"))
    return initial_world_state(mission, facts)


def _hypothesis(hypothesis_id: str, capability: Capability) -> Hypothesis:
    request = ActionRequest(
        sequence=0,
        requester="test",
        capability=capability,
        target="http://198.51.100.14:80/",
        purpose="test",
    )
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        subject_ref="T-14",
        predicate="reachable",
        value=True,
        test_actions=(request,),
        expected_observation="HTTP response",
        falsifier="connection refusal",
        confidence_bps=9000,
        confidence_band="CONFIRMED",
    )


@dataclass
class _Selector:
    plan: ExecutionPlan

    def select_and_compose(self, mission_type, mission_params, facts, **kwargs):
        return self.plan


@dataclass(frozen=True, slots=True)
class _LedgerView:
    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        return EvidenceBinding(
            evidence_id=evidence_id,
            request_seq=1,
            policy_decision="allow",
            result_success=True,
            session_id="session-1",
        )


def _plan(capabilities: tuple[str, ...]) -> ExecutionPlan:
    plan = ExecutionPlan(
        plan_id="DP-test",
        mission_id="M-14",
        target_id="T-14",
        mission_type="probe",
    )
    for capability_id in capabilities:
        plan.add_step(
            capability_id=capability_id,
            params={"target": "http://198.51.100.14:80/", "path": "/"},
            purpose="registered capability",
        )
    return plan


class D14PlannerTests(unittest.TestCase):
    def test_hypothesis_store_is_snapshot_only_and_reduces_observations(self):
        hypothesis = _hypothesis("H-1", Capability.NETWORK_HTTP_REQUEST)
        store = HypothesisStore((hypothesis,))

        self.assertEqual(store.snapshot(), (hypothesis,))
        self.assertIs(store.get("H-1"), hypothesis)

        observation = ObservationRecord(
            observation_id="O-1",
            capability_id="network_http_request",
            observation_type="http_response",
            target_host="198.51.100.14",
            target_port=80,
            timestamp=time.time(),
            content_hash="hash",
            provenance={"session_id": "session-1"},
        )
        updated = store.apply_observation(
            _state(),
            ObservationUpdate(
                observation=observation,
                source_seq=1,
                evidence_id="evidence-1",
            ),
            _LedgerView(),
        )
        self.assertEqual(updated.revision, 1)
        self.assertEqual(store.snapshot(), (hypothesis,))

    def test_permutation_invariance_and_stable_decision_id(self):
        registry = CapabilityRegistry()
        registry.register(network_descriptors()[0], InertAdapter())
        first_plan = _plan(("NETWORK_HTTP_REQUEST", "NETWORK_HTTP_REQUEST"))
        second_plan = _plan(("NETWORK_HTTP_REQUEST", "NETWORK_HTTP_REQUEST"))
        second_plan.steps.reverse()
        first = Planner(
            selector=_Selector(first_plan),
            registry=registry,
            hypotheses=(_hypothesis("H-1", Capability.NETWORK_HTTP_REQUEST),),
        ).plan(_state())
        second = Planner(
            selector=_Selector(second_plan),
            registry=registry,
            hypotheses=(_hypothesis("H-1", Capability.NETWORK_HTTP_REQUEST),),
        ).plan(_state())

        self.assertEqual(first.decision_id, second.decision_id)
        self.assertEqual(
            first.next_action.capability_id,
            second.next_action.capability_id,
        )
        self.assertEqual(first.selected_capability_id, "NETWORK_HTTP_REQUEST")
        self.assertIsInstance(first.next_action, NextAction)

    def test_empty_selection_has_explicit_rationale(self):
        registry = CapabilityRegistry()
        decision = Planner(
            selector=_Selector(_plan(())),
            registry=registry,
        ).plan(_state())

        self.assertIsNone(decision.next_action)
        self.assertEqual(decision.rationale_codes, ("NO_APPLICABLE_CAPABILITY",))

    def test_unregistered_capability_fails_closed(self):
        with self.assertRaises(ValueError):
            Planner(
                selector=_Selector(_plan(("NETWORK_HTTP_REQUEST",))),
                registry=CapabilityRegistry(),
            ).plan(_state())

    def test_next_action_contains_no_policy_decision(self):
        registry = CapabilityRegistry()
        registry.register(network_descriptors()[0], InertAdapter())
        decision = Planner(
            selector=_Selector(_plan(("NETWORK_HTTP_REQUEST",))),
            registry=registry,
        ).plan(_state())

        assert decision.next_action is not None
        self.assertEqual(
            set(decision.next_action.__dataclass_fields__),
            {"request", "plan_id", "step_id", "capability_id"},
        )
        self.assertIsNone(getattr(decision.next_action, "policy_decision", None))


if __name__ == "__main__":
    unittest.main()
