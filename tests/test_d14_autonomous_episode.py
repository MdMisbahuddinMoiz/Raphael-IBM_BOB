"""One deterministic D14 episode through the real governed execution seam."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.contracts import Capability, Mission
from raphael_ibm_bob.d14_ledger_view import EvidenceLedgerView
from raphael_ibm_bob.d14_planner import NextAction, Planner
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig, evaluate
from raphael_ibm_bob.d14_world_state import (
    ObservationUpdate,
    WorldState,
    initial_world_state,
    reduce_world_state,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.network_runtime import NetworkMediator
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.target_service_model import AuthorizationScope, ServiceRecord, TargetFacts
from raphael_ibm_bob.workspace import Workspace


HOST = "127.0.0.1"
MISSION_ID = "M-D14-autonomous-synthetic"


def _synthetic_opener(url: str, method: str, timeout: float, limit: int) -> tuple[int, bytes, bool]:
    """Return a fixed response without opening a socket."""
    del url, method, timeout, limit
    return 200, b"synthetic-http-response", False


def _facts() -> TargetFacts:
    facts = TargetFacts(
        target_id=f"http://{HOST}:80",
        host=HOST,
        mission_id=MISSION_ID,
    )
    facts.add_service(ServiceRecord(HOST, 80, "http", source="manual"))
    facts.authorization = AuthorizationScope(
        target_host=HOST,
        authorized_protocols=frozenset({"http"}),
        authorized_ports=frozenset({80}),
        engagement_id="E-D14-synthetic",
        scope_document_ref="scope://synthetic/d14",
    )
    return facts


def _planner() -> Planner:
    registry = CapabilityRegistry()
    for descriptor in network_descriptors():
        registry.register(descriptor, InertAdapter())
    return Planner(registry=registry, mission_type="service_interaction")


def _capability(action: NextAction | None) -> str | None:
    return None if action is None else action.capability_id


class D14AutonomousEpisode(unittest.TestCase):
    def test_next_action_is_derived_from_changed_world_state(self) -> None:
        """Given facts, execute A, ingest it, and derive a different B."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_root = root / "workspace"
            workspace_root.mkdir()
            workspace = Workspace(workspace_root)
            store = TargetStore()
            store.set_target(
                build_target_profile(
                    mission_id=MISSION_ID,
                    locator=HOST,
                    allowed_ports=[80],
                    allowed_protocols=["http"],
                    authorization_ref="synthetic-only",
                ),
            )
            mission = Mission(
                mission_id=MISSION_ID,
                description="synthetic D14 episode",
                scope="",
                criteria=["state-derived next action"],
                problem={
                    "target_host": HOST,
                    "protocol": "http",
                    "target_port": 80,
                },
            )
            ledger = EvidenceLedger(root / "run")
            self.addCleanup(ledger.close)
            broker = BOBBroker(
                BOBPolicy(workspace, target_store=store),
                workspace,
                ledger=ledger,
                network_mediator=NetworkMediator(opener=_synthetic_opener),
                target_store=store,
            )
            runtime = BOBRuntime(broker)
            planner = _planner()

            state: WorldState = initial_world_state(mission, _facts())
            first = planner.plan(state)
            first_action = first.next_action
            self.assertEqual(_capability(first_action), Capability.NETWORK_HTTP_REQUEST.name)
            assert first_action is not None

            first_result = runtime.submit(first_action.request, mission)
            self.assertTrue(first_result.broker_result.capability_invoked)
            self.assertTrue(first_result.execution is not None and first_result.execution.success)

            observation_evidence_id = "EV-D14-synthetic-observation-a"
            ledger.append_evidence(
                evidence_id=observation_evidence_id,
                producer="d14-test-observation",
                request_seq=first_result.request_seq,
                decision_seq=first_result.decision_seq,
                result_seq=first_result.result_seq,
                payload={
                    "request_seq": first_result.request_seq,
                    "decision_seq": first_result.decision_seq,
                    "result_seq": first_result.result_seq,
                    "session_id": "synthetic-session",
                },
            )
            observation = ObservationUpdate(
                observation=ObservationRecord(
                    observation_id="obs-http-a",
                    capability_id=Capability.NETWORK_HTTP_REQUEST.value,
                    observation_type="http_response",
                    target_host=HOST,
                    target_port=80,
                    timestamp=time.time(),
                    content_hash="synthetic-http-response",
                    provenance={"session_id": "synthetic-session"},
                ),
                source_seq=first_result.result_seq or first_result.decision_seq,
                evidence_id=observation_evidence_id,
                replan_requested=True,
            )
            changed_state = reduce_world_state(
                state,
                observation,
                EvidenceLedgerView(ledger),
            )

            second = planner.plan(changed_state)
            second_action = second.next_action
            self.assertNotEqual(state.world_state_hash, changed_state.world_state_hash)
            self.assertEqual(changed_state.replan_count, 1)
            self.assertNotEqual(_capability(first_action), _capability(second_action))
            self.assertIsNone(second_action)
            self.assertEqual(
                evaluate(changed_state, second, None, StopEvaluatorConfig()),
                StopCondition.NO_APPLICABLE_CAPABILITY,
            )


if __name__ == "__main__":
    unittest.main()
