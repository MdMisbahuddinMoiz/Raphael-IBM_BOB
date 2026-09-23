"""tests.test_d12_1_http_hardening — D12.1 HTTP boundary hardening (G7/H-4/H-5/M-12/M-14).

Proves, against the real HTTP server (loopback, ephemeral port) and
real in-process dispatch — no real network beyond localhost:

* G7:  non-loopback bind without an API key refuses to start (and
  refuses unauth routes in-process); loopback keeps working keyless.
* H-4: foreign `Host` rejected; loopback Host allowed.
* H-5: foreign/`null`/empty Origin rejected on state-changing routes;
  foreign Referer rejected; valid same-origin allowed (JSON API and the
  plain HTML form flow); headerless non-browser clients unaffected;
  foreign Origin on safe GETs is ignored.
* M-12: `..%2F..%2Fetc` and backslash/dot/absolute/nested/
  double-encoded/NUL/oversize variants rejected at the HTTP boundary
  for session/run/workspace IDs (path params and JSON/form bodies);
  valid-but-absent IDs still 404 (not 400).
* M-14: SSE lifetime/replay/buffer bounds hold without removing
  streaming (terminal runs still stream every event then close).
* Errors: response bodies never contain the sessions_root/runs_root
  absolute paths.
"""
from __future__ import annotations

import http.client
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http import security
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    create_server,
    dispatch,
)
from raphael_ibm_bob.http.views import event_stream as es


def _quote_segment(raw: str) -> str:
    return (raw.replace("%", "%25").replace("/", "%2F")
            .replace("\\", "%5C").replace(" ", "%20"))


class _LiveCase(unittest.TestCase):
    """Temp tree + real HTTP server on 127.0.0.1:0 + raw client."""

    api_key = None

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d121_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.config = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="127.0.0.1", port=0, api_key=self.api_key,
            default_max_turns=3)
        self.router = build_router()
        self.server = create_server(self.config)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        self.host_header = f"127.0.0.1:{self.port}"

    # --- client ---------------------------------------------------------

    def call(self, method, path, body=None, raw=None, headers=None,
             form=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=60)
        hdrs = dict(headers or {})
        payload = None
        if form is not None:
            payload = "&".join(f"{k}={v}" for k, v in form.items())
            hdrs.setdefault("Content-Type",
                            "application/x-www-form-urlencoded")
        elif raw is not None:
            payload = raw
            hdrs.setdefault("Content-Type", "application/json")
        elif body is not None:
            payload = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        parsed = None
        if data:
            try:
                parsed = json.loads(data)
            except ValueError:
                parsed = {"_raw": data.decode("utf-8", "replace")}
        return resp.status, parsed

    def same_origin(self, extra=None):
        hdrs = {"Origin": f"http://{self.host_header}"}
        hdrs.update(extra or {})
        return hdrs

    # --- fixtures -------------------------------------------------------

    def mission(self, mission_id="M-harden"):
        return Mission(
            mission_id=mission_id, description="hardening mission",
            scope="src/", criteria=["recover"],
            problem={"symptom_target": "src/cand.txt",
                     "capability": "read", "purpose": "probe"})

    def new_session(self, **overrides):
        body = {"workspace_root": str(self.ws), "project_name": "h",
                "mission": self.mission().to_dict()}
        body.update(overrides)
        status, data = self.call("POST", "/sessions", body=body)
        self.assertEqual(status, 201, data)
        return data["session_id"]


class BindBoundary(_LiveCase):
    def test_loopback_without_key_serves(self):
        status, data = self.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(self.server.config.is_loopback())

    def test_non_loopback_without_key_refuses_to_bind(self):
        cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="0.0.0.0", port=0, api_key=None)
        with self.assertRaises(RuntimeError):
            create_server(cfg)
        with self.assertRaises(RuntimeError):
            security.ensure_bind_allowed(cfg)

    def test_non_loopback_with_key_binds(self):
        cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="0.0.0.0", port=0, api_key="sk-bind-test")
        server = create_server(cfg)
        try:
            self.assertIsNotNone(server.server_address[1])
        finally:
            server.server_close()

    def test_non_loopback_without_key_refuses_routes_in_process(self):
        cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="0.0.0.0", port=0, api_key=None)
        router = build_router()
        denied = dispatch(Request(method="GET", path="/sessions"),
                          cfg, router)
        self.assertEqual(denied.status, 401)
        # Liveness stays open.
        alive = dispatch(Request(method="GET", path="/health"), cfg, router)
        self.assertEqual(alive.status, 200)


class HostBoundary(_LiveCase):
    def test_foreign_host_rejected(self):
        status, data = self.call("GET", "/health",
                                 headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "FORBIDDEN_HOST")

    def test_foreign_host_with_port_rejected(self):
        status, data = self.call("GET", "/sessions",
                                 headers={"Host": "evil.example:8787"})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "FORBIDDEN_HOST")

    def test_loopback_host_allowed(self):
        status, _ = self.call("GET", "/health",
                              headers={"Host": self.host_header})
        self.assertEqual(status, 200)

    def test_host_check_in_process(self):
        denied = dispatch(
            Request(method="GET", path="/health",
                    headers={"host": "evil.example"}),
            self.config, self.router)
        self.assertEqual(denied.status, 403)
        # No Host header (in-process callers) passes through.
        ok = dispatch(Request(method="GET", path="/health"),
                      self.config, self.router)
        self.assertEqual(ok.status, 200)


class OriginCsrfBoundary(_LiveCase):
    def test_foreign_origin_rejected_on_browser_post(self):
        status, data = self.call(
            "POST", "/operations/start",
            form={"session_id": "nope", "mode": "runner"},
            headers={"Host": self.host_header,
                     "Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "INVALID_ORIGIN")

    def test_foreign_origin_rejected_on_json_post(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws)},
            headers={"Host": self.host_header,
                     "Origin": "http://evil.example:9999"})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "INVALID_ORIGIN")

    def test_null_origin_rejected(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws)},
            headers={"Host": self.host_header, "Origin": "null"})
        self.assertEqual(status, 403)

    def test_empty_origin_rejected(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws)},
            headers={"Host": self.host_header, "Origin": ""})
        self.assertEqual(status, 403)

    def test_foreign_referer_rejected_without_origin(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws)},
            headers={"Host": self.host_header,
                     "Referer": "http://evil.example/steal"})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"]["code"], "CSRF_REJECTED")

    def test_origin_host_mismatch_rejected(self):
        status, _ = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws)},
            headers={"Host": self.host_header,
                     "Origin": "http://localhost:9999"})
        self.assertEqual(status, 403)

    def test_valid_same_origin_json_allowed(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws),
                  "mission": self.mission().to_dict()},
            headers=self.same_origin())
        self.assertEqual(status, 201, data)
        self.assertIn("session_id", data)

    def test_valid_same_origin_form_post_allowed(self):
        session_id = self.new_session()
        status, _ = self.call(
            "POST", "/operations/start",
            form={"session_id": session_id, "mode": "runner",
                  "candidate_target": "src/cand.txt"},
            headers={"Host": self.host_header,
                     "Origin": f"http://{self.host_header}",
                     "Referer": f"http://{self.host_header}/operations"})
        self.assertEqual(status, 200)

    def test_headerless_non_browser_post_allowed(self):
        status, data = self.call(
            "POST", "/sessions",
            body={"workspace_root": str(self.ws),
                  "mission": self.mission().to_dict()})
        self.assertEqual(status, 201, data)

    def test_safe_get_ignores_foreign_origin(self):
        status, _ = self.call("GET", "/health",
                              headers={"Host": self.host_header,
                                       "Origin": "http://evil.example"})
        self.assertEqual(status, 200)


class ResourceIdBoundary(_LiveCase):
    VARIANTS = [
        "..%2F..%2Fetc",
        "..%2f..%2fetc%2fpasswd",
        "..%5C..%5Cetc",
        "..%5c..%5cwindows",
        "%2e%2e%2fetc",
        "%2Fetc%2Fpasswd",
        "a%2F..%2Fb",
        "%252e%252e%252fetc",
        "a%00b",
        "..",
        ".",
        "../etc",
        "a/b",
        "a\\b",
        "a%b",
        "x" * 200,
    ]

    def test_session_traversal_variants_rejected(self):
        for variant in self.VARIANTS:
            with self.subTest(variant=variant):
                status, data = self.call(
                    "GET", f"/sessions/{_quote_segment(variant)}")
                self.assertIn(status, (400, 404), variant)
                if status == 400:
                    self.assertIn("error", data)

    def test_run_traversal_variants_rejected(self):
        for variant in self.VARIANTS:
            with self.subTest(variant=variant):
                status, data = self.call(
                    "GET", f"/runs/{_quote_segment(variant)}")
                self.assertIn(status, (400, 404), variant)
                if status == 400:
                    self.assertIn("error", data)

    def test_encoded_dotdot_slash_is_400_not_filesystem(self):
        status, data = self.call("GET", "/sessions/..%2F..%2Fetc")
        self.assertEqual(status, 400, data)
        status, data = self.call("GET", "/runs/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(status, 400, data)

    def test_raw_encoded_variants_rejected(self):
        raws = ("..%2F..%2Fetc", "..%5C..%5Cetc", "%2e%2e%2fetc",
                "%252e%252e%252fetc", "a%00b", "%2Fetc%2Fpasswd",
                "%c0%afetc")
        for raw in raws:
            for prefix in ("sessions", "runs"):
                with self.subTest(prefix=prefix, raw=raw):
                    status, _ = self.call("GET", f"/{prefix}/{raw}")
                    self.assertEqual(status, 400, (prefix, raw))

    def test_oversize_and_invalid_ids_rejected(self):
        for bad in ("x" * 200, "has space!", "semi;colon",
                    "quote\"q", "tick`", "dollar$"):
            with self.subTest(bad=bad):
                status, _ = self.call(
                    "GET", f"/runs/{_quote_segment(bad)}")
                self.assertIn(status, (400, 404), bad)
        status, _ = self.call("GET", "/runs/" + "y" * 200)
        self.assertEqual(status, 400)

    def test_valid_but_absent_ids_still_404(self):
        status, data = self.call("GET", "/runs/nope")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "RUN_NOT_FOUND")
        status, data = self.call("GET", "/sessions/nope")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "SESSION_NOT_FOUND")

    def test_body_session_id_traversal_rejected(self):
        status, data = self.call(
            "POST", "/runs", body={"session_id": "../../etc"})
        self.assertEqual(status, 400, data)
        status, data = self.call(
            "POST", "/sessions",
            body={"session_id": "..%2Fetc",
                  "workspace_root": str(self.ws)})
        self.assertEqual(status, 400, data)
        status, data = self.call(
            "POST", "/operations/start",
            form={"session_id": "..\\..\\etc"})
        self.assertEqual(status, 400, data)

    def test_workspace_traversal_rejected(self):
        status, data = self.call("GET", "/workspaces/..%2F..%2Fetc")
        self.assertEqual(status, 400, data)
        status, data = self.call(
            "GET", "/workspaces/" + _quote_segment("a/../b"))
        self.assertIn(status, (400, 404))

    def test_task_id_traversal_rejected(self):
        run_id = "20260101T000000_probe"
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(
            run_id=run_id, session_id="s", mission=self.mission(),
            workspace_root=str(self.ws), state="pending",
            ledger_dir=str(run_dir)))
        status, _ = self.call(
            "GET", f"/runs/{run_id}/tasks/..%2F..%2Fetc")
        self.assertEqual(status, 400)

    def test_containment_helper(self):
        resolved = security.contained_path(self.sessions, "abc123")
        self.assertTrue(str(resolved).startswith(str(self.sessions)))
        with self.assertRaises(ValueError):
            security.contained_path(self.sessions, "../escape")


class ErrorScrubbing(_LiveCase):
    def test_run_404_hides_runs_root(self):
        status, data = self.call("GET", "/runs/nope")
        self.assertEqual(status, 404)
        blob = json.dumps(data)
        self.assertNotIn(str(self.runs), blob)
        self.assertNotIn(str(self.runs.resolve()), blob)

    def test_session_404_hides_sessions_root(self):
        status, data = self.call("GET", "/sessions/nope")
        self.assertEqual(status, 404)
        blob = json.dumps(data)
        self.assertNotIn(str(self.sessions), blob)
        self.assertNotIn(str(self.sessions.resolve()), blob)

    def test_evidence_404_hides_runs_root(self):
        status, data = self.call("GET", "/runs/nope/evidence")
        self.assertEqual(status, 404)
        blob = json.dumps(data)
        self.assertNotIn(str(self.runs.resolve()), blob)

    def test_scrub_helper_replaces_roots(self):
        message = (f"run directory not found: "
                   f"{self.runs.resolve()}/nope")
        scrubbed = security.scrub_paths(message, self.config)
        self.assertNotIn(str(self.runs.resolve()), scrubbed)
        self.assertIn("<runs-root>", scrubbed)


class SseBounds(_LiveCase):
    def test_bounds_constants_exist(self):
        self.assertLessEqual(es.ABSOLUTE_MAX_SECONDS, 300.0)
        self.assertGreaterEqual(es.MAX_REPLAY_EVENTS, 1)
        self.assertGreaterEqual(es.MAX_FRAMES_PER_POLL, 1)
        self.assertLessEqual(es.DEFAULT_MAX_SECONDS,
                             es.ABSOLUTE_MAX_SECONDS)

    def test_lifetime_cap_enforced(self):
        run_id = "20260101T000000_pending"
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(
            run_id=run_id, session_id="s", mission=self.mission(),
            workspace_root=str(self.ws), state="pending",
            ledger_dir=str(run_dir)))
        clock = {"t": 0.0}

        def _clock():
            clock["t"] += 60.0
            return clock["t"]

        frames = list(es.iter_frames(
            run_id, runs_root=self.runs, poll_seconds=0.0,
            max_seconds=10 ** 9, heartbeat_seconds=60.0,
            clock=_clock, sleep=lambda _s: None))
        self.assertTrue(frames)
        # Capped at ABSOLUTE_MAX_SECONDS (5 x 60s ticks), then closed.
        self.assertLessEqual(clock["t"], 600.0)
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))

    def test_huge_cursor_terminates_without_replay_flood(self):
        session_id = self.new_session()
        status, data = self.call("POST", "/runs",
                                 body={"session_id": session_id})
        self.assertEqual(status, 201, data)
        run_id = data["run_id"]
        frames = list(es.iter_frames(run_id, runs_root=self.runs,
                                     after=10 ** 12, poll_seconds=0.0,
                                     max_seconds=5.0,
                                     sleep=lambda _s: None))
        replayed = [f for f in frames
                    if f.startswith(b"event: RAPHAEL_EVENT")]
        self.assertEqual(replayed, [])
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))

    def test_terminal_run_still_streams_then_closes(self):
        session_id = self.new_session()
        status, data = self.call("POST", "/runs",
                                 body={"session_id": session_id})
        run_id = data["run_id"]
        frames = list(es.iter_frames(run_id, runs_root=self.runs))
        emitted = [f for f in frames
                   if f.startswith(b"event: RAPHAEL_EVENT")]
        self.assertGreater(len(emitted), 0)
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))

    def test_cursor_clamp(self):
        self.assertEqual(security.clamp_cursor("-5"), 0)
        self.assertEqual(security.clamp_cursor("abc"), 0)
        self.assertEqual(security.clamp_cursor(None), 0)
        self.assertEqual(security.clamp_cursor(7), 7)
        self.assertEqual(security.clamp_cursor(10 ** 12),
                         security.MAX_CURSOR)


class AuthStillEnforced(unittest.TestCase):
    def test_api_key_flow_unaffected(self):
        base = Path(tempfile.mkdtemp(prefix="d121k_"))
        self.addCleanup(shutil.rmtree, base, True)
        cfg = RaphaelHTTPConfig(
            sessions_root=base / "sessions", runs_root=base / "runs",
            host="127.0.0.1", port=0, api_key="sk-harden")
        server = create_server(cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def get(headers):
            conn = http.client.HTTPConnection(
                "127.0.0.1", port, timeout=30)
            conn.request("GET", "/sessions", headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            return resp.status, body

        status, _ = get(None)
        self.assertEqual(status, 401)
        status, _ = get({"X-API-Key": "sk-harden"})
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
