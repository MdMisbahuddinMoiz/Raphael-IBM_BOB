"""D14 deterministic autonomy episodes.

These tests call only the frozen D14 seams:
``d14_world_state.initial_world_state`` / ``reduce_world_state``,
``ObservationUpdate``, ``WorldState``, ``d14_hypothesis.Hypothesis`` /
``HypothesisStore``, and ``d14_planner``'s ``NextAction``, ``Planner.plan``,
``SelectionDecision``, ``StopCondition``, and ``AutonomyState``.

All target inputs are synthetic ``TargetFacts`` and observations.  The
planner is never replaced with a scripted action list.  In particular, the
HTTP+Telnet and observation-transition tests would fail if the planner
returned a fixed second action.
"""
from __future__ import annotations

import unittest
import inspect
from enum import Enum
from types import SimpleNamespace

from raphael_ibm_bob.contracts import ActionRequest, Capability, Decision, GateVerdict, Mission, PolicyDecision
from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.d14_state_codec import EvidenceBinding
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig, evaluate
from raphael_ibm_bob.d14_loop import AutonomyState
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)

try:
    from raphael_ibm_bob.d14_world_state import (
        ObservationUpdate,
        WorldState,
        initial_world_state,
        reduce_world_state,
    )
    from raphael_ibm_bob.d14_hypothesis import Hypothesis, HypothesisStore
    from raphael_ibm_bob.d14_planner import (
        NextAction,
        Planner,
        SelectionDecision,
    )
except ImportError as error:
    D14_IMPORT_ERROR = f"D14 autonomy API is incomplete: {error}"
else:
    D14_IMPORT_ERROR = None


HOST = "synthetic.invalid"
MISSION = Mission(
    mission_id="M-D14-synthetic",
    description="deterministic synthetic autonomy episode",
    scope="synthetic-only",
    criteria=["state-derived action selection"],
)


def _facts(
    services: tuple[tuple[str, int], ...],
    credentials: tuple[str, ...] = (),
    *,
    authorized: bool = True,
) -> TargetFacts:
    facts = TargetFacts(
        target_id="synthetic-target",
        host=HOST,
        credential_refs=list(credentials),
        mission_id=MISSION.mission_id,
    )
    for protocol, port in services:
        facts.add_service(ServiceRecord(
            host=HOST,
            port=port,
            protocol=protocol,
            source="manual",
            discovered_at=0.0,
        ))
    if authorized:
        facts.authorization = AuthorizationScope(
            target_host=HOST,
            authorized_protocols=frozenset(protocol for protocol, _ in services),
            authorized_ports=frozenset(port for _, port in services),
            engagement_id="E-D14-synthetic",
            scope_document_ref="scope://synthetic/d14",
        )
    return facts


def _state(facts: TargetFacts) -> WorldState:
    return initial_world_state(MISSION, facts)


def _update(
    observation_id: str,
    capability_id: str,
    observation_type: str,
    port: int,
    *,
    replan_requested: bool = False,
    service: ServiceRecord | None = None,
    session_id: str = "session-d14",
) -> ObservationUpdate:
    return ObservationUpdate(
        observation=ObservationRecord(
            observation_id=observation_id,
            capability_id=capability_id,
            observation_type=observation_type,
            target_host=HOST,
            target_port=port,
            timestamp=__import__("time").time(),
            content_hash=f"hash-{observation_id}",
            provenance={"session_id": session_id},
        ),
        source_seq=1,
        evidence_id=f"evidence-{observation_id}",
        replan_requested=replan_requested,
        service=service,
    )


class _LedgerView:
    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        return EvidenceBinding(evidence_id, 1, "allow", True, "session-d14")


LEDGER = _LedgerView()


def _plan(state: WorldState) -> SelectionDecision:
    registry = CapabilityRegistry()
    for descriptor in network_descriptors():
        registry.register(descriptor, InertAdapter())
    return Planner(
        registry=registry,
        mission_type="service_interaction",
    ).plan(state)


def _action(decision: SelectionDecision) -> NextAction | None:
    return decision.next_action


def _capability(action: NextAction | None) -> str | None:
    if action is None:
        return None
    value = getattr(action, "capability_id", getattr(action, "capability", None))
    return getattr(value, "value", str(value))


def _label(value: Enum | str | None) -> str:
    if isinstance(value, Enum):
        return str(value.value).upper()
    return "" if value is None else str(value).upper()


@unittest.skipIf(D14_IMPORT_ERROR is not None, D14_IMPORT_ERROR or "D14 API unavailable")
class D14AutonomyEpisodes(unittest.TestCase):
    def test_frozen_d14_symbols_are_available(self) -> None:
        self.assertTrue(inspect.isclass(Hypothesis))
        self.assertEqual(AutonomyState.OBSERVE.value, "observe")
        self.assertNotIn("DONE", AutonomyState.__members__)

    def test_A_http_only_selects_http(self) -> None:
        decision = _plan(_state(_facts((("http", 80),))))
        self.assertEqual(_capability(_action(decision)), "NETWORK_HTTP_REQUEST")

    def test_B_telnet_with_credential_selects_telnet(self) -> None:
        decision = _plan(_state(_facts((("telnet", 23),), ("telnet-valid",))))
        self.assertEqual(_capability(_action(decision)), "NETWORK_TELNET_SESSION")

    def test_C_http_and_telnet_follow_state_ordering(self) -> None:
        state = _state(_facts((("http", 80), ("telnet", 23)), ("telnet-valid",)))
        first = _plan(state)
        after_http = _state(_facts((("http", 80), ("telnet", 23)), ("telnet-valid",)))
        after_http = reduce_world_state(
            after_http,
            _update("obs-http", "network_http_request", "http_response", 80),
            LEDGER,
        )
        second = _plan(after_http)
        self.assertEqual(_capability(_action(first)), "NETWORK_HTTP_REQUEST")
        self.assertEqual(_capability(_action(second)), "NETWORK_TELNET_SESSION")
        self.assertNotEqual(_capability(_action(first)), _capability(_action(second)))

    def test_D_unknown_service_stops_without_applicable_capability(self) -> None:
        state = _state(_facts((("gopher", 70),)))
        decision = _plan(state)
        self.assertIsNone(_action(decision))
        self.assertEqual(evaluate(state, decision, None, StopEvaluatorConfig()), StopCondition.NO_APPLICABLE_CAPABILITY)

    def test_E_missing_prerequisite_never_selects_telnet(self) -> None:
        decision = _plan(_state(_facts((("telnet", 23),))))
        capability = _capability(_action(decision))
        self.assertTrue(capability is None or "credential" in capability or "gather" in capability)

    def test_F_policy_denial_has_no_invocation(self) -> None:
        state = _state(_facts((("http", 80),), authorized=False))
        decision = _plan(state)
        denial = PolicyDecision(
            1,
            Decision.DENY,
            "outside scope",
            Capability.NETWORK_HTTP_REQUEST,
            "synthetic.invalid",
        )
        self.assertIsNone(_action(decision))
        self.assertEqual(state.step_count, 0)
        self.assertEqual(evaluate(state, denial, None, StopEvaluatorConfig()), StopCondition.POLICY_DENIAL)

    def test_G_success_observation_changes_next_action(self) -> None:
        state = _state(_facts((("http", 80), ("telnet", 23)), ("telnet-valid",)))
        first = _plan(state)
        progressed = reduce_world_state(
            state,
            _update(
                "obs-http-success",
                "network_http_request",
                "http_response",
                80,
                service=ServiceRecord(
                    HOST,
                    23,
                    "telnet",
                    discovered_at=0.0,
                    source="prior_observation",
                ),
            ),
            LEDGER,
        )
        second = _plan(progressed)
        self.assertEqual(_capability(_action(first)), "NETWORK_HTTP_REQUEST")
        self.assertNotEqual(_capability(_action(first)), _capability(_action(second)))
        self.assertEqual(_capability(_action(second)), "NETWORK_TELNET_SESSION")

    def test_H_failed_action_replans_from_new_state(self) -> None:
        state = _state(_facts((("http", 80), ("telnet", 23)), ("telnet-valid",)))
        first = _plan(state)
        failed = reduce_world_state(
            state,
            _update("obs-http-failed", "network_http_request", "connection_refused", 80, replan_requested=True),
            LEDGER,
        )
        second = _plan(failed)
        self.assertEqual(_capability(_action(first)), "NETWORK_HTTP_REQUEST")
        self.assertEqual(failed.replan_count, 1)
        self.assertEqual(_capability(_action(second)), "NETWORK_TELNET_SESSION")

    def test_I_no_progress_stops(self) -> None:
        state = _state(_facts((("http", 80),)))
        decision = _plan(state)
        self.assertEqual(evaluate(state, decision, None, StopEvaluatorConfig(prior_world_states=(state, state))), StopCondition.NO_PROGRESS)

    def test_J_mission_complete_returns_gate_verdict_without_action(self) -> None:
        state = _state(_facts((("http", 80),)))
        decision = _plan(state)
        gate = SimpleNamespace(verdict=GateVerdict.COMPLETE)
        self.assertEqual(evaluate(state, decision, gate, StopEvaluatorConfig()), StopCondition.MISSION_COMPLETE)


if __name__ == "__main__":
    unittest.main()
