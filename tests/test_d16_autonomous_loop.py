"""D16 Wave 1 acceptance matrix for a governed autonomous loop.

Every consumed action is selected by the frozen D14 ``Planner`` and submitted
through ``BOBRuntime -> BOBBroker -> BOBPolicy``. The synthetic observation
adapter binds each observation to the durable result that produced it; the
matrix never constructs Action B or asks a second agent to choose it.
"""
from __future__ import annotations

import unittest

from raphael_ibm_bob.contracts import Decision, GateVerdict
from raphael_ibm_bob.d14_planner import SelectionDecision
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig, evaluate
from raphael_ibm_bob.runtime import RuntimeResult

from tests.d16_autonomous_loop_helpers import (
    AutonomousLoopFixture,
    ObservationRoute,
    ObservationSpec,
    VerificationStatus,
    decision_is_allowed,
    selected_action,
)
from tests.d16_verification_helpers import route_for_verification, verify_listing


class D16AutonomousLoopAcceptance(unittest.TestCase):
    """The eight required state-to-action acceptance rows."""

    def _fixture(
        self,
        initial_protocols: tuple[str, ...] = ("stage_a", "stage_b"),
    ) -> AutonomousLoopFixture:
        fixture = AutonomousLoopFixture(initial_protocols)
        self.addCleanup(fixture.close)
        return fixture

    def _execute_first(
        self,
        fixture: AutonomousLoopFixture,
    ) -> tuple[SelectionDecision, RuntimeResult]:
        first_decision = fixture.planner.plan(fixture.state)
        first_result = fixture.consume(first_decision)
        fixture.fold(
            fixture.observation_from_result(
                first_result,
                ObservationSpec("O-D16-A"),
            ),
        )
        return first_decision, first_result

    def _assert_consumed_success(self, result: RuntimeResult) -> None:
        self.assertTrue(decision_is_allowed(result))
        execution = result.execution
        self.assertIsNotNone(execution)
        assert execution is not None
        self.assertTrue(execution.success)

    def test_no_change_observation_preserves_and_consumes_next_action(self) -> None:
        # Given: Action A has produced a governed observation and Action B is
        # the planner's pre-Observation-B baseline.
        fixture = self._fixture()
        _first, first_result = self._execute_first(fixture)
        baseline_state = fixture.state
        baseline_decision = fixture.planner.plan(baseline_state)
        baseline_action = selected_action(baseline_decision)

        # When: the same bound observation arrives again and changes no state.
        fixture.fold(
            fixture.observation_from_result(
                first_result,
                ObservationSpec("O-D16-A"),
            ),
        )
        next_decision = fixture.planner.plan(fixture.state)
        action_b = selected_action(next_decision)

        # Then: the selected Action B remains equivalent and is consumed by
        # Runtime; it is not a test-injected request.
        self.assertEqual(fixture.state.world_state_hash, baseline_state.world_state_hash)
        self.assertEqual(action_b, baseline_action)
        self._assert_consumed_success(fixture.consume(next_decision))

    def test_state_change_selects_genuinely_different_consumed_action(self) -> None:
        # Given: Action B is selected before its Observation B exists.
        fixture = self._fixture()
        _first, _first_result = self._execute_first(fixture)
        before_observation_b = fixture.state
        baseline_decision = fixture.planner.plan(before_observation_b)
        baseline_action = selected_action(baseline_decision)
        baseline_result = fixture.consume(baseline_decision)

        # When: Observation B adds a new normalized fact and is folded.
        fixture.fold(
            fixture.observation_from_result(
                baseline_result,
                ObservationSpec("O-D16-B-state-change", route=ObservationRoute.STATE_CHANGED),
            ),
        )
        after_observation_b = fixture.state
        replanned = fixture.planner.plan(after_observation_b)
        action_b = selected_action(replanned)

        # Then: the central acceptance assertion proves causality, not merely
        # a changed variable: the same planner gives baseline before B and a
        # genuinely different action after the new state is available.
        self.assertNotEqual(
            fixture.planner.plan(before_observation_b).next_action,
            action_b,
        )
        self.assertEqual(
            fixture.planner.plan(before_observation_b).next_action,
            baseline_action,
        )
        self.assertEqual(
            fixture.planner.plan(after_observation_b).next_action,
            action_b,
        )
        self.assertNotEqual(
            before_observation_b.world_state_hash,
            after_observation_b.world_state_hash,
        )
        self.assertNotEqual(
            baseline_decision.execution_plan.plan_id,
            replanned.execution_plan.plan_id,
        )
        self.assertEqual(action_b.capability_id, "SEARCH")
        self._assert_consumed_success(fixture.consume(replanned))

    def test_verification_success_advances_from_confirmed_hypothesis(self) -> None:
        # Given: a governed Action B is the baseline for a deterministic check.
        fixture = self._fixture()
        _first, _first_result = self._execute_first(fixture)
        baseline_state = fixture.state
        baseline_decision = fixture.planner.plan(baseline_state)
        baseline_action = selected_action(baseline_decision)
        verification_execution = fixture.consume(baseline_decision)
        verification = verify_listing(
            verification_execution,
            expected_marker="candidate.txt",
        )

        # When: the successful verification observation is folded into state.
        fixture.fold(
            fixture.observation_from_result(
                verification_execution,
                ObservationSpec("O-D16-B-verified", route=route_for_verification(verification)),
            ),
        )
        replanned = fixture.planner.plan(fixture.state)
        action_b = selected_action(replanned)

        # Then: confirmation is factual, the planner advances, and its result
        # is consumed through the same governed boundary.
        self.assertIs(verification.status, VerificationStatus.CONFIRMED)
        self.assertEqual(baseline_decision.next_action, baseline_action)
        self.assertNotEqual(action_b, baseline_action)
        self.assertEqual(action_b.capability_id, "SEARCH")
        self._assert_consumed_success(fixture.consume(replanned))

    def test_verification_failure_changes_course_to_recovery_action(self) -> None:
        # Given: a governed Action B is the baseline for a falsifiable check.
        fixture = self._fixture()
        _first, _first_result = self._execute_first(fixture)
        baseline_decision = fixture.planner.plan(fixture.state)
        baseline_action = selected_action(baseline_decision)
        verification_execution = fixture.consume(baseline_decision)
        verification = verify_listing(
            verification_execution,
            expected_marker="marker-that-is-not-present",
        )

        # When: the falsifying observation is folded into the governed state.
        fixture.fold(
            fixture.observation_from_result(
                verification_execution,
                ObservationSpec("O-D16-B-falsified", route=route_for_verification(verification)),
            ),
        )
        replanned = fixture.planner.plan(fixture.state)
        action_b = selected_action(replanned)

        # Then: the planner changes course from the baseline and the recovery
        # action is the planner result consumed through Runtime.
        self.assertIs(verification.status, VerificationStatus.FALSIFIED)
        self.assertNotEqual(action_b, baseline_action)
        self.assertEqual(action_b.capability_id, "WRITE")
        recovery = fixture.consume(replanned)
        self._assert_consumed_success(recovery)
        self.assertEqual(
            (fixture.root / "recovery.txt").read_text(encoding="utf-8"),
            "d16-recovery",
        )

    def test_terminal_success_stops_before_selecting_unnecessary_action(self) -> None:
        # Given: a new governed state exists after Action A.
        fixture = self._fixture(("stage_a",))
        _first, first_result = self._execute_first(fixture)
        self.assertEqual(fixture.state.revision, 1)
        planner_calls_before_stop = fixture.selector.plan_calls

        # When: the mission gate confirms the terminal success condition.
        stop = evaluate(
            fixture.state,
            first_result,
            GateVerdict.COMPLETE,
            StopEvaluatorConfig(),
        )

        # Then: terminal success wins and no replacement request is selected
        # or submitted after the gate.
        self.assertIs(stop, StopCondition.MISSION_COMPLETE)
        self.assertEqual(fixture.selector.plan_calls, planner_calls_before_stop)
        self.assertEqual(len(fixture.ledger.records_by_kind("request")), 1)

    def test_terminal_refusal_denies_state_required_ungoverned_action(self) -> None:
        # Given: a new state requires a Telnet action outside the HTTP-only
        # authorization profile.
        fixture = self._fixture()
        first_decision, _first_result = self._execute_first(fixture)
        baseline_decision = fixture.planner.plan(fixture.state)
        baseline_result = fixture.consume(baseline_decision)
        fixture.fold(
            fixture.observation_from_result(
                baseline_result,
                ObservationSpec("O-D16-terminal-refusal", route=ObservationRoute.TERMINAL_REFUSAL),
            ),
        )
        refusal_decision = fixture.planner.plan(fixture.state)
        action_b = selected_action(refusal_decision)

        # When: the planner-selected request traverses Runtime -> Broker ->
        # Policy.
        refusal = fixture.consume(refusal_decision)
        stop = evaluate(
            fixture.state,
            refusal.broker_result.decision,
            GateVerdict.REFUSE,
            StopEvaluatorConfig(),
        )

        # Then: the action is genuinely state-selected but Policy refuses it;
        # no execution result or observation is manufactured.
        self.assertNotEqual(action_b, selected_action(first_decision))
        self.assertEqual(action_b.capability_id, "NETWORK_TELNET_SESSION")
        self.assertIs(refusal.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(refusal.broker_result.capability_invoked)
        self.assertIsNone(refusal.execution)
        self.assertIs(stop, StopCondition.POLICY_DENIAL)
        self.assertEqual(len(fixture.state.observations), 2)
        self.assertEqual(len(fixture.ledger.records_by_kind("result")), 2)

    def test_provenance_mismatch_cannot_drive_trusted_replanning(self) -> None:
        # Given: a baseline planner action and a real successful execution.
        fixture = self._fixture(("stage_a",))
        baseline_decision = fixture.planner.plan(fixture.state)
        baseline_action = selected_action(baseline_decision)
        first_result = fixture.consume(baseline_decision)
        before_hash = fixture.state.world_state_hash

        # When: an observation with a fabricated session binding is submitted.
        forged = fixture.observation_from_result(
            first_result,
            ObservationSpec("O-D16-forged", route=ObservationRoute.STAGE_B, observation_session="fabricated-session"),
        )
        with self.assertRaisesRegex(ValueError, "invalid observation provenance"):
            fixture.fold(forged)
        replanned = fixture.planner.plan(fixture.state)

        # Then: the trusted snapshot and selected action remain unchanged.
        self.assertEqual(fixture.state.world_state_hash, before_hash)
        self.assertEqual(selected_action(replanned), baseline_action)
        self.assertEqual(len(fixture.state.observations), 0)

    def test_stale_observation_cannot_overwrite_newer_governed_state(self) -> None:
        # Given: a newer Observation B has already selected a state-derived
        # follow-up action.
        fixture = self._fixture()
        _first, first_result = self._execute_first(fixture)
        baseline_decision = fixture.planner.plan(fixture.state)
        baseline_result = fixture.consume(baseline_decision)
        fixture.fold(
            fixture.observation_from_result(
                baseline_result,
                ObservationSpec("O-D16-newer", route=ObservationRoute.STATE_CHANGED),
            ),
        )
        newer_decision = fixture.planner.plan(fixture.state)
        newer_action = selected_action(newer_decision)
        newer_hash = fixture.state.world_state_hash
        newer_source_seq = fixture.state.last_source_seq

        # When: an older, bound observation arrives with a lower source seq.
        stale = fixture.observation_from_result(
            first_result,
            ObservationSpec("O-D16-stale", route=ObservationRoute.TERMINAL_REFUSAL, source_seq=first_result.result_seq),
        )
        fixture.fold(stale)
        after_stale = fixture.planner.plan(fixture.state)

        # Then: the newer state and Action B remain authoritative, and the
        # still-selected planner result is the one that gets executed.
        self.assertEqual(fixture.state.world_state_hash, newer_hash)
        self.assertEqual(fixture.state.last_source_seq, newer_source_seq)
        self.assertEqual(selected_action(after_stale), newer_action)
        self._assert_consumed_success(fixture.consume(after_stale))


if __name__ == "__main__":
    unittest.main()
