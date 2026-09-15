"""raphael_ibm_bob.harness.session — session + workspace context.

A session binds a mission, a workspace, and a sequence of runs. It
carries NO execution logic: runs are driven by `harness.run.start_run`
against the existing Runner, and the ledger remains the source of
truth (the session file only references run IDs).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.workspace import Workspace


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkspaceContext:
    """Harness view of a workspace: identity + run association.

    Containment rules stay in `Workspace`; this only names the
    project directory a session works in and which runs used it.
    """
    workspace_root: str
    project_name: str
    run_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_workspace(cls, workspace: Workspace,
                       project_name: str) -> "WorkspaceContext":
        return cls(workspace_root=str(workspace.root),
                   project_name=project_name)


@dataclass
class RaphaelSession:
    """One Harness session: mission intake + run references.

    `provider`/`model` are a *reference* (names only) to the model
    configuration — never credentials, keys, or auth headers. `status`
    is the session state; `run_ids` is the ordered run history.
    """
    session_id: str
    mission: Optional[Mission] = None
    workspace: Optional[WorkspaceContext] = None
    model: str = "unconfigured"
    provider: str = "none"
    status: str = "open"
    current_run_id: Optional[str] = None
    run_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    def add_run(self, run_id: str) -> None:
        """Record a run against this session (idempotent)."""
        if run_id not in self.run_ids:
            self.run_ids.append(run_id)
        self.current_run_id = run_id
        if self.workspace is not None and \
                run_id not in self.workspace.run_ids:
            self.workspace.run_ids.append(run_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mission": self.mission.to_dict() if self.mission else None,
            "workspace": (self.workspace.to_dict()
                          if self.workspace else None),
            "model": self.model,
            "provider": self.provider,
            "status": self.status,
            "current_run_id": self.current_run_id,
            "run_ids": list(self.run_ids),
            "created_at": self.created_at,
        }

    @classmethod
    def create(cls, mission: Optional[Mission] = None,
               workspace: Optional[WorkspaceContext] = None,
               model: str = "unconfigured",
               provider: str = "none",
               session_id: Optional[str] = None) -> "RaphaelSession":
        return cls(
            session_id=session_id or uuid.uuid4().hex[:12],
            mission=mission,
            workspace=workspace,
            model=model,
            provider=provider,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RaphaelSession":
        mission = None
        if data.get("mission"):
            mission = Mission(**data["mission"])
        workspace = None
        if data.get("workspace"):
            workspace = WorkspaceContext(**data["workspace"])
        return cls(
            session_id=data["session_id"],
            mission=mission,
            workspace=workspace,
            model=data.get("model", "unconfigured"),
            provider=data.get("provider", "none"),
            status=data.get("status", "open"),
            current_run_id=data.get("current_run_id"),
            run_ids=list(data.get("run_ids", [])),
            created_at=data.get("created_at", _utcnow()),
        )


def _session_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "session.json"


def save_session(session: RaphaelSession,
                 sessions_root: Path) -> Path:
    """Persist a session; returns the file path."""
    path = _session_path(sessions_root, session.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return path


def load_session(session_id: str, sessions_root: Path) -> RaphaelSession:
    """Reload a persisted session; raises FileNotFoundError if absent."""
    path = _session_path(sessions_root, session_id)
    return RaphaelSession.from_dict(
        json.loads(path.read_text(encoding="utf-8")))


def list_sessions(sessions_root: Path) -> List[str]:
    """Return persisted session ids, sorted (empty if none)."""
    root = Path(sessions_root)
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "session.json").is_file())


__all__ = [
    "RaphaelSession",
    "WorkspaceContext",
    "load_session",
    "save_session",
    "list_sessions",
]
