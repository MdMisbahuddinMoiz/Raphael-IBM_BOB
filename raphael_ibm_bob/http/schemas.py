"""raphael_ibm_bob.http.schemas — stable JSON projections.

Explicit, whitelisted JSON shapes for the presentation layer. These are
NOT `asdict` dumps: every field is chosen deliberately so internal
objects, filesystem details, and (crucially) secrets never leak by
accident. Read-only; no transformation changes authoritative state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def session_json(session) -> Dict[str, Any]:
    """Session reference (names/model only; never credentials)."""
    return {
        "session_id": session.session_id,
        "mission": session.mission.to_dict() if session.mission else None,
        "workspace": (session.workspace.to_dict()
                      if session.workspace else None),
        "model": session.model,
        "provider": session.provider,
        "status": session.status,
        "current_run_id": session.current_run_id,
        "run_ids": list(session.run_ids),
        "created_at": session.created_at,
    }


def run_json(run) -> Dict[str, Any]:
    """Run record: references and verdict, not duplicated truth."""
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "mission": run.mission.to_dict(),
        "workspace_root": run.workspace_root,
        "state": run.state,
        "terminal": run.is_terminal(),
        "gate_verdict": run.gate_verdict,
        "plan_ids": list(run.plan_ids),
        "finding_ids": list(run.finding_ids),
        "failure_reason": run.failure_reason,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def event_json(event: Dict[str, Any]) -> Dict[str, Any]:
    """Event projection (already a plain ledger-derived dict)."""
    return dict(event)


def evidence_json(record: Dict[str, Any]) -> Dict[str, Any]:
    """One persisted evidence/ledger record (authoritative, read-only)."""
    return dict(record)


def artifact_json(path: Path) -> Dict[str, Any]:
    """Artifact descriptor: name + size (never an absolute path)."""
    size: Optional[int]
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    return {"name": path.name, "size": size}


def gate_json(gate: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The last persisted QualityGate record, or None."""
    return dict(gate) if gate is not None else None


def seal_json(ok: bool, reason: str) -> Dict[str, Any]:
    """Seal verification result."""
    return {"ok": bool(ok), "reason": reason}


def workspace_json(view: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only workspace description (already a plain dict)."""
    return dict(view)


def role_json(role) -> Dict[str, Any]:
    """Declared specialist role (declaration, never a grant)."""
    return {
        "id": role.id,
        "name": role.name,
        "purpose": role.purpose,
        "capabilities": sorted(c.value for c in role.capabilities),
    }


def capability_json(definition) -> Dict[str, Any]:
    """Declared capability definition."""
    return {
        "capability": definition.capability.value,
        "description": definition.description,
        "target_schema": definition.target_schema,
        "purpose_template": definition.purpose_template,
        "verification_expectation": definition.verification_expectation,
        "version": definition.version,
        "timeout_seconds": definition.timeout_seconds,
        "evidence_produced": list(definition.evidence_produced),
        "evidence_consumed": list(definition.evidence_consumed),
    }


def skill_json(skill) -> Dict[str, Any]:
    """Declared skill definition (challenge callables are not exposed)."""
    return {
        "id": skill.id,
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "capability": skill.capability.value,
        "role": skill.role,
        "target_schema": skill.target_schema,
        "purpose_template": skill.purpose_template,
        "success_markers": list(skill.success_markers),
        "evidence_produced": list(skill.evidence_produced),
        "evidence_consumed": list(skill.evidence_consumed),
        "prerequisites": list(skill.prerequisites),
    }


def task_json(task, states: Optional[Dict[str, str]] = None
              ) -> Dict[str, Any]:
    """A task subtree with its orchestration state (descriptive only)."""
    data = task.to_dict()
    state = (states or {}).get(task.task_id)
    data["state"] = state.value if hasattr(state, "value") else state
    return data


def task_plan_json(plan: Dict[str, Any],
                   run_id: Optional[str] = None) -> Dict[str, Any]:
    """A TaskPlan.to_dict() projection, tagged with its run."""
    return {
        "run_id": run_id,
        "root": plan.get("root"),
        "states": plan.get("states", {}),
    }


def tasks_list_json(plan: Dict[str, Any],
                    run_id: Optional[str] = None) -> Dict[str, Any]:
    """Flattened task list (id/name/role/skills/state), deterministic."""
    states = plan.get("states", {})
    tasks: List[Dict[str, Any]] = []

    def _visit(node: Dict[str, Any]) -> None:
        tasks.append({
            "task_id": node.get("task_id"),
            "name": node.get("name"),
            "description": node.get("description"),
            "role": node.get("role"),
            "skills": list(node.get("skills", [])),
            "state": states.get(node.get("task_id")),
        })
        for child in node.get("subtasks", []):
            _visit(child)

    root = plan.get("root")
    if root is not None:
        _visit(root)
    return {"run_id": run_id, "tasks": tasks, "states": dict(states)}


__all__ = [
    "artifact_json",
    "capability_json",
    "event_json",
    "evidence_json",
    "gate_json",
    "role_json",
    "run_json",
    "seal_json",
    "session_json",
    "skill_json",
    "task_json",
    "task_plan_json",
    "tasks_list_json",
    "workspace_json",
]
