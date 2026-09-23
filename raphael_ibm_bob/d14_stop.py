"""Pure D14 stop evaluation and coordinator-facing audit payloads."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, NotRequired, TypedDict

from raphael_ibm_bob.contracts import Decision, GateVerdict

# Provenance: harness/loop.py:113-128.
MAX_STEPS: Final = 5
# Provenance: runner.py:170-214.
MAX_REPLANS: Final = 1
# New, not-yet-ratified D14 bound.
MAX_FAILURES: Final = 5
# New, not-yet-ratified D14 bound.
NO_PROGRESS_WINDOW: Final = 3
# New, not-yet-ratified D14 bound.
CONFIDENCE_THRESHOLD_BPS: Final = 2000


@unique
class StopCondition(StrEnum):
    """Closed set of reasons for returning control to the coordinator."""

    MAX_STEPS = "max_steps"
    MAX_REPLANS = "max_replans"
    MAX_FAILURES = "max_failures"
    NO_PROGRESS = "no_progress"
    NO_APPLICABLE_CAPABILITY = "no_applicable_capability"
    MISSION_COMPLETE = "mission_complete"
    POLICY_DENIAL = "policy_denial"
    CONFIDENCE_THRESHOLD = "confidence_threshold"


@dataclass(frozen=True, slots=True)
class StopEvaluatorConfig:
    """Explicit bounds and state history used by the pure evaluator."""

    max_steps: int = MAX_STEPS
    max_replans: int = MAX_REPLANS
    max_failures: int = MAX_FAILURES
    no_progress_window: int = NO_PROGRESS_WINDOW
    confidence_threshold_bps: int = CONFIDENCE_THRESHOLD_BPS
    prior_world_states: tuple[object, ...] = ()  # noqa: ANN401, OBJECT_OK


class StopAuditPayload(TypedDict):
    """Serializable stop data for the outer coordinator to persist."""

    producer: str
    kind: str
    reason: str
    step_count: int
    max_steps: int
    replan_count: int
    max_replans: int
    failure_count: int
    max_failures: int
    world_state_hash: str
    plan_id: str | None
    request_seq: int | None
    deny_reason: str | None
    confidence: int | None
    threshold: int


class RunFinalizePayload(TypedDict):
    """Coordinator-facing finalization marker returned by D14."""

    producer: str
    kind: str
    reason: str
    condition: str | None
    world_state_hash: str
    plan_id: str | None


def evaluate(world_state, last_runtime_result, gate_evaluation, config: StopEvaluatorConfig) -> StopCondition | None:  # noqa: ANN001
    """Return the first applicable stop condition without side effects."""
    if _gate_verdict(gate_evaluation) is GateVerdict.COMPLETE:
        return StopCondition.MISSION_COMPLETE
    if _is_policy_denial(last_runtime_result):
        return StopCondition.POLICY_DENIAL
    if _has_no_applicable_capability(last_runtime_result):
        return StopCondition.NO_APPLICABLE_CAPABILITY
    if world_state.step_count >= config.max_steps:
        return StopCondition.MAX_STEPS
    if world_state.replan_count >= config.max_replans:
        return StopCondition.MAX_REPLANS
    if world_state.failure_count >= config.max_failures:
        return StopCondition.MAX_FAILURES
    if _has_no_progress(world_state, config):
        return StopCondition.NO_PROGRESS
    if _confidence_reached(last_runtime_result, config.confidence_threshold_bps):
        return StopCondition.CONFIDENCE_THRESHOLD
    return None


def stop_audit_payload(world_state, condition: StopCondition, *, plan_id: str | None = None, request_seq: int | None = None, deny_reason: str | None = None, confidence: int | None = None, config: StopEvaluatorConfig = StopEvaluatorConfig()) -> StopAuditPayload:  # noqa: ANN001
    """Build, but do not persist, the required stop audit payload."""
    return {
        "producer": "planner",
        "kind": f"stop-{condition.value}",
        "reason": condition.value,
        "step_count": world_state.step_count,
        "max_steps": config.max_steps,
        "replan_count": world_state.replan_count,
        "max_replans": config.max_replans,
        "failure_count": world_state.failure_count,
        "max_failures": config.max_failures,
        "world_state_hash": world_state.world_state_hash,
        "plan_id": plan_id,
        "request_seq": request_seq,
        "deny_reason": deny_reason,
        "confidence": confidence,
        "threshold": config.confidence_threshold_bps,
    }


def run_finalize_payload(world_state, condition: StopCondition | None, *, plan_id: str | None = None) -> RunFinalizePayload:  # noqa: ANN001
    """Build, but do not persist, the run-finalization payload."""
    return {
        "producer": "planner",
        "kind": "run-finalize",
        "reason": condition.value if condition is not None else "run_complete",
        "condition": condition.value if condition is not None else None,
        "world_state_hash": world_state.world_state_hash,
        "plan_id": plan_id,
    }


def _gate_verdict(gate_evaluation) -> GateVerdict | None:  # noqa: ANN001
    value = getattr(gate_evaluation, "verdict", gate_evaluation)
    try:
        return GateVerdict(value)
    except (TypeError, ValueError):
        return None


def _is_policy_denial(result) -> bool:  # noqa: ANN001
    decision = getattr(result, "decision", None)
    if decision is None:
        decision = getattr(getattr(result, "policy_decision", None), "decision", None)
    try:
        return Decision(decision) is Decision.DENY
    except (TypeError, ValueError):
        return False


def _has_no_applicable_capability(result) -> bool:  # noqa: ANN001
    rationale = getattr(result, "rationale_codes", ())
    next_action = getattr(result, "next_action", None)
    return "NO_APPLICABLE_CAPABILITY" in rationale and next_action is None


def _has_no_progress(world_state, config: StopEvaluatorConfig) -> bool:
    history = (*config.prior_world_states, world_state)
    window = config.no_progress_window
    if window <= 0 or len(history) < window:
        return False
    recent = history[-window:]
    return len({(item.world_state_hash, item.progress_token) for item in recent}) == 1


def _confidence_reached(result, threshold: int) -> bool:  # noqa: ANN001
    confidence = getattr(result, "confidence_bps", None)
    return isinstance(confidence, int) and confidence >= threshold


__all__ = [
    "CONFIDENCE_THRESHOLD_BPS",
    "MAX_FAILURES",
    "MAX_REPLANS",
    "MAX_STEPS",
    "NO_PROGRESS_WINDOW",
    "RunFinalizePayload",
    "StopAuditPayload",
    "StopCondition",
    "StopEvaluatorConfig",
    "evaluate",
    "run_finalize_payload",
    "stop_audit_payload",
]
