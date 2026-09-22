"""tests.test_d9_1_network_run — D9.1 normal-run-path integration tests.

Deterministic and offline: exercises the REAL HTTP app (`/operations/start`)
with product mode TESTING/HTB and a mission-bound TargetProfile, against a
local stdlib HTTP fixture. Proves the governed network capability now runs
through the normal operator path and produces a normal `harness.json` run.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    dispatch,
)
from raphael_ibm_bob.mode import Mode, ModeManager
from raphael_ibm_bob.target_profile import TargetStore

FLAG = "HTB{deterministic_d91_fixture_flag}"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, b"ok")
        elif path == "/flag":
            self._send(200, f"welcome {FLAG}".encode())
        elif path == "/verify":
            self._send(200, f"confirmed {FLAG}".encode())
        elif path == "/decoy":
            self._send(200, b"nothing here")
        else:
            self._send(404, b"nope")


@contextmanager
def _fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StubVPN:
    def status(self):
        return {"state": "disconnected", "history": []}

    def connect(self, *a, **k):
        return self.status()

    def disconnect(self):
        return self.status()


class _Base(unittest.TestCase):
    mission_id = "M-HTB-001"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d91_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8")
        self.sessions = self.tmp / "sessions"
        self.runs = self.tmp / "runs"
        self.mode = ModeManager()
        self.mode.set(Mode.TESTING, "htb")
        self.store = TargetStore()
        self.cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            mode_manager=self.mode, target_store=self.store,
            vpn_manager=_StubVPN())
        self.router = build_router()

    def call(self, method, path, body=None):
        return dispatch(Request(method=method, path=path, body=body),
                        self.cfg, self.router)

    def new_session(self, problem, mission_id=None, scope=""):
        mission = {
            "mission_id": mission_id or self.mission_id,
            "description": "authorized HTB network validation",
            "scope": scope, "criteria": ["obtain and verify the flag"],
            "problem": problem,
        }
        resp = self.call("POST", "/sessions", {
            "workspace_root": str(self.ws), "project_name": "htb",
            "mission": mission})
        self.assertEqual(resp.status, 201, resp.body)
        return resp.body["session_id"]

    def declare_target(self, port, mission_id=None, locator="127.0.0.1"):
        resp = self.call("POST", "/htb/target", {
            "platform": "htb", "locator": locator, "allowed_ports": [port],
            "allowed_protocols": ["http"], "scope": locator,
            "authorization_ref": "HTB-AUTHORIZED-D91",
            "mission_id": mission_id or self.mission_id})
        self.assertEqual(resp.status, 201, resp.body)

    def start(self, session_id):
        return self.call("POST", "/operations/start",
                         {"session_id": session_id})

    def run_id_from(self, html):
        match = re.search(r"/operations/([0-9T]+_[0-9a-f]+)", html)
        self.assertIsNotNone(match, html[:200])
        return match.group(1)

    def ledger(self, run_id):
        path = self.runs / run_id / "evidence.jsonl"
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


class PositiveRun(_Base):
    def test_htb_operation_start_creates_network_run(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session({
                "symptom_target": "127.0.0.1", "request_path": "/flag",
                "decoy_path": "/decoy", "probe_path": "/",
                "verification_tests": ["test_ok.py"]})
            resp = self.start(sid)
            self.assertEqual(resp.status, 200, resp.body)
            run_id = self.run_id_from(resp.body)

            # normal run record
            harness = self.runs / run_id / "harness.json"
            self.assertTrue(harness.is_file(), "harness.json missing")
            run = json.loads(harness.read_text())
            self.assertEqual(run["mission"]["mission_id"], self.mission_id)
            self.assertEqual(run["state"], "completed")
            self.assertEqual(run["gate_verdict"], "complete")

            # appears in GET /runs
            listed = self.call("GET", "/runs").body["runs"]
            self.assertIn(run_id, listed)

            records = self.ledger(run_id)
            kinds = [r.get("kind") for r in records]
            self.assertIn("request", kinds)
            self.assertIn("decision", kinds)
            self.assertIn("result", kinds)
            self.assertTrue(any(r.get("kind") == "evidence"
                                and r.get("producer") == "network"
                                for r in records))
            self.assertTrue(any(r.get("kind") == "evidence"
                                and r.get("producer") == "verifier"
                                for r in records))
            self.assertTrue(any(r.get("kind") == "evidence"
                                and r.get("producer") == "falsifier"
                                for r in records))
            self.assertTrue(any(r.get("kind") == "gate" for r in records))
            network_req = [r for r in records if r.get("kind") == "request"
                           and r.get("capability") == "network_http_request"]
            self.assertTrue(network_req)
            self.assertTrue(str(network_req[0].get("target")).endswith("/flag"))

    def test_run_visible_on_operations_page(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session({
                "symptom_target": "127.0.0.1", "request_path": "/flag",
                "decoy_path": "/decoy", "probe_path": "/",
                "verification_tests": ["test_ok.py"]})
            resp = self.start(sid)
            run_id = self.run_id_from(resp.body)
            page = self.call("GET", "/operations").body
            self.assertIn(run_id, page)


class NegativeRuns(_Base):
    def test_no_target_profile_refuses(self):
        with _fixture() as _port:
            # no POST /htb/target
            sid = self.new_session({
                "symptom_target": "127.0.0.1", "request_path": "/flag",
                "verification_tests": ["test_ok.py"]})
            resp = self.start(sid)
            run_id = self.run_id_from(resp.body)
            harness = json.loads((self.runs / run_id / "harness.json").read_text())
            self.assertEqual(harness["state"], "refused")
            self.assertEqual(harness["gate_verdict"], "refuse")

    def test_wrong_mission_target_refuses(self):
        with _fixture() as port:
            self.declare_target(port, mission_id="M-OTHER")
            sid = self.new_session({
                "symptom_target": "127.0.0.1", "request_path": "/flag",
                "verification_tests": ["test_ok.py"]})
            resp = self.start(sid)
            run_id = self.run_id_from(resp.body)
            records = self.ledger(run_id)
            self.assertFalse(any(r.get("capability") == "network_http_request"
                                 for r in records if r.get("kind") == "request"))
            harness = json.loads((self.runs / run_id / "harness.json").read_text())
            self.assertEqual(harness["state"], "refused")

    def test_http_failure_no_flag_no_complete(self):
        port = _closed_port()
        self.declare_target(port)
        sid = self.new_session({
            "symptom_target": "127.0.0.1", "request_path": "/flag",
            "verification_tests": ["test_ok.py"]})
        resp = self.start(sid)
        run_id = self.run_id_from(resp.body)
        harness = json.loads((self.runs / run_id / "harness.json").read_text())
        self.assertNotEqual(harness["state"], "completed")
        records = self.ledger(run_id)
        network_ev = [r for r in records if r.get("kind") == "evidence"
                      and r.get("producer") == "network"]
        self.assertTrue(network_ev)
        self.assertIsNone((network_ev[0].get("payload") or {}).get("flag"))
        self.assertFalse(any(r.get("producer") == "probe" for r in records))

    def test_falsification_decoy_contradiction_refuses(self):
        with _fixture() as port:
            self.declare_target(port)
            # decoy_path points at the flag path -> counter-example -> REFUTED
            sid = self.new_session({
                "symptom_target": "127.0.0.1", "request_path": "/flag",
                "decoy_path": "/flag", "verification_tests": ["test_ok.py"]})
            resp = self.start(sid)
            run_id = self.run_id_from(resp.body)
            harness = json.loads((self.runs / run_id / "harness.json").read_text())
            self.assertEqual(harness["state"], "refused")
            records = self.ledger(run_id)
            self.assertTrue(any(r.get("kind") == "evidence"
                                and r.get("producer") == "falsifier"
                                and (r.get("payload") or {}).get("kind")
                                == "counter-example"
                                for r in records))


if __name__ == "__main__":
    unittest.main()
