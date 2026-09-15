"""Workspace routes — read-only description, never execution."""
from __future__ import annotations

from pathlib import Path

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http import errors, schemas


def get_workspace(request, params, config):
    """GET /workspaces/{workspace_id} — read-only description.

    `workspace_id` is the URL-encoded workspace root path. This never
    executes anything: there is deliberately no execution endpoint.
    """
    raw = params["workspace_id"]
    root = Path(raw)
    if not root.is_dir():
        raise errors.not_found(
            errors.WORKSPACE_NOT_FOUND, f"workspace not found: {raw}")
    view = api.describe_workspace(
        root, sessions_root=config.sessions_root,
        runs_root=config.runs_root)
    return schemas.workspace_json(view)


__all__ = ["get_workspace"]
