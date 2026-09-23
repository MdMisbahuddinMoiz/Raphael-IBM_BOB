"""Unit coverage for the additive D16 coordinator."""
from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import ExecutionPlan, plan_to_action_requests
from raphael_ibm_bob.contracts import GateVerdict, Mission
from raphael_ibm_bob.d14_hypothesis import Hypothesis
from raphael_ibm_bob.d14_planner import Planner
from raphael_ibm_bob.d14_state_codec import EvidenceBinding
from raphael_ibm_bob.d14_world_state import ObservationUpdate, initial_world_state
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts
from raphael_ibm_bob.d16_autonomous import AutonomousLoop, VerificationOutcome, VerificationResult


MISSION = Mission("M-D16-UNIT", "state-driven loop", "scope://synthetic")


@dataclass(frozen=True, slots=True)
class _Selector:
    plan: ExecutionPlan

    def select_and_compose(self, mission_type: str, mission_params: dict[str, str], facts: TargetFacts, *, credential_refs: list[str] | None = None) -> ExecutionPlan:
        return self.plan


@dataclass(frozen=True, slots=True)
class _Ledger:
    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding:
        return EvidenceBinding(evidence_id, 1, "allow", True, "d16-session")


@dataclass
class _Runtime:
    requests: list[object]

    def submit(self, request, mission: Mission):
        self.requests.append(request)
        return None


def _loop() -> tuple[AutonomousLoop, _Runtime]:
    registry = CapabilityRegistry()
    for descriptor in network_descriptors():
        registry.register(descriptor, InertAdapter())
    plan = ExecutionPlan("P-A", MISSION.mission_id, "synthetic", "probe")
    plan.add_step("NETWORK_HTTP_REQUEST", {"target": "http://synthetic.invalid"}, purpose="A")
    plan.add_step("NETWORK_TELNET_SESSION", {"target": "telnet://synthetic.invalid:23"}, purpose="B")
    actions = plan_to_action_requests(plan, registry=registry, requester="unit")
    hypotheses = tuple(
        Hypothesis(f"H-{label}", "synthetic", "available", True, (action,), "response", "failure", 9000, "CONFIRMED")
        for label, action in zip(("A", "B"), actions, strict=True)
    )
    facts = TargetFacts("synthetic", "synthetic.invalid")
    facts.add_service(ServiceRecord("synthetic.invalid", 80, "http"))
    runtime = _Runtime([])
    return AutonomousLoop(MISSION, Planner(_Selector(plan), registry, hypotheses=hypotheses), runtime, _Ledger(), initial_world_state(MISSION, facts)), runtime


class D16LoopUnitTests(unittest.TestCase):
    def test_evidence_changes_next_action_without_planner_execution(self) -> None:
        # Given: the planner has proposed Action A.
        loop, runtime = _loop()
        baseline = loop.propose()
        action_a = baseline.next_action
        self.assertIsNotNone(action_a)

        # When: Runtime receives A and its fresh evidence is ingested.
        loop.submit_next()
        assert action_a is not None
        observation = ObservationRecord("O-A", action_a.capability_id, "http_response", "synthetic.invalid", time.time(), "hash", 80, provenance={"session_id": "d16-session"})
        result = loop.ingest(ObservationUpdate(observation, 1, "E-A"), VerificationResult("V-A", VerificationOutcome.FALSIFIED, ("E-A",), "O-A", "counterexample"))

        # Then: state changed, replacement B is explicit, and only Runtime was called.
        self.assertEqual(len(runtime.requests), 1)
        self.assertNotEqual(result.next_action, action_a)
        self.assertEqual(result.next_action.capability_id, "NETWORK_TELNET_SESSION")
        self.assertEqual(result.replan.reason, "verification_falsified")

    def test_complete_gate_stops_before_replacement(self) -> None:
        # Given: an evidence-backed observation and a terminal gate verdict.
        loop, _ = _loop()
        action = loop.propose().next_action
        self.assertIsNotNone(action)
        assert action is not None
        observation = ObservationRecord("O-A", action.capability_id, "http_response", "synthetic.invalid", time.time(), "hash", 80, provenance={"session_id": "d16-session"})

        # When: the terminal verdict is incorporated with the observation.
        result = loop.ingest(ObservationUpdate(observation, 1, "E-A"), VerificationResult("V-A", VerificationOutcome.VERIFIED, ("E-A",), "O-A", "confirmed"), GateVerdict.COMPLETE)

        # Then: completion is preserved and no replacement is selected.
        self.assertEqual(result.stop, "mission_complete")
        self.assertIsNone(result.next_action)


if __name__ == "__main__":
    unittest.main()
