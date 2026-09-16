"""raphael_ibm_bob.http.app — presentation-layer HTTP/JSON server.

A small, dependency-free HTTP API over the existing Harness API.

    HTTP  ->  harness.api  ->  existing Harness  ->  Runtime -> Broker
              ->  Policy -> Execution -> Evidence -> Verification
              ->  Falsification -> Replan -> QualityGate

This layer is PRESENTATION / INTEGRATION only. It is NOT an execution
authority: it never calls `execute_capability`, never touches the
Broker/Policy/QualityGate directly, opens no outbound network path, and
fabricates no verdicts. It only serializes what `harness.api` returns.

Framework choice: the Python standard library (`http.server`) — no new
dependencies. The repository is deliberately stdlib-only; adding
FastAPI would drag in pydantic/starlette/uvicorn for no governance
benefit, and the core must stay usable without any HTTP server.
"""
from __future__ import annotations

import argparse
import hmac
import json
import sys
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness.api import DEFAULT_MAX_TURNS
from raphael_ibm_bob.http import errors
from raphael_ibm_bob.http.errors import ApiError

MAX_BODY_BYTES = 1_048_576  # 1 MiB: bound request bodies.
DEFAULT_PORT = 8787
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass
class RaphaelHTTPConfig:
    """Runtime configuration for the HTTP presentation layer.

    `api_key` is read from the environment only and is never persisted,
    logged, or returned by any endpoint.
    """
    sessions_root: Path = Path("sessions")
    runs_root: Path = Path("runs")
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    api_key: Optional[str] = None
    default_max_turns: int = DEFAULT_MAX_TURNS
    verbose: bool = False

    def is_loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS


def config_from_env(environ: Optional[Dict[str, str]] = None
                    ) -> RaphaelHTTPConfig:
    """Build config from RAPHAEL_HTTP_* / RAPHAEL_API_KEY (never logged)."""
    import os
    env = environ if environ is not None else os.environ

    def _get(name: str, default: str) -> str:
        value = env.get(name)
        return value if value not in (None, "") else default

    port_raw = _get("RAPHAEL_HTTP_PORT", str(DEFAULT_PORT))
    try:
        port = int(port_raw)
    except ValueError:
        raise ApiError(500, errors.INTERNAL_ERROR,
                       f"invalid RAPHAEL_HTTP_PORT: {port_raw!r}")
    api_key = env.get("RAPHAEL_API_KEY") or None
    return RaphaelHTTPConfig(
        sessions_root=Path(_get("RAPHAEL_HTTP_SESSIONS_ROOT", "sessions")),
        runs_root=Path(_get("RAPHAEL_HTTP_RUNS_ROOT", "runs")),
        host=_get("RAPHAEL_HTTP_HOST", "127.0.0.1"),
        port=port,
        api_key=api_key,
        default_max_turns=int(_get("RAPHAEL_HTTP_MAX_TURNS",
                                   str(DEFAULT_MAX_TURNS))),
    )


# -----------------------------------------------------------------------------
# Request / response / routing
# -----------------------------------------------------------------------------

@dataclass
class Request:
    method: str
    path: str
    query: Dict[str, List[str]] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None

    def query_one(self, name: str) -> Optional[str]:
        values = self.query.get(name)
        return values[0] if values else None


@dataclass
class Response:
    status: int
    body: Any
    content_type: str = "application/json"

    def to_json(self) -> bytes:
        return (json.dumps(self.body, sort_keys=True) + "\n").encode("utf-8")

    def to_bytes(self) -> bytes:
        """Serialise the body for the wire (JSON by default, HTML opt-in)."""
        if self.content_type.startswith("application/json"):
            return self.to_json()
        if isinstance(self.body, bytes):
            return self.body
        return str(self.body).encode("utf-8")


@dataclass
class StreamResponse:
    """A long-lived streaming response (e.g. Server-Sent Events).

    `stream` is a callable that receives a `write(bytes)` sink and
    pumps frames until done or the client disconnects. It never touches
    the harness: the route builds it from a generator over the existing
    event projection.
    """
    stream: Callable[[Callable[[bytes], None]], None]
    status: int = 200
    content_type: str = "text/event-stream; charset=utf-8"


Handler = Callable[[Request, Dict[str, str], RaphaelHTTPConfig],
                   Response]


def _unquote(value: str) -> str:
    """Minimal percent-decoder (no `urllib`, keeps the outbound-free rule)."""
    if "%" not in value:
        return value
    out: List[str] = []
    i = 0
    while i < len(value):
        char = value[i]
        if char == "%" and i + 3 <= len(value):
            hex_digits = value[i + 1:i + 3]
            try:
                out.append(chr(int(hex_digits, 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(char)
        i += 1
    return "".join(out)


def _parse_query(query_string: str) -> Dict[str, List[str]]:
    parsed: Dict[str, List[str]] = {}
    if not query_string:
        return parsed
    for pair in query_string.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        key = _unquote(key).replace("+", " ")
        value = _unquote(value).replace("+", " ")
        parsed.setdefault(key, []).append(value)
    return parsed


def _split_path(path: str) -> Tuple[str, ...]:
    return tuple(segment for segment in path.strip("/").split("/")
                 if segment != "")


class Router:
    """Literal/`{param}` path router (no wildcards, no regex)."""

    def __init__(self) -> None:
        self._routes: List[Tuple[str, Tuple[str, ...], Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self._routes.append(
            (method.upper(), _split_path(pattern), handler))

    def match(self, method: str, path: str
              ) -> Tuple[Handler, Dict[str, str]]:
        segments = _split_path(path)
        allowed: List[str] = []
        for route_method, pattern, handler in self._routes:
            params = _match_segments(pattern, segments)
            if params is None:
                continue
            if route_method == method.upper():
                return handler, params
            allowed.append(route_method)
        if allowed:
            raise ApiError(405, errors.METHOD_NOT_ALLOWED,
                           f"{method.upper()} not allowed for {path}")
        raise ApiError(404, errors.NOT_FOUND,
                       f"no route for {method.upper()} {path}")


def _match_segments(pattern: Tuple[str, ...],
                    segments: Tuple[str, ...]
                    ) -> Optional[Dict[str, str]]:
    if len(pattern) != len(segments):
        return None
    params: Dict[str, str] = {}
    for expected, actual in zip(pattern, segments):
        if expected.startswith("{") and expected.endswith("}"):
            name = expected[1:-1]
            if not actual:
                return None
            params[name] = _unquote(actual)
        elif expected != actual:
            return None
    return params


# -----------------------------------------------------------------------------
# Authentication (protects the interface; Policy still governs execution)
# -----------------------------------------------------------------------------

def _auth_required(config: RaphaelHTTPConfig, path: str) -> bool:
    if config.api_key is None:
        return False
    return _split_path(path) != ("health",)


def _authorized(request: Request, config: RaphaelHTTPConfig) -> bool:
    key = config.api_key
    if key is None:
        return True
    presented = request.headers.get("x-api-key")
    if presented is None:
        authorization = request.headers.get("authorization", "")
        prefix = "bearer "
        if authorization.lower().startswith(prefix):
            presented = authorization[len(prefix):].strip()
    if not presented:
        return False
    return hmac.compare_digest(presented, key)


# -----------------------------------------------------------------------------
# Dispatch
# -----------------------------------------------------------------------------

def dispatch(request: Request, config: RaphaelHTTPConfig,
             router: Optional[Router] = None) -> Response:
    """Route, authorize, and invoke one request; never raises.

    Always returns a `Response` (including structured error responses),
    so the transport adapter and in-process callers behave identically.
    """
    try:
        return _dispatch(request, config, router)
    except ApiError as exc:
        return error_response(exc)
    except Exception:  # never leak a stack trace to a client
        return error_response(ApiError(
            500, errors.INTERNAL_ERROR, "internal server error"))


def _dispatch(request: Request, config: RaphaelHTTPConfig,
              router: Optional[Router]):
    router = router or build_router()
    if _auth_required(config, request.path) and \
            not _authorized(request, config):
        raise ApiError(401, errors.UNAUTHORIZED,
                       "missing or invalid API key")
    handler, params = router.match(request.method, request.path)
    try:
        response = handler(request, params, config)
    except ApiError:
        raise
    except FileNotFoundError as exc:
        raise _not_found_from(exc, params) from None
    except KeyError as exc:
        raise ApiError(404, errors.NOT_FOUND, str(exc)) from None
    except (ValueError, TypeError) as exc:
        raise errors.invalid_input(str(exc)) from None
    if isinstance(response, (Response, StreamResponse)):
        return response
    if (isinstance(response, tuple) and len(response) == 2
            and isinstance(response[0], int)):
        return Response(response[0], response[1])
    return Response(200, response)


def _not_found_from(exc: FileNotFoundError,
                    params: Dict[str, str]) -> ApiError:
    message = str(exc) or "not found"
    if "session_id" in params:
        return ApiError(404, errors.SESSION_NOT_FOUND, message)
    if "run_id" in params:
        return ApiError(404, errors.RUN_NOT_FOUND, message)
    if "workspace_id" in params:
        return ApiError(404, errors.WORKSPACE_NOT_FOUND, message)
    return ApiError(404, errors.NOT_FOUND, message)


def error_response(exc: ApiError) -> Response:
    return Response(exc.status, exc.to_body())


# -----------------------------------------------------------------------------
# Route table
# -----------------------------------------------------------------------------

def build_router() -> Router:
    from raphael_ibm_bob.http.routes import (
        command,
        discovery,
        health,
        operations,
        runs,
        sessions,
        tasks,
        workspaces,
    )
    router = Router()
    router.add("GET", "/health", health.health)

    # Command Center — primary read-only operational overview.
    router.add("GET", "/command", command.command)

    router.add("GET", "/sessions", sessions.list_sessions)
    router.add("POST", "/sessions", sessions.create_session)
    router.add("GET", "/sessions/{session_id}", sessions.get_session)
    router.add("POST", "/sessions/{session_id}/missions",
               sessions.submit_mission)

    router.add("GET", "/runs", runs.list_runs)
    router.add("POST", "/runs", runs.create_run)
    router.add("POST", "/runs/model", runs.start_model_run)
    router.add("GET", "/runs/{run_id}", runs.get_run)
    router.add("POST", "/runs/{run_id}/cancel", runs.cancel_run)
    router.add("GET", "/runs/{run_id}/events", runs.get_events)
    router.add("GET", "/runs/{run_id}/evidence", runs.get_evidence)
    router.add("GET", "/runs/{run_id}/artifacts", runs.get_artifacts)
    router.add("GET", "/runs/{run_id}/gate", runs.get_gate)
    router.add("GET", "/runs/{run_id}/seal", runs.get_seal)

    router.add("GET", "/runs/{run_id}/tasks", tasks.list_tasks)
    router.add("GET", "/runs/{run_id}/tasks/{task_id}", tasks.get_task)

    router.add("GET", "/workspaces/{workspace_id}", workspaces.get_workspace)

    router.add("GET", "/roles", discovery.list_roles)
    router.add("GET", "/skills", discovery.list_skills)
    router.add("GET", "/capabilities", discovery.list_capabilities)

    # M15.3 — read-only operator screen. Renders observable, persisted
    # decision/evidence data from harness.api. Presentation only.
    router.add("GET", "/operations/{run_id}/decision-trace",
               operations.decision_trace)

    # M15.4 — live operator console + controls (orchestration only).
    router.add("GET", "/operations", operations.list_operations)
    router.add("GET", "/operations/{run_id}", operations.console)
    router.add("GET", "/operations/{run_id}/events",
               operations.event_stream_page)
    router.add("POST", "/operations/start", operations.start_operation)
    router.add("POST", "/operations/{run_id}/cancel",
               operations.cancel_operation)
    router.add("GET", "/runs/{run_id}/events/stream",
               operations.events_stream)
    return router


# -----------------------------------------------------------------------------
# HTTP transport
# -----------------------------------------------------------------------------

class HarnessRequestHandler(BaseHTTPRequestHandler):
    """Thin transport adapter: bytes <-> Request/Response. No logic."""

    server_version = "RaphaelHarnessHTTP/1.0"
    protocol_version = "HTTP/1.1"

    def _build_request(self) -> Request:
        target = self.path or "/"
        path, _, query_string = target.partition("?")
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw or "0")
        except ValueError:
            raise errors.bad_request("invalid Content-Length")
        if length < 0:
            raise errors.bad_request("invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, errors.PAYLOAD_TOO_LARGE,
                           "request body too large")
        raw = self.rfile.read(length) if length else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        body: Any = None
        if raw:
            if content_type.startswith(
                    "application/x-www-form-urlencoded"):
                parsed = _parse_query(raw.decode("utf-8", "replace"))
                body = {k: v[-1] for k, v in parsed.items()}
            else:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise errors.bad_request("malformed JSON body")
        headers = {k.lower(): v for k, v in self.headers.items()}
        return Request(
            method=self.command,
            path=path or "/",
            query=_parse_query(query_string),
            headers=headers,
            body=body,
        )

    def _handle(self) -> None:
        try:
            request = self._build_request()
            response = dispatch(request, self.server.config)
        except ApiError as exc:
            response = error_response(exc)
        except Exception:  # never leak a stack trace to a client
            response = error_response(ApiError(
                500, errors.INTERNAL_ERROR, "internal server error"))
        if isinstance(response, StreamResponse):
            self._stream(response)
            return
        self._write(response)

    do_GET = _handle
    do_POST = _handle

    def _stream(self, response: StreamResponse) -> None:
        """Pump a streaming response; stop cleanly on client disconnect."""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk: bytes) -> None:
            self.wfile.write(chunk)
            self.wfile.flush()

        try:
            response.stream(write)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _write(self, response: Response) -> None:
        payload = response.to_bytes()
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Deliberately minimal: method + path only (never headers/keys).
        if getattr(self.server, "config", None) and \
                self.server.config.verbose:
            sys.stderr.write(f"{self.command} {self.path}\n")


class HarnessHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: RaphaelHTTPConfig) -> None:
        super().__init__((config.host, config.port), HarnessRequestHandler)
        self.config = config


def create_server(config: RaphaelHTTPConfig) -> HarnessHTTPServer:
    """Bind and return the HTTP server (does not serve yet)."""
    return HarnessHTTPServer(config)


def serve(config: RaphaelHTTPConfig) -> int:
    """Run the server until interrupted (inbound presentation only)."""
    server = create_server(config)
    host, port = server.server_address[0], server.server_address[1]
    print(f"raphael-harness HTTP API listening on http://{host}:{port}")
    if not config.is_loopback() and config.api_key is None:
        print("warning: non-loopback bind without RAPHAEL_API_KEY; the "
              "interface is unauthenticated", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    config = config_from_env()
    parser = argparse.ArgumentParser(
        prog="raphael-http",
        description="RAPHAEL Harness HTTP API (presentation layer over "
                    "harness.api; not an execution authority).")
    parser.add_argument("--host", default=config.host)
    parser.add_argument("--port", type=int, default=config.port)
    parser.add_argument("--sessions-root",
                        default=str(config.sessions_root))
    parser.add_argument("--runs-root", default=str(config.runs_root))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    config.host = args.host
    config.port = args.port
    config.sessions_root = Path(args.sessions_root)
    config.runs_root = Path(args.runs_root)
    config.verbose = args.verbose or config.verbose
    return serve(config)


if __name__ == "__main__":
    sys.exit(main())
