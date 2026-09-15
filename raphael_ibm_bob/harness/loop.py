"""raphael_ibm_bob.harness.loop — model turn driver around the core.

One turn = model proposes, Harness submits through Runtime/Broker/
Policy, observation recorded. The loop coordinates turns; it performs
NO verification, falsification, replanning, or gating itself — those
remain the Runner's and the QualityGate's job (call `Runner.run` or
the verifier/falsifier directly with loop observations).

Terminal states are explicit data, never exceptions escaping:
`done` (model declared intent=done), `max-turns`, `model-error`
(malformed proposal, provider failure, unknown mission),
`runtime-error` (broker rejection such as an invalid timeout).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.model import ModelAdapter, ModelContext
from raphael_ibm_bob.harness.providers import (
    DoneSignal,
    ProviderError,
    StructuredProposalError,
)
from raphael_ibm_bob.runtime import BOBRuntime

TERMINAL_STATES = ("done", "max-turns", "model-error", "runtime-error")


@dataclass
class TurnRecord:
    """One observed turn: proposal, governed outcome, evidence refs."""
    index: int
    request: Dict[str, Any]
    decision: Optional[str] = None
    deny_reason: Optional[str] = None
    executed: bool = False
    success: Optional[bool] = None
    evidence_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LoopOutcome:
    """Terminal result of `drive_turns`."""
    turns: List[TurnRecord]
    terminal: str
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turns": [t.to_dict() for t in self.turns],
            "terminal": self.terminal,
            "reason": self.reason,
        }


def _turn_summary(record: "TurnRecord") -> Dict[str, Any]:
    """Compact observation of one governed turn for the next context."""
    return {
        "capability": record.request.get("capability"),
        "target": record.request.get("target"),
        "decision": record.decision,
        "executed": record.executed,
        "success": record.success,
        "error": (record.error or "")[:300],
    }


def drive_turns(*, model: ModelAdapter, runtime: BOBRuntime,
                mission: Mission,
                store: Optional[FindingStore] = None,
                workspace_root: str = "",
                workspace_files: Tuple[str, ...] = (),
                history_window: int = 5,
                max_turns: int = 5) -> LoopOutcome:
    """Run model turns until a terminal state (bounded by max_turns).

    Each turn's context carries finding states plus the recent turn
    outcomes, so the model observes governed results (including
    denials) and can adapt. Nothing here verifies or gates: use the
    Verifier/Falsifier/QualityGate on the resulting evidence.
    """
    if max_turns < 1:
        raise ValueError("max_turns must be >= 1")
    turns: List[TurnRecord] = []
    for index in range(max_turns):
        findings = list(store.all()) if store is not None else []
        context = ModelContext(
            mission=mission, findings=findings,
            workspace_root=workspace_root,
            evidence_count=sum(1 for _ in _iter_evidence(runtime)),
            workspace_files=tuple(workspace_files),
            recent_turns=tuple(
                _turn_summary(t) for t in turns[-history_window:]),
        )
        try:
            request = model.propose(context)
        except DoneSignal:
            return LoopOutcome(turns=turns, terminal="done",
                               reason="model declared done")
        except (StructuredProposalError, ProviderError, KeyError) as exc:
            return LoopOutcome(
                turns=turns, terminal="model-error",
                reason=f"{type(exc).__name__}:{exc}")
        record = TurnRecord(index=index,
                            request=request.to_dict())
        try:
            result = runtime.submit(request, mission)
        except Exception as exc:  # broker rejection et al: recorded
            record.error = f"{type(exc).__name__}:{exc}"
            turns.append(record)
            return LoopOutcome(turns=turns, terminal="runtime-error",
                               reason=record.error)
        record.decision = result.broker_result.decision.decision.value
        record.deny_reason = result.broker_result.decision.reason
        record.executed = result.broker_result.capability_invoked
        if result.execution is not None:
            record.success = result.execution.success
        record.evidence_ids = list(result.evidence_ids)
        turns.append(record)
    return LoopOutcome(turns=turns, terminal="max-turns",
                       reason=f"reached max_turns={max_turns}")


def _iter_evidence(runtime: BOBRuntime):
    """Yield evidence ids observed so far (ledger-backed)."""
    ledger = runtime.broker.ledger
    if ledger is None:
        return
    for rec in ledger.all_records():
        if rec.get("kind") == "evidence":
            yield rec.get("evidence_id")


__all__ = [
    "TERMINAL_STATES",
    "TurnRecord",
    "LoopOutcome",
    "drive_turns",
]
