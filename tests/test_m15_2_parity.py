"""tests.test_m15_2_parity — direct vs HTTP model-run parity (A..L).

Proves `POST /runs/model` is the SAME governed operation as
`harness.api.start_model_run()` with equivalent inputs/configuration.

Uses a local OpenAI-compatible STUB (a real HTTP server) so the real
provider adapter, the real model loop, and the real RAPHAEL core run
deterministically. The RAPHAEL core is never mocked away - only the
external model endpoint is stubbed.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.providers.openai_compat import (
    OpenAICompatAdapter,
)
from raphael_ibm_bob.http.app import RaphaelHTTPConfig, create_server

FAKE_KEY = "sk-parity-secret-must-not-leak"
READ_THEN_DONE = [
    (200, {"intent": "act", "skill": "read-file",
           "target": "src/cand.txt", "purpose": "inspect"}),
    (200, {"intent": "done"}),
]


class _StubProvider:
    """Configurable OpenAI-compatible stub; records bodies + headers."""

    def __init__(self, testcase, script=None):
        self.script = list(script or [])
        self.calls = 0
        self.bodies = []
        self.headers = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    stub.bodies.append(json.loads(raw.decode("utf-8")))
                except ValueError:
                    stub.bodies.append({})
                stub.headers.append(dict(self.headers))
                index = stub.calls
                stub.calls += 1
                if index < len(stub.script):
                    status, content = stub.script[index]
                else:
                    status, content = 200, {"intent": "done"}
                if status != 200:
                    blob = b'{"error": "stub"}'
                else:
                    text = (content if isinstance(content, str)
                            else json.dumps(content))
                    blob = json.dumps(
                        {"choices": [{"message": {"content": text}}]}
                    ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        testcase.addCleanup(self.server.server_close)
        testcase.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def reset(self, script=None):
        self.calls = 0
        self.bodies = []
        self.headers = []
        if script is not None:
            self.script = list(script)


class _ParityCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m152_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self._last_run_id = None
        self.config = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="127.0.0.1", port=0)
        self.server = create_server(self.config)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        self.stub = _StubProvider(self)

    # --- helpers --------------------------------------------------------

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        payload = (json.dumps(body).encode("utf-8")
                   if body is not None else None)
        headers = {"Content-Type": "application/json"} if payload else {}
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, (json.loads(data) if data else None)

    def mission(self, mission_id="M-parity"):
        return Mission(mission_id=mission_id, description="parity mission",
                       scope="src/", criteria=["recover"],
                       problem={"symptom_target": "src/cand.txt"})

    def env(self, extra=None):
        values = {
            "RAPHAEL_MODEL_ENDPOINT": self.stub.url,
            "RAPHAEL_MODEL_NAME": "stub-parity",
            "RAPHAEL_MODEL_API_KEY": FAKE_KEY,
            "RAPHAEL_MODEL_TIMEOUT": "9",
            "RAPHAEL_MODEL_MAX_TOKENS": "321",
            "RAPHAEL_MODEL_TEMPERATURE": "0",
        }
        values.update(extra or {})
        return mock.patch.dict(os.environ, values)

    def new_session(self, mission=None):
        status, data = self.call("POST", "/sessions", {
            "workspace_root": str(self.ws),
            "mission": (mission or self.mission()).to_dict()})
        self.assertEqual(status, 201, data)
        return data["session_id"]

    def http_run(self, session_id, **body):
        payload = {"session_id": session_id}
        payload.update(body)
        status, data = self.call("POST", "/runs/model", payload)
        if status == 201:
            self._last_run_id = data["run"]["run_id"]
        return status, data

    def direct_run(self, session_id, mission=None, max_turns=5):
        session = api.get_session(session_id, self.sessions)
        return api.start_model_run(
            session, mission=mission or self.mission(),
            model=api.make_model_adapter("openai-compatible"),
            max_turns=max_turns, sessions_root=self.sessions,
            runs_root=self.runs)


class ParityTests(_ParityCase):
    def test_A_http_uses_start_model_run_entry_point(self):
        with self.env():
            sid = self.new_session()
            real = api.start_model_run
            captured = {}

            def spy(session, mission=None, *, model, probe=None,
                    max_turns=api.DEFAULT_MAX_TURNS, sessions_root=None,
                    runs_root=api.DEFAULT_RUNS_ROOT):
                captured.update(session=session, mission=mission, model=model,
                                probe=probe, max_turns=max_turns,
                                sessions_root=sessions_root,
                                runs_root=runs_root)
                return real(session, mission=mission, model=model, probe=probe,
                            max_turns=max_turns, sessions_root=sessions_root,
                            runs_root=runs_root)

            self.stub.reset(READ_THEN_DONE)
            with mock.patch.object(api, "start_model_run", new=spy):
                status, data = self.http_run(sid, max_turns=5)
            self.assertEqual(status, 201, data)
            self.assertEqual(captured["session"].session_id, sid)
            self.assertIsNone(captured["probe"])
            self.assertEqual(captured["max_turns"], 5)
            self.assertIsInstance(captured["model"], OpenAICompatAdapter)

    def test_A2_omitted_max_turns_uses_shared_default(self):
        with self.env():
            sid = self.new_session()
            real = api.start_model_run
            captured = {}

            def spy(session, mission=None, *, model, probe=None,
                    max_turns=api.DEFAULT_MAX_TURNS, sessions_root=None,
                    runs_root=api.DEFAULT_RUNS_ROOT):
                captured["max_turns"] = max_turns
                return real(session, mission=mission, model=model, probe=probe,
                            max_turns=max_turns, sessions_root=sessions_root,
                            runs_root=runs_root)

            self.stub.reset([(200, {"intent": "done"})])
            with mock.patch.object(api, "start_model_run", new=spy):
                self.http_run(sid)
            self.assertEqual(captured["max_turns"], api.DEFAULT_MAX_TURNS)
            self.assertEqual(api.DEFAULT_MAX_TURNS,
                             RaphaelHTTPConfig().default_max_turns)

    def test_B_provider_config_reaches_both_paths(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, {"intent": "done"})])
            status, _ = self.http_run(sid, max_turns=3)
            self.assertEqual(status, 201)
            http_body = self.stub.bodies[0]
            self.stub.reset([(200, {"intent": "done"})])
            self.direct_run(sid, max_turns=3)
            direct_body = self.stub.bodies[0]
            for body in (http_body, direct_body):
                self.assertEqual(body["model"], "stub-parity")
                self.assertEqual(body["max_tokens"], 321)
                self.assertEqual(body["temperature"], 0.0)
                self.assertEqual(body["response_format"],
                                 {"type": "json_object"})
            self.assertEqual(http_body, direct_body)

    def test_C_mission_reaches_model_context(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, {"intent": "done"})])
            self.http_run(sid, max_turns=2)
            summary = json.loads(
                self.stub.bodies[0]["messages"][1]["content"])
            self.assertEqual(summary["mission"]["mission_id"], "M-parity")
            self.assertEqual(summary["mission"]["scope"], "src/")

    def test_D_session_and_workspace_preserved(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, {"intent": "done"})])
            self.http_run(sid, max_turns=2)
            payload = json.loads(
                self.stub.bodies[0]["messages"][1]["content"])
            summary = payload["mission"]
            self.assertEqual(summary["session_id"], sid)
            self.assertEqual(summary["workspace_root"], str(self.ws))
            run = api.get_run(self._last_run_id, self.runs)
            self.assertEqual(run.session_id, sid)
            self.assertEqual(run.workspace_root, str(self.ws))

    def test_E_roles_skills_and_task_context_preserved(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, {"intent": "done"})])
            self.http_run(sid, max_turns=2)
            payload = json.loads(
                self.stub.bodies[0]["messages"][1]["content"])
            summary = payload["mission"]
            self.assertEqual(len(summary["available_roles"]), 6)
            self.assertIsNotNone(summary["active_task"])
            self.assertIn("steps", summary["active_task"])
            self.assertEqual(
                {s["skill"] for s in payload["available_skills"]},
                {"read-file", "list-dir", "search-dir", "write-file",
                 "run-test", "network-http-request",
                 "network-telnet-session"})
            self.assertTrue(all("role" in s
                                for s in payload["available_skills"]))

    def test_F_provider_request_bodies_identical(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset(READ_THEN_DONE)
            self.http_run(sid, max_turns=5)
            http_bodies = list(self.stub.bodies)
            self.stub.reset(READ_THEN_DONE)
            self.direct_run(sid, max_turns=5)
            direct_bodies = list(self.stub.bodies)
            self.assertEqual(direct_bodies, http_bodies)
            self.assertGreaterEqual(len(http_bodies), 2)

    def test_G_max_turns_forwarded(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([
                (200, {"intent": "act", "skill": "read-file",
                       "target": "src/cand.txt", "purpose": "inspect"})])
            status, data = self.http_run(sid, max_turns=1)
            self.assertEqual(status, 201)
            self.assertEqual(data["terminal"], "max-turns")
            self.assertEqual(data["turns"], 1)
            self.assertIn("max_turns=1", data["terminal_reason"])

    def test_H_provider_http_error_surfaced_consistently(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(500, None)])
            status, data = self.http_run(sid, max_turns=3)
            self.assertEqual(status, 201)
            self.assertEqual(data["terminal"], "model-error")
            self.assertIn("ProviderError", data["terminal_reason"])
            self.stub.reset([(500, None)])
            direct = self.direct_run(sid, max_turns=3)
            self.assertEqual(direct.terminal, "model-error")
            self.assertIn("ProviderError", direct.terminal_reason)

    def test_H2_structured_error_surfaced_consistently(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, "this is not json")])
            status, data = self.http_run(sid, max_turns=3)
            self.assertEqual(status, 201)
            self.assertEqual(data["terminal"], "model-error")
            self.assertIn("StructuredProposalError", data["terminal_reason"])
            self.stub.reset([(200, "this is not json")])
            direct = self.direct_run(sid, max_turns=3)
            self.assertEqual(direct.terminal, "model-error")
            self.assertIn("StructuredProposalError", direct.terminal_reason)

    def test_I_terminal_states_consistent(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset(READ_THEN_DONE)
            status, data = self.http_run(sid, max_turns=5)
            self.assertEqual(data["terminal"], "done")
            self.assertEqual(data["terminal_reason"], "model declared done")
            self.stub.reset(READ_THEN_DONE)
            direct = self.direct_run(sid, max_turns=5)
            self.assertEqual(direct.terminal, data["terminal"])
            self.assertEqual(direct.terminal_reason, data["terminal_reason"])
            self.assertEqual(direct.run.state, data["run"]["state"])
            self.assertEqual(direct.gate_verdict, data["gate_verdict"])

    def test_K_runs_are_governed_not_bypassed(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset(READ_THEN_DONE)
            status, data = self.http_run(sid, max_turns=5)
            records = api.get_evidence(data["run"]["run_id"], self.runs)
            kinds = [r.get("kind") for r in records]
            self.assertIn("request", kinds)
            self.assertIn("decision", kinds)
            self.assertIn("result", kinds)

    def test_L_no_secret_leakage(self):
        with self.env():
            sid = self.new_session()
            self.stub.reset([(200, {"intent": "done"})])
            status, data = self.http_run(sid, max_turns=2)
            auth = [h.get("Authorization") for h in self.stub.headers]
            self.assertIn(f"Bearer {FAKE_KEY}", auth)
            self.assertNotIn(FAKE_KEY, json.dumps(data))
            for root in (self.runs, self.sessions):
                for path in root.rglob("*"):
                    if path.is_file():
                        self.assertNotIn(
                            FAKE_KEY, path.read_text(
                                encoding="utf-8", errors="replace"))


class GovernanceParity(unittest.TestCase):
    """J/K static: the HTTP layer has no second loop and no bypass."""

    @classmethod
    def setUpClass(cls):
        import raphael_ibm_bob.http as http_pkg
        cls.pkg = Path(http_pkg.__file__).parent
        cls.sources = {
            p: p.read_text(encoding="utf-8")
            for p in cls.pkg.rglob("*.py")
            if "__pycache__" not in p.parts}

    def test_J_no_second_model_loop(self):
        for path, src in self.sources.items():
            for token in ("run_model_mission(", "drive_turns(",
                          "def propose(", "while True"):
                self.assertNotIn(token, src, f"{token} in {path}")

    def test_K_no_broker_or_policy_bypass(self):
        for path, src in self.sources.items():
            for token in ("BOBBroker", "BOBPolicy", "BOBRuntime",
                          "BOBQualityGate", "execute_capability(",
                          "GateVerdict", "write_seal"):
                self.assertNotIn(token, src, f"{token} in {path}")


if __name__ == "__main__":
    unittest.main()
