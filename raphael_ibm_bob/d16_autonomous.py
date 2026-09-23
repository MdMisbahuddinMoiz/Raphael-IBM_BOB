"""D16 evidence-driven coordination around the frozen D14 seams."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Protocol

from raphael_ibm_bob.contracts import GateVerdict, Mission
from raphael_ibm_bob.d14_planner import NextAction, Planner, SelectionDecision
from raphael_ibm_bob.d14_replan import ReplanDecision
from raphael_ibm_bob.d14_state_codec import ReadOnlyLedgerView
from raphael_ibm_bob.d14_stop import StopCondition, StopEvaluatorConfig, evaluate
from raphael_ibm_bob.d14_world_state import ObservationUpdate, WorldState, reduce_world_state


@unique
class VerificationOutcome(StrEnum):
    """The machine-readable result of an evidence-backed check."""

    VERIFIED = "verified"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """A verification outcome that cannot exist without ledger evidence."""

    verification_id: str
    outcome: VerificationOutcome
    evidence_ids: tuple[str, ...]
    observation_id: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.verification_id or not self.observation_id:
            raise ValueError("verification and observation identities are required")
        if not self.evidence_ids:
            raise ValueError("verification must reference evidence")


class RuntimeBoundary(Protocol):
    """The only execution surface accepted by the autonomous loop."""

    def submit(self, request, mission: Mission):  # noqa: ANN001
        ...


@dataclass(frozen=True, slots=True)
class LoopSnapshot:
    """Immutable coordinator state exposed to callers."""

    state: WorldState
    decision: SelectionDecision
    verification_results: tuple[VerificationResult, ...]
    replan: ReplanDecision
    stop: StopCondition | None

    @property
    def next_action(self) -> NextAction | None:
        """Return the current replacement proposal, never execute it."""
        if self.stop is not None:
            return None
        return self.replan.next_action if self.replan.should_replan else self.decision.next_action


class AutonomousLoop:
    """Coordinate D16 state transitions without invoking capabilities."""

    def __init__(
        self,
        mission: Mission,
        planner: Planner,
        runtime: RuntimeBoundary,
        ledger_view: ReadOnlyLedgerView,
        initial_state: WorldState,
        stop_config: StopEvaluatorConfig = StopEvaluatorConfig(),
    ) -> None:
        self._mission = mission
        self._planner = planner
        self._runtime = runtime
        self._ledger_view = ledger_view
        self._stop_config = stop_config
        decision = planner.plan(initial_state)
        self._last_runtime_result = None
        self._snapshot = LoopSnapshot(
            initial_state,
            decision,
            (),
            ReplanDecision(False, "initial_plan", "", None, None, decision.execution_plan, decision.next_action),
            None,
        )

    def snapshot(self) -> LoopSnapshot:
        """Return the current immutable loop snapshot."""
        return self._snapshot

    def propose(self) -> SelectionDecision:
        """Return a planner proposal without authorization or execution."""
        return self._snapshot.decision

    def submit_next(self):  # noqa: ANN201
        """Submit the proposal through Runtime; planners never execute."""
        action = self._snapshot.next_action
        if action is None:
            raise RuntimeError("autonomous loop has no next action")
        self._last_runtime_result = self._runtime.submit(action.request, self._mission)
        return self._last_runtime_result

    def ingest(
        self,
        update: ObservationUpdate,
        verification: VerificationResult,
        gate_verdict: GateVerdict | None = None,
    ) -> LoopSnapshot:
        """Fold trusted evidence, incorporate its outcome, then replan."""
        self._validate_verification(update, verification)
        state = reduce_world_state(self._snapshot.state, update, self._ledger_view)
        results = (*self._snapshot.verification_results, verification)
        stop = evaluate(state, self._last_runtime_result, gate_verdict, self._stop_config)
        if stop is not None:
            replan = ReplanDecision(False, "terminal_state", self._plan_id(), None, None, None, None)
            self._snapshot = LoopSnapshot(state, self._snapshot.decision, results, replan, stop)
            return self._snapshot
        decision = self._planner.plan(state)
        reason = "verification_falsified" if verification.outcome is VerificationOutcome.FALSIFIED else "observation_changed_state"
        replan = ReplanDecision(True, reason, self._plan_id(), None, None, decision.execution_plan, decision.next_action)
        self._snapshot = LoopSnapshot(state, decision, results, replan, None)
        return self._snapshot

    def _validate_verification(self, update: ObservationUpdate, verification: VerificationResult) -> None:
        if verification.observation_id != update.observation.observation_id:
            raise ValueError("verification observation does not match update")
        if update.evidence_id not in verification.evidence_ids:
            raise ValueError("verification does not reference observation evidence")
        for evidence_id in verification.evidence_ids:
            binding = self._ledger_view.resolve_evidence(evidence_id)
            if binding is None or binding.policy_decision.lower() != "allow" or not binding.result_success:
                raise ValueError("verification evidence is not trusted")

    def _plan_id(self) -> str:
        plan = self._snapshot.decision.execution_plan
        return "" if plan is None else plan.plan_id


__all__ = ["AutonomousLoop", "LoopSnapshot", "RuntimeBoundary", "VerificationOutcome", "VerificationResult"]
