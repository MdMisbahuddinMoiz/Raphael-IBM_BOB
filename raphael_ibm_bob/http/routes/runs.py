"""Runs routes — lifecycle + inspection, all through harness.api."""
from __future__ import annotations

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.providers import ProviderConfigError
from raphael_ibm_bob.http import errors, schemas, security
from raphael_ibm_bob.http.errors import ApiError
from raphael_ibm_bob.http.routes._common import (
    body_object,
    mission_from_body,
    required,
)


def list_runs(request, params, config):
    return {"runs": api.get_runs(config.runs_root)}


def _load_session(config, session_id):
    try:
        security.check_resource_id(session_id, "session_id")
    except ValueError as exc:
        raise errors.bad_request(str(exc)) from None
    try:
        return api.get_session(session_id, config.sessions_root)
    except FileNotFoundError:
        raise errors.not_found(
            errors.SESSION_NOT_FOUND,
            f"session not found: {session_id}") from None


def get_run(request, params, config):
    return schemas.run_json(api.get_run(params["run_id"], config.runs_root))


def create_run(request, params, config):
    """POST /runs — start a Runner-driven governed run."""
    body = body_object(request)
    session = _load_session(config, required(body, "session_id"))
    runner_kwargs = {}
    if "candidate_target" in body:
        runner_kwargs["candidate_target"] = body["candidate_target"]
    if "max_replans" in body:
        runner_kwargs["max_replans"] = int(body["max_replans"])
    if "verification_tests" in body:
        tests = body["verification_tests"]
        if not isinstance(tests, list):
            raise errors.invalid_input("verification_tests must be a list")
        runner_kwargs["verification_tests"] = tuple(tests)
    run = api.start_run(
        session, mission=mission_from_body(request),
        sessions_root=config.sessions_root, runs_root=config.runs_root,
        **runner_kwargs)
    return 201, schemas.run_json(run)


def start_model_run(request, params, config):
    """POST /runs/model — start a model-led governed run.

    Uses the EXISTING provider factory and the EXISTING model loop via
    `harness.api.start_model_run`; it creates no second model loop and
    no second provider. Synchronous: the run completes before the
    response, so the HTTP request bounds the run.
    """
    body = body_object(request)
    session = _load_session(config, required(body, "session_id"))
    provider = body.get("provider", "openai-compatible")
    try:
        model = api.make_model_adapter(provider)
    except ProviderConfigError as exc:
        raise ApiError(503, errors.MODEL_NOT_CONFIGURED, str(exc)) from None
    max_turns = int(body.get("max_turns", config.default_max_turns))
    if max_turns <= 0:
        raise errors.invalid_input("max_turns must be positive")
    result = api.start_model_run(
        session, mission=mission_from_body(request), model=model,
        max_turns=max_turns, sessions_root=config.sessions_root,
        runs_root=config.runs_root)
    return 201, {
        "run": schemas.run_json(result.run),
        "terminal": result.terminal,
        "terminal_reason": result.terminal_reason,
        "turns": result.turns,
        "gate_verdict": result.gate_verdict,
        "tasks": result.task_plan,
    }


def cancel_run(request, params, config):
    """Cooperatively cancel a pending run; report honestly otherwise."""
    run = api.get_run(params["run_id"], config.runs_root)
    if run.state == "pending":
        cancelled = api.cancel_run(params["run_id"], config.runs_root)
        return {"run": schemas.run_json(cancelled), "cancelled": True,
                "note": "pending run cancelled"}
    if run.state == "cancelled":
        return {"run": schemas.run_json(run), "cancelled": False,
                "note": "run already cancelled"}
    if run.state == "running":
        raise errors.conflict(
            errors.RUN_NOT_CANCELLABLE,
            "run is executing synchronously and cannot be force-killed; "
            "the in-flight timeout remains the bound")
    raise errors.conflict(
        errors.RUN_TERMINAL,
        f"run is terminal ({run.state}) and cannot be cancelled")


def _run_id(params):
    return params["run_id"]


def get_events(request, params, config):
    run_id = _run_id(params)
    return {"run_id": run_id,
            "events": [schemas.event_json(e)
                       for e in api.get_events(run_id, config.runs_root)]}


def get_evidence(request, params, config):
    run_id = _run_id(params)
    return {"run_id": run_id,
            "evidence": [schemas.evidence_json(r)
                         for r in api.get_evidence(run_id,
                                                   config.runs_root)]}


def get_artifacts(request, params, config):
    run_id = _run_id(params)
    return {"run_id": run_id,
            "artifacts": [schemas.artifact_json(p)
                          for p in api.get_artifacts(run_id,
                                                     config.runs_root)]}


def get_gate(request, params, config):
    run_id = _run_id(params)
    gate = api.get_gate(run_id, config.runs_root)
    return {"run_id": run_id, "gate": schemas.gate_json(gate)}


def get_seal(request, params, config):
    run_id = _run_id(params)
    ok, reason = api.get_seal(run_id, config.runs_root)
    return {"run_id": run_id, "seal": schemas.seal_json(ok, reason)}


__all__ = [
    "cancel_run",
    "create_run",
    "get_artifacts",
    "get_events",
    "get_evidence",
    "get_gate",
    "get_run",
    "get_seal",
    "list_runs",
    "start_model_run",
]
