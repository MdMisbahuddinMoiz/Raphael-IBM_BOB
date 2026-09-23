from __future__ import annotations

# noqa: SIZE_OK — this file is the single deterministic D16 transition proof matrix.

import tempfile
import time
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import ExecutionPlan
from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.d14_ledger_view import EvidenceLedgerView
from raphael_ibm_bob.d14_state_codec import EvidenceBinding, ExecutionBinding
from raphael_ibm_bob.d14_world_state import (
    ObservationUpdate,
    StateTransitionError,
    StaleObservationError,
    WorldState,
    initial_world_state,
    reduce_state_transition,
    reduce_world_state,
)
from raphael_ibm_bob.d15_observation import (
    ObservationContext,
    ServiceBannerMetadata,
    associate_observation,
    build_service_banner,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.network_runtime import NetworkMediator
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)
from raphael_ibm_bob.workspace import Workspace


HOST = "198.51.100.16"
MISSION = Mission(
    mission_id="M-D16-state-transition",
    description="synthetic D16 state transition",
    scope="scope://synthetic/d16",
    criteria=["changed state selects the next action"],
)
SESSION_ID = "session-d16-runtime"


@dataclass(frozen=True, slots=True)
class _RuntimeSession:
    session_id: str


@dataclass(frozen=True, slots=True)
class _LedgerView:
    bindings: dict[str, EvidenceBinding]

    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        return self.bindings.get(evidence_id)


@dataclass(frozen=True, slots=True)
class _FixedSelector:
    plan: ExecutionPlan

    def select_and_compose(
        self,
        mission_type: str,
        mission_params: dict[str, str],
        facts: TargetFacts,
        *,
        credential_refs: list[str] | None = None,
    ) -> ExecutionPlan:
        del mission_type, mission_params, facts, credential_refs
        return self.plan


def _synthetic_opener(
    url: str,
    method: str,
    timeout: float,
    max_bytes: int,
) -> tuple[int, bytes, bool]:
    """Return a fixed response without opening a socket."""
    del url, method, timeout, max_bytes
    return 200, b"synthetic-d16-response", False


def _facts() -> TargetFacts:
    facts = TargetFacts(
        target_id="synthetic-target",
        host=HOST,
        mission_id=MISSION.mission_id,
    )
    facts.add_service(ServiceRecord(HOST, 23, "telnet", discovered_at=0.0))
    facts.authorization = AuthorizationScope(
        target_host=HOST,
        authorized_protocols=frozenset({"http", "telnet"}),
        authorized_ports=frozenset({23, 80}),
        engagement_id="E-D16-synthetic",
        scope_document_ref="scope://synthetic/d16",
    )
    return facts


def _seed_update() -> ObservationUpdate:
    return ObservationUpdate(
        observation=ObservationRecord(
            observation_id="obs-d16-a",
            capability_id="synthetic-observer",
            observation_type="http_response",
            target_host=HOST,
            target_port=80,
            timestamp=time.time(),
            content_hash="seed-http",
            provenance={"session_id": SESSION_ID},
        ),
        source_seq=1,
        evidence_id="E-D16-A",
        service=ServiceRecord(
            HOST,
            80,
            "http",
            discovered_at=0.0,
            source="prior_observation",
        ),
    )


def _seed_ledger() -> _LedgerView:
    return _LedgerView({
        "E-D16-A": EvidenceBinding(
            evidence_id="E-D16-A",
            request_seq=1,
            policy_decision="allow",
            result_success=True,
            session_id=SESSION_ID,
        ),
    })


def _plan() -> ExecutionPlan:
    plan = ExecutionPlan(
        "DP-D16-transition",
        MISSION.mission_id,
        "synthetic-target",
        "service_interaction",
    )
    plan.add_step(
        "NETWORK_HTTP_REQUEST",
        {"target": f"http://{HOST}:80/"},
        purpose="Action A",
    )
    plan.add_step(
        "NETWORK_TELNET_SESSION",
        {"target": f"telnet://{HOST}:23"},
        purpose="Action B",
    )
    return plan


def _planner() -> tuple[CapabilityRegistry, _FixedSelector]:
    registry = CapabilityRegistry()
    for descriptor in network_descriptors():
        registry.register(descriptor, InertAdapter())
    return registry, _FixedSelector(_plan())


class D16StateTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="d16_state_transition_")
        root = Path(self.tempdir.name)
        workspace_root = root / "workspace"
        workspace_root.mkdir()
        self.workspace = Workspace(workspace_root)
        self.store = TargetStore()
        self.store.set_target(build_target_profile(
            mission_id=MISSION.mission_id,
            locator=HOST,
            allowed_ports=[80],
            allowed_protocols=["http"],
            authorization_ref="synthetic-d16-only",
        ))
        self.ledger = EvidenceLedger(root / "run")
        self.broker = BOBBroker(
            BOBPolicy(self.workspace, target_store=self.store),
            self.workspace,
            ledger=self.ledger,
            network_mediator=NetworkMediator(opener=_synthetic_opener),
            target_store=self.store,
        )
        self.runtime = BOBRuntime(self.broker)
        self.addCleanup(self.ledger.close)
        self.addCleanup(self.tempdir.cleanup)

    def _state_after_observation_a(self) -> WorldState:
        state = initial_world_state(MISSION, _facts())
        return reduce_world_state(state, _seed_update(), _seed_ledger())

    def _execute_action_a(self, state: WorldState) -> tuple[WorldState, RuntimeResult, ExecutionBinding]:
        registry, selector = _planner()
        from raphael_ibm_bob.d14_planner import Planner

        decision = Planner(
            selector=selector,
            registry=registry,
            mission_type="service_interaction",
        ).plan(state)
        action = decision.next_action
        if action is None:
            raise AssertionError("synthetic state must select Action A")
        result = self.runtime.submit(action.request, MISSION)
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution is not None and result.execution.success)
        observation_evidence_id = "E-D16-B"
        self.ledger.append_evidence(
            evidence_id=observation_evidence_id,
            producer="d16-observation",
            request_seq=result.request_seq,
            decision_seq=result.decision_seq,
            result_seq=result.result_seq,
            payload={
                "request_seq": result.request_seq,
                "decision_seq": result.decision_seq,
                "result_seq": result.result_seq,
                "session_id": SESSION_ID,
                "execution_evidence_id": result.evidence_ids[-1],
            },
        )
        binding = ExecutionBinding.from_runtime_result(
            result,
            _RuntimeSession(SESSION_ID),
            observation_evidence_id,
        )
        return state, result, binding

    def _associated_observation(self, binding: ExecutionBinding) -> ObservationRecord:
        context = ObservationContext.from_governed_runtime(
            capability_id="NETWORK_HTTP_REQUEST",
            target_host=HOST,
            target_port=80,
            runtime_session=_RuntimeSession(SESSION_ID),
        )
        normalized = build_service_banner(
            context,
            ServiceBannerMetadata(
                protocol="http",
                transport="tcp",
                banner_hash="sha256:synthetic-d16",
                version="synthetic/1",
            ),
        )
        return associate_observation(normalized, binding)

    def test_observation_a_establishes_initial_world_state_fact(self) -> None:
        state = initial_world_state(MISSION, _facts())

        changed = reduce_world_state(state, _seed_update(), _seed_ledger())

        self.assertIsNone(state.facts.get_service("http"))
        self.assertIsNotNone(changed.facts.get_service("http"))
        self.assertEqual(changed.endpoints[f"{HOST}:80"].value, "confirmed")

    def test_action_a_produces_normalized_observation_associated_with_execution(self) -> None:
        state = self._state_after_observation_a()
        _state, result, binding = self._execute_action_a(state)

        observation = self._associated_observation(binding)

        self.assertTrue(result.broker_result.capability_invoked)
        self.assertEqual(
            observation.capability_id.casefold(),
            binding.capability_id.casefold(),
        )
        self.assertEqual(observation.provenance["session_id"], SESSION_ID)
        self.assertEqual(
            observation.provenance["execution_binding"]["result_seq"],
            result.result_seq,
        )
        self.assertIn("normalized", observation.provenance)

    def test_d16_reducer_reuses_d14_reducer_and_changes_state_deterministically(self) -> None:
        state = self._state_after_observation_a()
        _state, _result, binding = self._execute_action_a(state)
        observation = self._associated_observation(binding)
        update = ObservationUpdate(
            observation=observation,
            source_seq=binding.result_seq,
            evidence_id=binding.observation_evidence_id,
            execution_binding=binding,
            replan_requested=True,
        )

        transition = reduce_state_transition(
            state,
            update,
            EvidenceLedgerView(self.ledger),
        )
        replay = reduce_state_transition(
            state,
            update,
            EvidenceLedgerView(self.ledger),
        )

        self.assertTrue(transition.changed)
        self.assertIs(transition.previous, state)
        self.assertNotEqual(transition.current.world_state_hash, state.world_state_hash)
        self.assertEqual(transition.current.world_state_hash, replay.current.world_state_hash)
        self.assertEqual(transition.current.progress_token, replay.current.progress_token)
        self.assertEqual(transition.current.replan_count, 1)

    def test_changed_state_drives_replanning_decision(self) -> None:
        from raphael_ibm_bob.d14_planner import Planner

        state = self._state_after_observation_a()
        registry, selector = _planner()
        planner = Planner(
            selector=selector,
            registry=registry,
            mission_type="service_interaction",
        )
        before = planner.plan(state)
        self.assertIsNotNone(before.next_action)
        _state, _result, binding = self._execute_action_a(state)
        update = ObservationUpdate(
            self._associated_observation(binding),
            binding.result_seq,
            binding.observation_evidence_id,
            replan_requested=True,
            execution_binding=binding,
        )
        changed = reduce_state_transition(
            state,
            update,
            EvidenceLedgerView(self.ledger),
        ).current

        after = planner.plan(changed)

        self.assertEqual(before.selected_capability_id, "NETWORK_HTTP_REQUEST")
        self.assertEqual(after.selected_capability_id, "NETWORK_TELNET_SESSION")
        self.assertNotEqual(before.decision_id, after.decision_id)
        self.assertEqual(after.world_revision, changed.revision)

    def test_stale_state_cannot_masquerade_as_newest_observation(self) -> None:
        state = self._state_after_observation_a()
        _state, _result, binding = self._execute_action_a(state)
        observation = self._associated_observation(binding)
        update = ObservationUpdate(
            observation,
            binding.result_seq,
            binding.observation_evidence_id,
            execution_binding=binding,
        )
        newest = reduce_state_transition(
            state,
            update,
            EvidenceLedgerView(self.ledger),
        ).current
        stale = replace(
            update,
            observation=replace(observation, observation_id="obs-d16-stale"),
        )

        with self.assertRaises(StaleObservationError):
            reduce_state_transition(
                newest,
                stale,
                EvidenceLedgerView(self.ledger),
            )

        self.assertEqual(newest.last_source_seq, binding.result_seq)
        self.assertEqual(newest.observations[-1].observation_id, observation.observation_id)

    def test_ingestion_binding_and_runtime_session_are_required(self) -> None:
        state = self._state_after_observation_a()
        _state, _result, binding = self._execute_action_a(state)
        observation = self._associated_observation(binding)
        unbound = ObservationUpdate(
            observation,
            binding.result_seq,
            binding.observation_evidence_id,
        )

        with self.assertRaises(StateTransitionError):
            reduce_state_transition(
                state,
                unbound,
                EvidenceLedgerView(self.ledger),
            )

        forged = replace(
            observation,
            provenance={**observation.provenance, "session_id": "caller-session"},
        )
        update = ObservationUpdate(
            forged,
            binding.result_seq,
            binding.observation_evidence_id,
            execution_binding=binding,
        )

        with self.assertRaises(ValueError):
            reduce_state_transition(
                state,
                update,
                EvidenceLedgerView(self.ledger),
            )

        self.assertEqual(binding.session_binding.session_id, SESSION_ID)


if __name__ == "__main__":
    unittest.main()
