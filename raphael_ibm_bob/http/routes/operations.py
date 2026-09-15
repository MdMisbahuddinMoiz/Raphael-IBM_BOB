"""Operator screens + controls — orchestration over harness.api.

These routes render HTML views and accept operator control actions
(start, cancel). Every action calls `harness.api`; none touches the
Broker, Policy, Runtime, QualityGate, or the ledger directly. The UI
may ORCHESTRATE the Harness; it may not BYPASS it.
"""
from __future__ import annotations

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.providers import ProviderConfigError
from raphael_ibm_bob.http import errors
from raphael_ibm_bob.http.app import Response, StreamResponse
from raphael_ibm_bob.http.errors import ApiError
from raphael_ibm_bob.http.views import decision_trace as _view
from raphael_ibm_bob.http.views import event_stream as _stream
from raphael_ibm_bob.http.views import operations_console as _console

HTML = "text/html; charset=utf-8"


def decision_trace(request, params, config):
    """GET /operations/{run_id}/decision-trace — read-only operator view."""
    html_doc = _view.render_decision_trace(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def list_operations(request, params, config):
    """GET /operations — list runs + New Operation form."""
    run_ids = api.get_runs(config.runs_root)
    html_doc = _console.render_index(
        run_ids, runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def console(request, params, config):
    """GET /operations/{run_id} — live operator console."""
    html_doc = _console.render_console(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def _load_session(config, session_id):
    try:
        return api.get_session(session_id, config.sessions_root)
    except FileNotFoundError:
        raise errors.not_found(
            errors.SESSION_NOT_FOUND,
            f"session not found: {session_id}") from None


def _as_int(value, fallback):
    if value in (None, ""):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        raise errors.invalid_input("max_turns must be an integer") from None


def start_operation(request, params, config):
    """POST /operations/start — start a governed run (existing API).

    Orchestration only: delegates to `api.start_run` /
    `api.start_model_run`. It never builds its own Runner, ModelAdapter,
    or model loop.
    """
    body = request.body if isinstance(request.body, dict) else {}
    session = _load_session(config, body.get("session_id"))
    mode = body.get("mode", "runner")
    if mode == "model":
        provider = body.get("provider", "openai-compatible")
        try:
            model = api.make_model_adapter(provider)
        except ProviderConfigError as exc:
            raise ApiError(503, errors.MODEL_NOT_CONFIGURED, str(exc)) from None
        result = api.start_model_run(
            session, model=model,
            max_turns=_as_int(body.get("max_turns"),
                              config.default_max_turns),
            sessions_root=config.sessions_root, runs_root=config.runs_root)
        run_id = result.run.run_id
    else:
        runner_kwargs = {}
        target = body.get("candidate_target")
        if target:
            runner_kwargs["candidate_target"] = target
        run = api.start_run(
            session, sessions_root=config.sessions_root,
            runs_root=config.runs_root, **runner_kwargs)
        run_id = run.run_id
    return Response(200, _console.redirect_page(f"/operations/{run_id}"),
                    content_type=HTML)


def cancel_operation(request, params, config):
    """POST /operations/{run_id}/cancel — cooperative cancel (existing API).

    Honest semantics are the Harness's: a pending run cancels; a running
    synchronous run cannot be force-killed; a terminal run is unchanged.
    """
    run = api.cancel_run(params["run_id"], config.runs_root)
    return Response(200, _console.redirect_page(f"/operations/{run.run_id}"),
                    content_type=HTML)


def _cursor(request) -> int:
    last = request.headers.get("last-event-id")
    if last:
        try:
            return max(0, int(last))
        except ValueError:
            pass
    raw = request.query_one("after")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 0
    return 0


def events_stream(request, params, config):
    """GET /runs/{run_id}/events/stream — SSE over the event projection."""
    run_id = params["run_id"]
    api.get_run(run_id, config.runs_root)  # 404 when the run is unknown
    after = _cursor(request)

    def pump(write):
        for frame in _stream.iter_frames(
                run_id, runs_root=config.runs_root, after=after):
            write(frame)

    return StreamResponse(stream=pump)


__all__ = [
    "cancel_operation",
    "console",
    "decision_trace",
    "events_stream",
    "list_operations",
    "start_operation",
]
