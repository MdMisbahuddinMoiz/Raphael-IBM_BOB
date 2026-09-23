"""Deterministic D16 loop fixtures built on the frozen D12-D15 seams."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Final
from unittest.mock import patch

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import Decision, Mission
from raphael_ibm_bob.d14_ledger_view import EvidenceLedgerView
from raphael_ibm_bob.d14_planner import NextAction, Planner, SelectionDecision
from raphael_ibm_bob.d14_world_state import (
    ObservationUpdate,
    WorldState,
    initial_world_state,
    reduce_world_state,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult
from raphael_ibm_bob.target_profile import TargetProfile, TargetStore
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts
from raphael_ibm_bob.workspace import Workspace
from tests.d16_autonomous_loop_model import (
    CANDIDATE_TARGET,
    MISSION_ID,
    MISSION_TYPE,
    RECOVERY_TARGET,
    SESSION_ID,
    TARGET_HOST,
    ObservationRoute,
    ObservationSpec,
    StateDrivenSelector,
    VerificationResult,
    VerificationStatus,
    registry,
)


FIXED_TIMESTAMP: Final = 1_700_000_000.0
FIXED_LEDGER_CLOCK: Final = 1_700_000_000_000_000_000


class AutonomousLoopFixture:
    """One isolated D16 run with a real Runtime -> Broker -> Policy path."""

    def __init__(
        self,
        initial_protocols: tuple[str, ...] = ("stage_a", "stage_b"),
    ) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="d16_acceptance_")
        self.root = Path(self._temporary.name)
        (self.root / CANDIDATE_TARGET).write_text(
            "D16-HYPOTHESIS\n",
            encoding="utf-8",
        )
        (self.root / RECOVERY_TARGET).write_text("initial\n", encoding="utf-8")
        workspace = Workspace(self.root)
        self.mission = Mission(
            mission_id=MISSION_ID,
            description="synthetic D16 autonomous-loop acceptance",
            scope="",
            criteria=["planner consumes governed observations"],
        )
        self.target_store = TargetStore()
        self.target_store.set_target(
            TargetProfile(
                target_id="TP-D16-synthetic",
                mission_id=MISSION_ID,
                platform="htb",
                locator=TARGET_HOST,
                allowed_ports=(80,),
                allowed_protocols=("http",),
                scope=TARGET_HOST,
                authorization_ref="synthetic-d16-http-only",
                environment="synthetic",
                created_ts="2026-01-01T00:00:00+00:00",
            ),
        )
        facts = TargetFacts(
            target_id="synthetic-d16-target",
            host=TARGET_HOST,
            mission_id=MISSION_ID,
        )
        for protocol in initial_protocols:
            facts.add_service(
                ServiceRecord(
                    host=TARGET_HOST,
                    port=1,
                    protocol=protocol,
                    discovered_at=FIXED_TIMESTAMP,
                    source="manual",
                ),
            )
        self.ledger = EvidenceLedger(
            self.root / "run",
            clock=lambda: FIXED_LEDGER_CLOCK,
        )
        capability_registry = registry()
        self.broker = BOBBroker(
            BOBPolicy(workspace, target_store=self.target_store),
            workspace,
            ledger=self.ledger,
            target_store=self.target_store,
            registry=capability_registry,
        )
        self.runtime = BOBRuntime(self.broker)
        self.selector = StateDrivenSelector(CANDIDATE_TARGET)
        self.planner = Planner(
            selector=self.selector,
            registry=capability_registry,
            mission_type=MISSION_TYPE,
        )
        self.state: WorldState = initial_world_state(self.mission, facts)
        self._closed = False

    def close(self) -> None:
        """Close durable resources and remove this isolated fixture."""
        if self._closed:
            return
        self._closed = True
        self.ledger.close()
        self._temporary.cleanup()

    def consume(self, decision: SelectionDecision) -> RuntimeResult:
        """Consume exactly the planner-selected request through Runtime."""
        action = decision.next_action
        if action is None:
            raise AssertionError("acceptance fixture requires a selected action")
        return self.runtime.submit(action.request, self.mission)

    def observation_from_result(
        self,
        result: RuntimeResult,
        spec: ObservationSpec,
    ) -> ObservationUpdate:
        """Bind a deterministic normalized observation to a real result."""
        result_seq = result.result_seq
        if result_seq is None:
            raise AssertionError("an observation needs a successful result sequence")
        evidence_id = digest_id(
            {
                "observation_id": spec.observation_id,
                "request_seq": result.request_seq,
                "decision_seq": result.decision_seq,
                "result_seq": result_seq,
            },
            prefix="D16O",
        )
        self.ledger.append_evidence(
            evidence_id=evidence_id,
            producer="d16-observation-adapter",
            request_seq=result.request_seq,
            decision_seq=result.decision_seq,
            result_seq=result_seq,
            payload={
                "kind": "synthetic-observation",
                "session_id": SESSION_ID,
                "capability": result.broker_result.decision.capability.value,
                "request_seq": result.request_seq,
                "decision_seq": result.decision_seq,
                "result_seq": result_seq,
            },
        )
        route_value = "observed" if spec.route is None else spec.route.value
        content_hash = hashlib.sha256(
            f"{spec.observation_id}:{route_value}".encode(),
        ).hexdigest()
        observation = ObservationRecord(
            observation_id=spec.observation_id,
            capability_id=result.broker_result.decision.capability.name,
            observation_type="http_response",
            target_host=TARGET_HOST,
            target_port=1,
            timestamp=FIXED_TIMESTAMP,
            content_hash=content_hash,
            provenance={
                "session_id": spec.observation_session,
                "synthetic": "d16",
                "route": route_value,
            },
        )
        service = None if spec.route is None else ServiceRecord(
            host=TARGET_HOST,
            port=1,
            protocol=spec.route.value,
            discovered_at=FIXED_TIMESTAMP,
            source="prior_observation",
        )
        return ObservationUpdate(
            observation=observation,
            source_seq=result_seq if spec.source_seq is None else spec.source_seq,
            evidence_id=evidence_id,
            replan_requested=True,
            service=service,
        )

    def fold(self, update: ObservationUpdate) -> WorldState:
        """Apply D16's monotonic observation-ingress rule, then D14's reducer.

        The source-sequence gate is the test coordinator's only D16-specific
        stateful behavior. The resulting snapshot is always fed to the frozen
        D14 reducer, and tests assert planner actions from that snapshot.
        """
        if update.source_seq <= self.state.last_source_seq:
            return self.state
        with patch(
            "raphael_ibm_bob.observation_model.time.time",
            return_value=FIXED_TIMESTAMP,
        ):
            self.state = reduce_world_state(
                self.state,
                update,
                EvidenceLedgerView(self.ledger),
            )
        return self.state


def selected_action(decision: SelectionDecision) -> NextAction:
    """Require a planner proposal in a matrix row that expects one."""
    action = decision.next_action
    if action is None:
        raise AssertionError("matrix row expected a planner-selected action")
    return action


def decision_is_allowed(result: RuntimeResult) -> bool:
    """Return the durable policy outcome for a consumed planner result."""
    return result.broker_result.decision.decision is Decision.ALLOW


__all__ = [
    "AutonomousLoopFixture",
    "FIXED_TIMESTAMP",
    "MISSION_ID",
    "ObservationRoute",
    "ObservationSpec",
    "VerificationResult",
    "VerificationStatus",
    "decision_is_allowed",
    "selected_action",
]
