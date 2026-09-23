from __future__ import annotations

import unittest
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Callable, Final
from unittest.mock import patch

from raphael_ibm_bob.contracts import ActionRequest, Decision, GateVerdict
from raphael_ibm_bob.d16_autonomous import AutonomousLoop, LoopSnapshot, VerificationOutcome, VerificationResult
from raphael_ibm_bob.d14_ledger_view import EvidenceLedgerView
from raphael_ibm_bob.d14_state_codec import ExecutionBinding
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig
from raphael_ibm_bob.d14_world_state import ObservationUpdate
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.runtime import RuntimeResult
from raphael_ibm_bob.target_service_model import ServiceRecord

from tests.d16_autonomous_loop_helpers import (
    AutonomousLoopFixture,
    FIXED_TIMESTAMP,
    ObservationRoute,
    ObservationSpec,
)
from tests.d16_autonomous_loop_model import SESSION_ID


_CONTENT_RESIDUAL: Final[str] = "D17 residual: AutonomousLoop.ingest validates evidence identity and session provenance, then calls reduce_world_state without binding observation capability, target, or injected service to Runtime execution content."
_STALE_RESIDUAL: Final[str] = "D17 residual: AutonomousLoop.ingest does not enforce the D14 source-sequence monotonicity gate before reducing world state."


@dataclass(frozen=True, slots=True)
class _RuntimeSession:
    session_id: str


class _UnregisteredCapability(StrEnum):
    D17 = "D17_UNREGISTERED_CAPABILITY"


class D17HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AutonomousLoopFixture()
        self.addCleanup(self.fixture.close)

    def _loop(
        self,
        fixture: AutonomousLoopFixture | None = None,
        stop_config: StopEvaluatorConfig | None = None,
    ) -> AutonomousLoop:
        active_fixture = self.fixture if fixture is None else fixture
        return AutonomousLoop(
            active_fixture.mission, active_fixture.planner, active_fixture.runtime,
            EvidenceLedgerView(active_fixture.ledger), active_fixture.state,
            stop_config or StopEvaluatorConfig(max_replans=5),
        )

    @staticmethod
    def _verification(update: ObservationUpdate) -> VerificationResult:
        evidence_id = update.evidence_id
        if not evidence_id:
            raise AssertionError("D17 verification requires an evidence id")
        return VerificationResult(
            verification_id=f"V-D17-{update.observation.observation_id}",
            outcome=VerificationOutcome.VERIFIED,
            evidence_ids=(evidence_id,),
            observation_id=update.observation.observation_id,
            rationale="deterministic D17 evidence fold",
        )

    @staticmethod
    def _bound_update(
        fixture: AutonomousLoopFixture,
        result: RuntimeResult,
        observation_id: str,
        route: ObservationRoute | None = None,
        source_seq: int | None = None,
    ) -> ObservationUpdate:
        update = fixture.observation_from_result(
            result,
            ObservationSpec(observation_id, route, source_seq=source_seq),
        )
        evidence_id = update.evidence_id
        if not evidence_id:
            raise AssertionError("D17 observation fixture requires evidence")
        return replace(update, execution_binding=ExecutionBinding.from_runtime_result(
            result, _RuntimeSession(SESSION_ID), evidence_id,
        ))

    def _assert_rejected_or_unchanged(
        self,
        loop: AutonomousLoop,
        update: ObservationUpdate,
        residual: str,
    ) -> None:
        before = loop.snapshot()
        try:
            self._ingest(loop, update)
        except ValueError:
            return
        after = loop.snapshot()
        self.assertEqual(
            (after.state.world_state_hash, after.state.observations,
             after.decision, after.replan),
            (before.state.world_state_hash, before.state.observations,
             before.decision, before.replan),
            residual,
        )

    def _assert_content_mismatch(
        self,
        observation_id: str,
        mutation: Callable[[ObservationRecord], ObservationRecord],
        service: ServiceRecord | None = None,
    ) -> None:
        loop = self._loop()
        result = loop.submit_next()
        bound = self._bound_update(self.fixture, result, observation_id)
        mismatched = replace(bound, observation=mutation(bound.observation), service=service)
        self._assert_rejected_or_unchanged(loop, mismatched, _CONTENT_RESIDUAL)

    @staticmethod
    def _ingest(
        loop: AutonomousLoop,
        update: ObservationUpdate,
        gate_verdict: GateVerdict | None = None,
    ) -> LoopSnapshot:
        with patch(
            "raphael_ibm_bob.observation_model.time.time",
            return_value=FIXED_TIMESTAMP,
        ):
            return loop.ingest(update, D17HardeningTests._verification(update), gate_verdict)

    def test_fabricated_unbound_observation_cannot_drive_replanning(self) -> None:
        # Given: one real action has crossed Runtime -> Broker -> Policy.
        loop = self._loop()
        result = loop.submit_next()
        bound = self._bound_update(self.fixture, result, "O-D17-fabricated")
        forged = replace(bound, evidence_id="E-D17-not-in-ledger")
        before = loop.snapshot()

        # When: a verification claims an evidence id that the ledger cannot resolve.
        with self.assertRaisesRegex(ValueError, "trusted"):
            loop.ingest(forged, self._verification(forged))

        # Then: no trusted state or replacement proposal was created.
        after = loop.snapshot()
        self.assertEqual(after.state.world_state_hash, before.state.world_state_hash)
        self.assertEqual(after.state.observations, ())
        self.assertFalse(after.replan.should_replan)
        self.assertEqual(self.fixture.broker.submissions, 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("result")), 1)

    @unittest.expectedFailure
    def test_stale_observation_cannot_overwrite_newer_state(self) -> None:
        # Given: two newer observations have been executed and folded.
        loop = self._loop()
        first = loop.submit_next()
        first_update = self._bound_update(self.fixture, first, "O-D17-first")
        self._ingest(loop, first_update)
        second = loop.submit_next()
        newer = self._bound_update(
            self.fixture,
            second,
            "O-D17-newer",
            route=ObservationRoute.STATE_CHANGED,
        )
        self._ingest(loop, newer)

        # When: an older, legitimately evidenced result is presented again.
        stale = self._bound_update(
            self.fixture,
            first,
            "O-D17-stale",
            route=ObservationRoute.TERMINAL_REFUSAL,
            source_seq=first.result_seq,
        )

        # Then: rejection or an unchanged trusted snapshot is required.
        self._assert_rejected_or_unchanged(loop, stale, _STALE_RESIDUAL)

    @unittest.expectedFailure
    def test_content_mismatched_capability_cannot_change_trusted_state(self) -> None:
        # Given: a successful Runtime result and its legitimate D16 evidence id.
        self._assert_content_mismatch(
            "O-D17-capability",
            lambda observation: replace(observation, capability_id="WRITE"),
        )

    @unittest.expectedFailure
    def test_content_mismatched_target_cannot_change_trusted_state(self) -> None:
        # Given: a successful Runtime result and its legitimate D16 evidence id.
        self._assert_content_mismatch(
            "O-D17-target",
            lambda observation: replace(
                observation,
                target_host="forged.invalid",
                target_port=65534,
            ),
        )

    @unittest.expectedFailure
    def test_injected_service_cannot_change_trusted_state(self) -> None:
        # Given: a successful Runtime result and its legitimate D16 evidence id.
        injected = ServiceRecord(
            host="injected.invalid",
            port=31337,
            protocol="injected-service",
            discovered_at=0.0,
            source="forged-observation",
        )
        self._assert_content_mismatch(
            "O-D17-service",
            lambda observation: observation,
            injected,
        )

    def test_unregistered_capability_cannot_execute(self) -> None:
        # Given: a capability absent from both the policy allow-list and registry.
        request = ActionRequest(
            sequence=0,
            requester="planner",
            capability=_UnregisteredCapability.D17,
            target="candidate.txt",
            purpose="d17-unregistered-capability",
        )

        # When: the request is submitted through Runtime -> Broker -> Policy.
        result = self.fixture.runtime.submit(request, self.fixture.mission)

        # Then: Policy denies before any adapter or capability invocation.
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.execution)
        self.assertEqual(self.fixture.broker.capability_invocations, 0)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("decision")), 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("result")), 0)

    def test_planner_and_replanner_only_propose_until_runtime_submits(self) -> None:
        # Given: D16 has a planner proposal but no Runtime submission yet.
        loop = self._loop()
        proposal = loop.propose()
        self.assertIsNotNone(proposal.next_action)
        self.assertEqual(self.fixture.broker.submissions, 0)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 0)

        # When: the proposal is submitted, observed, and replanned once.
        first = loop.submit_next()
        first_update = self._bound_update(self.fixture, first, "O-D17-replan")
        snapshot = self._ingest(loop, first_update)
        self.assertTrue(snapshot.replan.should_replan)
        self.assertIsNotNone(snapshot.replan.next_action)

        # Then: the replan remains a proposal until this explicit Runtime call.
        self.assertEqual(self.fixture.broker.submissions, 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 1)
        second = loop.submit_next()
        self.assertTrue(second.broker_result.capability_invoked)
        self.assertEqual(self.fixture.broker.submissions, 2)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 2)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("result")), 2)

    def test_step_bound_stops_without_runaway(self) -> None:
        # Given: a real first action and a one-step stop bound.
        loop = self._loop(stop_config=StopEvaluatorConfig(max_steps=1, max_replans=5))
        first = loop.submit_next()
        update = self._bound_update(self.fixture, first, "O-D17-max-steps")

        # When: the governed observation is ingested.
        snapshot = self._ingest(loop, update)

        # Then: the bound stops the loop and blocks another submission.
        self.assertIs(snapshot.stop, StopCondition.MAX_STEPS)
        self.assertIsNone(snapshot.next_action)
        with self.assertRaisesRegex(RuntimeError, "no next action"):
            loop.submit_next()
        self.assertEqual(self.fixture.broker.submissions, 1)
        self.assertEqual(len(self.fixture.ledger.records_by_kind("request")), 1)

    def test_terminal_state_prevents_further_action(self) -> None:
        # Given: a single real action in a fixture with no replacement step.
        fixture = AutonomousLoopFixture(("stage_a",))
        self.addCleanup(fixture.close)
        loop = self._loop(fixture, StopEvaluatorConfig(max_replans=5))
        first = loop.submit_next()
        update = self._bound_update(fixture, first, "O-D17-terminal")

        # When: the Quality Gate supplies the terminal completion verdict.
        snapshot = self._ingest(loop, update, GateVerdict.COMPLETE)

        # Then: terminal state wins and no action can be submitted afterward.
        self.assertIs(snapshot.stop, StopCondition.MISSION_COMPLETE)
        self.assertIsNone(snapshot.next_action)
        self.assertFalse(snapshot.replan.should_replan)
        with self.assertRaisesRegex(RuntimeError, "no next action"):
            loop.submit_next()
        self.assertEqual(fixture.broker.submissions, 1)
        self.assertEqual(len(fixture.ledger.records_by_kind("request")), 1)
        self.assertEqual(len(fixture.ledger.records_by_kind("result")), 1)


if __name__ == "__main__":
    unittest.main()
