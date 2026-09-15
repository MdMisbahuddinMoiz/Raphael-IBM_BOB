"""raphael_ibm_bob.harness.model — model interaction boundary.

The model PROPOSES; RAPHAEL decides and executes. This module defines
only the seam: what context goes in, what structured proposal comes
out. There is deliberately no provider implementation here — no LLM
credentials, endpoints, or routing exist in this repository. The one
concrete adapter, `ScriptedModelAdapter`, is an explicitly labeled
deterministic test double (scripted replies for tests/demos), never
presented as a working model provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable

from raphael_ibm_bob.contracts import ActionRequest, Finding, Mission


@dataclass(frozen=True)
class ModelContext:
    """What the Harness shows the model: mission + current state.

    Deliberately small (same discipline as FocusedContext): the model
    sees the mission, finding summaries with states, workspace
    facts, a bounded file listing, and recent turn outcomes — never
    credentials, never raw policy internals, never the full ledger.
    """
    mission: Mission
    findings: List[Finding] = field(default_factory=list)
    workspace_root: str = ""
    evidence_count: int = 0
    workspace_files: Tuple[str, ...] = ()
    recent_turns: Tuple[Dict[str, Any], ...] = ()
    session_id: str = ""

    def summary(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission.mission_id,
            "description": self.mission.description,
            "scope": self.mission.scope,
            "findings": [
                {"finding_id": f.finding_id,
                 "state": f.state.value,
                 "target": f.target} for f in self.findings
            ],
            "workspace_root": self.workspace_root,
            "evidence_count": self.evidence_count,
            "workspace_files": list(self.workspace_files),
            "recent_turns": list(self.recent_turns),
            "session_id": self.session_id,
        }


@runtime_checkable
class ModelAdapter(Protocol):
    """Boundary every model integration must satisfy."""

    def propose(self, context: ModelContext) -> ActionRequest:
        """Return ONE proposed action for the given context.

        The proposal is an ordinary ActionRequest the Harness submits
        through Runtime -> Broker -> Policy. Returning a proposal
        grants nothing; Policy may still deny it.
        """
        ...


class ScriptedModelAdapter:
    """Deterministic test double: canned proposals keyed by mission.

    NOT a model provider. Used by tests and scripted demos so the
    Harness interaction path executes without network or credentials.
    Unknown missions raise KeyError loudly instead of inventing an
    action.
    """

    def __init__(self, proposals: Dict[str, ActionRequest]):
        self._proposals = dict(proposals)

    def propose(self, context: ModelContext) -> ActionRequest:
        try:
            return self._proposals[context.mission.mission_id]
        except KeyError:
            raise KeyError(
                f"scripted adapter has no proposal for mission "
                f"{context.mission.mission_id!r}") from None


__all__ = [
    "ModelAdapter",
    "ModelContext",
    "ScriptedModelAdapter",
]
