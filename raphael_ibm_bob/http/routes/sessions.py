"""Sessions routes — backed entirely by harness.api."""
from __future__ import annotations

from pathlib import Path

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http import schemas
from raphael_ibm_bob.http.routes._common import (
    body_object,
    mission_from_body,
)


def list_sessions(request, params, config):
    return {"sessions": api.get_sessions(config.sessions_root)}


def create_session(request, params, config):
    body = body_object(request)
    workspace_root = body.get("workspace_root")
    if workspace_root is not None and not isinstance(workspace_root, str):
        raise errors.invalid_input("workspace_root must be a string")
    session = api.create_session(
        mission=mission_from_body(request),
        workspace_root=Path(workspace_root) if workspace_root else None,
        project_name=body.get("project_name", "raphael"),
        model=body.get("model", "unconfigured"),
        provider=body.get("provider", "none"),
        session_id=body.get("session_id"),
        sessions_root=config.sessions_root,
    )
    return 201, schemas.session_json(session)


def get_session(request, params, config):
    session = api.get_session(params["session_id"], config.sessions_root)
    return schemas.session_json(session)


def submit_mission(request, params, config):
    mission = mission_from_body(request)
    if mission is None:
        raise errors.invalid_input("mission is required")
    session = api.submit_mission(
        params["session_id"], mission, config.sessions_root)
    return schemas.session_json(session)


__all__ = ["create_session", "get_session", "list_sessions",
           "submit_mission"]
