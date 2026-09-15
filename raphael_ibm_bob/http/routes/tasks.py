"""Task routes — read-only task decomposition inspection."""
from __future__ import annotations

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http import errors, schemas


def list_tasks(request, params, config):
    """GET /runs/{run_id}/tasks — descriptive orchestration state."""
    run_id = params["run_id"]
    plan = api.get_tasks(run_id, config.runs_root)
    return schemas.tasks_list_json(plan, run_id=run_id)


def _find(node, task_id):
    if node.get("task_id") == task_id:
        return node
    for child in node.get("subtasks", []):
        found = _find(child, task_id)
        if found is not None:
            return found
    return None


def get_task(request, params, config):
    """GET /runs/{run_id}/tasks/{task_id} — one task subtree."""
    run_id = params["run_id"]
    task_id = params["task_id"]
    plan = api.get_tasks(run_id, config.runs_root)
    node = _find(plan.get("root") or {}, task_id)
    if node is None:
        raise errors.not_found(errors.TASK_NOT_FOUND,
                               f"task not found: {task_id}")
    state = plan.get("states", {}).get(task_id)
    task = dict(node)
    task["state"] = state
    return {"run_id": run_id, "task": task}


__all__ = ["get_task", "list_tasks"]
