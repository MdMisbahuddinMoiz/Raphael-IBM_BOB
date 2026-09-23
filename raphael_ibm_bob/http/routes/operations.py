"""Operator screens + controls — orchestration over harness.api.

These routes render HTML views and accept operator control actions
(start, cancel). Every action calls `harness.api`; none touches the
Broker, Policy, Runtime, QualityGate, or the ledger directly. The UI
may ORCHESTRATE the Harness; it may not BYPASS it.
"""
from __future__ import annotations

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.providers import ProviderConfigError
from raphael_ibm_bob.http import errors, security
from raphael_ibm_bob.http.app import Response, StreamResponse
from raphael_ibm_bob.http.errors import ApiError
from raphael_ibm_bob.http.views import decision_trace as _view
from raphael_ibm_bob.http.views import event_stream as _stream
from raphael_ibm_bob.http.views import event_stream_page as _events_page
from raphael_ibm_bob.http.views import network_console as _network
from raphael_ibm_bob.http.views import operations_console as _console
from raphael_ibm_bob.mode import Mode, TestingProfile, get_mode_manager
from raphael_ibm_bob.target_profile import get_target_store
from raphael_ibm_bob.vpn import get_vpn_manager

HTML = "text/html; charset=utf-8"


def decision_trace(request, params, config):
    """GET /operations/{run_id}/decision-trace — read-only operator view."""
    html_doc = _view.render_decision_trace(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def network(request, params, config):
    """GET /operations/network — HTB VPN operator screen (D7).

    Reads the VPN manager's safe status snapshot. Presentation only: the
    page drives the VPN lifecycle through the /vpn/* API; it never
    executes a capability and never touches the governance core.
    """
    manager = getattr(config, "vpn_manager", None) or get_vpn_manager()
    html_doc = _network.render_network(manager.status())
    return Response(200, html_doc, content_type=HTML)


def list_operations(request, params, config):
    """GET /operations — list runs + New Operation form."""
    run_ids = api.get_runs(config.runs_root)
    html_doc = _console.render_index(
        run_ids, runs_root=config.runs_root,
        sessions_root=config.sessions_root,
        vpn_status=_vpn_status(config), mode_state=_mode_state(config),
        target_state=_target_state(config))
    return Response(200, html_doc, content_type=HTML)


def _target_state(config):
    """Safe declared-target snapshot for the operations page (never fatal)."""
    try:
        store = getattr(config, "target_store", None) or get_target_store()
        profile = store.current()
        return profile.to_dict() if profile is not None else None
    except Exception:
        return None


def _vpn_status(config):
    """Safe VPN snapshot for the operations strip (never fatal)."""
    try:
        manager = getattr(config, "vpn_manager", None) or get_vpn_manager()
        return manager.status()
    except Exception:
        return None


def _mode_state(config):
    """Safe product-mode snapshot for the operations page (never fatal)."""
    try:
        manager = getattr(config, "mode_manager", None) or get_mode_manager()
        return manager.state().to_dict()
    except Exception:
        return None


def console(request, params, config):
    """GET /operations/{run_id} — live operator console."""
    html_doc = _console.render_console(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def event_stream_page(request, params, config):
    """GET /operations/{run_id}/events — chronological audit view.

    Read-only: renders the existing event projection and subscribes to
    the existing SSE endpoint. No second event store or stream.
    """
    html_doc = _events_page.render_event_stream(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


def _load_session(config, session_id):
    try:
        security.check_resource_id(session_id, "session_id")
    except (ValueError, TypeError) as exc:
        raise errors.bad_request(str(exc)) from None
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


#: Upper bound for operator-supplied `max_replans` (a UI guardrail only;
#: the Runner keeps its own bounds/semantics).
MAX_UI_REPLANS = 10


def _optional_str(body, key):
    """Return a stripped, non-empty string field, else None."""
    value = body.get(key)
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return None


def _verification_tests(body):
    """Parse a comma-separated verification test list into a tuple."""
    raw = body.get("verification_tests")
    if not isinstance(raw, str):
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _max_replans(body):
    """Parse and bound the operator-supplied max_replans (None if absent)."""
    raw = body.get("max_replans")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise errors.invalid_input("max_replans must be an integer") from None
    if value < 0 or value > MAX_UI_REPLANS:
        raise errors.invalid_input(
            f"max_replans must be between 0 and {MAX_UI_REPLANS}")
    return value


def _runner_kwargs(body):
    """Map ordinary operator inputs to existing Runner.run arguments.

    Only documented Runner arguments are exposed. Internal authority
    objects/flags (challenge_specs, regression_ok, behavior_probe_ok)
    are never settable from the UI; omitted fields keep Runner defaults.
    """
    kwargs = {}
    candidate = _optional_str(body, "candidate_target")
    if candidate:
        kwargs["candidate_target"] = candidate
    summary = _optional_str(body, "candidate_summary")
    if summary:
        kwargs["candidate_summary"] = summary
    challenger = _optional_str(body, "challenger_target")
    if challenger:
        kwargs["challenger_target"] = challenger
    forbidden = _optional_str(body, "challenger_forbidden_substring")
    if forbidden:
        kwargs["challenger_forbidden_substring"] = forbidden
    tests = _verification_tests(body)
    if tests:
        kwargs["verification_tests"] = tests
    replans = _max_replans(body)
    if replans is not None:
        kwargs["max_replans"] = replans
    return kwargs


def start_operation(request, params, config):
    """POST /operations/start — start a governed run (existing API).

    Orchestration only: delegates to `api.start_run` /
    `api.start_model_run`. It never builds its own Runner, ModelAdapter,
    or model loop.
    """
    body = request.body if isinstance(request.body, dict) else {}
    session = _load_session(config, body.get("session_id"))
    mode = body.get("mode", "runner")

    # D9.1: product mode TESTING/HTB selects the deterministic governed
    # network mission instead of the file-remediation Runner/Model path.
    mode_manager = getattr(config, "mode_manager", None) or get_mode_manager()
    state = mode_manager.state()
    if (state.mode is Mode.TESTING
            and state.testing_profile is TestingProfile.HTB):
        result = api.start_network_run(
            session, sessions_root=config.sessions_root,
            runs_root=config.runs_root,
            target_store=getattr(config, "target_store", None))
        run_id = result.run.run_id
        return Response(200, _console.redirect_page(f"/operations/{run_id}"),
                        content_type=HTML)

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
        run = api.start_run(
            session, sessions_root=config.sessions_root,
            runs_root=config.runs_root, **_runner_kwargs(body))
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
            return security.clamp_cursor(int(last))
        except ValueError:
            pass
    raw = request.query_one("after")
    if raw:
        try:
            return security.clamp_cursor(int(raw))
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
    "event_stream_page",
    "events_stream",
    "list_operations",
    "network",
    "start_operation",
]
