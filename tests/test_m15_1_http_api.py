"""tests.test_m15_1_http_api — M15.1 HTTP/JSON API tests (A..Z).

Exercises the real HTTP server (loopback, ephemeral port) with a real
stdlib client against the real Harness + RAPHAEL core. No fake parallel
backend: every route runs `harness.api` over the actual governed stack.
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
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.events import EVENT_TYPES
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http.app import RaphaelHTTPConfig, create_server


def _quote_path(path: str) -> str:
    return path.replace("%", "%25").replace("/", "%2F")


class _HTTPCase(unittest.TestCase):
    """Base: temp tree + real HTTP server on 127.0.0.1:0 + client."""

    api_key = None

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m151_"))
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
        self.server = create_server(self.config)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    # --- client ---------------------------------------------------------

    def call(self, method, path, body=None, raw=None, headers=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=60)
        hdrs = dict(headers or {})
        payload = None
        if raw is not None:
            payload = raw
            hdrs.setdefault("Content-Type", "application/json")
        elif body is not None:
            payload = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
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

    # --- fixtures -------------------------------------------------------

    def mission(self, mission_id="M-http"):
        return Mission(
            mission_id=mission_id, description="http mission", scope="src/",
            criteria=["recover"],
            problem={"symptom_target": "src/cand.txt",
                     "capability": "read", "purpose": "http:probe"})

    def new_session(self, **overrides):
        body = {"workspace_root": str(self.ws), "project_name": "http",
                "mission": self.mission().to_dict()}
        body.update(overrides)
        status, data = self.call("POST", "/sessions", body=body)
        self.assertEqual(status, 201, data)
        return data["session_id"]

    def started_run(self):
        session_id = self.new_session()
        status, data = self.call("POST", "/runs",
                                 body={"session_id": session_id})
        self.assertEqual(status, 201, data)
        return session_id, data


class ApplicationLifecycle(_HTTPCase):
    def test_A_app_starts(self):
        self.assertGreater(self.port, 0)
        self.assertTrue(self.server.config.is_loopback())

    def test_B_health(self):
        status, data = self.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(data, {"status": "ok", "service": "raphael-harness"})

    def test_C_create_session(self):
        session_id = self.new_session()
        self.assertTrue(
            (self.sessions / session_id / "session.json").is_file())
        status, data = self.call("GET", "/sessions")
        self.assertEqual(status, 200)
        self.assertIn(session_id, data["sessions"])

    def test_D_retrieve_session(self):
        session_id = self.new_session()
        status, data = self.call("GET", f"/sessions/{session_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["session_id"], session_id)
        self.assertEqual(data["workspace"]["workspace_root"],
                         str(self.ws.resolve()))

    def test_E_submit_mission(self):
        session_id = self.new_session()
        body = {"mission": self.mission("M-http-2").to_dict()}
        status, data = self.call(
            "POST", f"/sessions/{session_id}/missions", body=body)
        self.assertEqual(status, 200)
        self.assertEqual(data["mission"]["mission_id"], "M-http-2")


class RunLifecycle(_HTTPCase):
    def test_F_create_and_start_run(self):
        session_id, run = self.started_run()
        self.assertEqual(run["session_id"], session_id)
        self.assertTrue(run["terminal"])
        self.assertIn(run["gate_verdict"], ("complete", "refuse"))
        status, listing = self.call("GET", "/runs")
        self.assertEqual(status, 200)
        self.assertIn(run["run_id"], listing["runs"])

    def test_G_retrieve_run(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(data["run_id"], run["run_id"])
        self.assertEqual(data["state"], run["state"])

    def test_R_cancel_pending_run(self):
        run_id = "20260101T000000_pending"
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(
            run_id=run_id, session_id="s", mission=self.mission(),
            workspace_root=str(self.ws), state="pending",
            ledger_dir=str(run_dir)))
        status, data = self.call("POST", f"/runs/{run_id}/cancel")
        self.assertEqual(status, 200)
        self.assertTrue(data["cancelled"])
        self.assertEqual(data["run"]["state"], "cancelled")

    def test_S_terminal_run_cannot_restart(self):
        _, run = self.started_run()
        status, data = self.call("POST", f"/runs/{run['run_id']}/cancel")
        self.assertEqual(status, 409)
        self.assertEqual(data["error"]["code"], "RUN_TERMINAL")
        status, after = self.call("GET", f"/runs/{run['run_id']}")
        self.assertEqual(after["state"], run["state"])


class RunInspection(_HTTPCase):
    def test_H_events(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/events")
        self.assertEqual(status, 200)
        self.assertGreater(len(data["events"]), 0)
        for event in data["events"]:
            self.assertIn(event["type"], EVENT_TYPES)

    def test_I_evidence(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/evidence")
        self.assertEqual(status, 200)
        self.assertGreater(len(data["evidence"]), 0)
        self.assertTrue(all("seq" in r and "kind" in r
                            for r in data["evidence"]))

    def test_J_artifacts(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/artifacts")
        self.assertEqual(status, 200)
        self.assertGreater(len(data["artifacts"]), 0)
        self.assertTrue(all("name" in a and "size" in a
                            for a in data["artifacts"]))

    def test_K_gate(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/gate")
        self.assertEqual(status, 200)
        self.assertIsNotNone(data["gate"])
        self.assertEqual(data["gate"]["decision"], run["gate_verdict"])

    def test_L_seal(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/seal")
        self.assertEqual(status, 200)
        # A fresh run has no sidecar seal yet: report honestly (never fake).
        self.assertFalse(data["seal"]["ok"])
        self.assertEqual(data["seal"]["reason"], "missing-seal")
        # Once the seal is written OUTSIDE the HTTP layer, it verifies.
        from raphael_ibm_bob.seal import write_seal
        write_seal(self.runs / run["run_id"])
        status, data = self.call("GET", f"/runs/{run['run_id']}/seal")
        self.assertEqual(status, 200)
        self.assertTrue(data["seal"]["ok"])
        self.assertEqual(data["seal"]["reason"], "seal-ok")

    def test_Q_tasks(self):
        _, run = self.started_run()
        status, data = self.call("GET", f"/runs/{run['run_id']}/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(data["run_id"], run["run_id"])
        self.assertGreater(len(data["tasks"]), 0)
        names = {t["name"] for t in data["tasks"]}
        self.assertIn("investigate", names)
        self.assertIn("validate", names)
        task_id = data["tasks"][-1]["task_id"]
        status, one = self.call(
            "GET", f"/runs/{run['run_id']}/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(one["task"]["task_id"], task_id)


class WorkspaceView(_HTTPCase):
    def test_M_retrieve_workspace(self):
        session_id = self.new_session()
        encoded = _quote_path(str(self.ws.resolve()))
        status, data = self.call("GET", f"/workspaces/{encoded}")
        self.assertEqual(status, 200)
        self.assertEqual(data["workspace_root"], str(self.ws.resolve()))
        self.assertTrue(data["is_directory"])
        self.assertIn(session_id, data["sessions"])
        self.assertIn("read", data["available_capabilities"])


class Discovery(_HTTPCase):
    def test_N_roles(self):
        status, data = self.call("GET", "/roles")
        self.assertEqual(status, 200)
        ids = {r["id"] for r in data["roles"]}
        self.assertIn("investigator", ids)
        self.assertIn("falsifier", ids)
        self.assertEqual(len(data["roles"]), 6)

    def test_O_skills_and_filters(self):
        status, data = self.call("GET", "/skills")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["skills"]), 5)
        status, filtered = self.call(
            "GET", "/skills?role=investigator")
        ids = {s["id"] for s in filtered["skills"]}
        self.assertEqual(ids, {"read-file", "list-dir", "search-dir"})
        status, by_cap = self.call("GET", "/skills?capability=READ")
        self.assertEqual({s["id"] for s in by_cap["skills"]},
                         {"read-file"})
        status, by_ev = self.call(
            "GET", "/skills?evidence_available=inspection")
        self.assertEqual(status, 200)
        self.assertTrue(all("inspection" in s["evidence_consumed"]
                            or not s["evidence_consumed"]
                            for s in by_ev["skills"]))

    def test_P_capabilities(self):
        status, data = self.call("GET", "/capabilities")
        self.assertEqual(status, 200)
        caps = {c["capability"] for c in data["capabilities"]}
        self.assertEqual(caps,
                         {"read", "list", "search", "write", "run_test"})
        status, by_role = self.call(
            "GET", "/capabilities?role=test_analyst")
        self.assertEqual({c["capability"] for c in by_role["capabilities"]},
                         {"run_test"})


class Errors(_HTTPCase):
    def test_T_missing_session_and_run(self):
        status, data = self.call("POST", "/runs",
                                 body={"session_id": "nope"})
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "SESSION_NOT_FOUND")
        status, data = self.call("GET", "/runs/nope")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "RUN_NOT_FOUND")
        status, data = self.call("GET", "/runs/nope/evidence")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "RUN_NOT_FOUND")

    def test_U_malformed_and_semantic_errors(self):
        status, data = self.call("POST", "/sessions", raw=b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "BAD_REQUEST")
        status, data = self.call(
            "POST", "/sessions", body={"mission": {"bogus": 1}})
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "INVALID_INPUT")
        status, data = self.call("GET", "/skills?role=ghost")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "ROLE_NOT_FOUND")
        status, data = self.call("GET", "/skills?capability=bogus")
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "INVALID_INPUT")
        status, data = self.call("GET", "/no-such-route")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "NOT_FOUND")

    def test_model_run_endpoint_reports_unconfigured_honestly(self):
        # No RAPHAEL_MODEL_* configured in tests: honest 503 (never faked).
        import os
        from unittest import mock
        session_id = self.new_session()
        with mock.patch.dict(os.environ, {
                "RAPHAEL_MODEL_ENDPOINT": "",
                "RAPHAEL_MODEL_NAME": "",
                "RAPHAEL_MODEL_API_KEY": ""}):
            status, data = self.call(
                "POST", "/runs/model", body={"session_id": session_id})
        self.assertEqual(status, 503)
        self.assertEqual(data["error"]["code"], "MODEL_NOT_CONFIGURED")


class AuthBoundary(_HTTPCase):
    api_key = "sk-test-secret-do-not-leak"

    def test_V_secret_non_leakage_and_enforcement(self):
        # Unauthenticated read is rejected; /health stays open.
        status, data = self.call("GET", "/sessions")
        self.assertEqual(status, 401)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")
        status, _ = self.call("GET", "/health")
        self.assertEqual(status, 200)
        # Wrong key rejected, right key accepted.
        status, _ = self.call("GET", "/sessions",
                              headers={"X-API-Key": "wrong"})
        self.assertEqual(status, 401)
        status, data = self.call(
            "GET", "/sessions", headers={"X-API-Key": self.api_key})
        self.assertEqual(status, 200)
        # The key never appears in a response body.
        self.assertNotIn(self.api_key, json.dumps(data))
        session_id = self.new_session_authorized()
        status, body = self.call(
            "GET", f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {self.api_key}"})
        self.assertEqual(status, 200)
        self.assertNotIn(self.api_key, json.dumps(body))
        self.assertNotIn("authorization", json.dumps(body).lower())
        blob = (self.sessions / session_id / "session.json").read_text(
            encoding="utf-8")
        self.assertNotIn(self.api_key, blob)

    def new_session_authorized(self):
        body = {"workspace_root": str(self.ws),
                "mission": self.mission().to_dict()}
        status, data = self.call("POST", "/sessions", body=body,
                                 headers={"X-API-Key": self.api_key})
        self.assertEqual(status, 201, data)
        return data["session_id"]


class GovernanceStatic(unittest.TestCase):
    """W/X/Y/Z: static boundary checks over the HTTP package source."""

    @classmethod
    def setUpClass(cls):
        import raphael_ibm_bob.http as http_pkg
        cls.pkg = Path(http_pkg.__file__).parent
        cls.sources = {
            path: path.read_text(encoding="utf-8")
            for path in sorted(cls.pkg.rglob("*.py"))
            if "__pycache__" not in path.parts
        }
        from raphael_ibm_bob.http import routes
        cls.route_sources = {
            path: path.read_text(encoding="utf-8")
            for path in sorted(
                Path(routes.__file__).parent.rglob("*.py"))
            if "__pycache__" not in path.parts
        }

    def test_W_routes_use_harness_api_not_direct_core(self):
        from raphael_ibm_bob.http import routes
        routes_dir = Path(routes.__file__).parent
        for name in ("sessions.py", "runs.py", "workspaces.py",
                     "discovery.py", "tasks.py"):
            src = (routes_dir / name).read_text(encoding="utf-8")
            self.assertIn("harness import api", src, name)
        for forbidden in (
                "from raphael_ibm_bob.broker", "from raphael_ibm_bob.policy",
                "from raphael_ibm_bob.runtime",
                "from raphael_ibm_bob.capabilities",
                "from raphael_ibm_bob.quality_gate",
                "from raphael_ibm_bob.runner",
                "from raphael_ibm_bob.evidence_ledger",
                "from raphael_ibm_bob.verifier",
                "from raphael_ibm_bob.falsifier",
                "from raphael_ibm_bob.replanner"):
            for path, src in self.sources.items():
                self.assertNotIn(forbidden, src,
                                 f"{forbidden} in {path}")

    def test_X_no_route_invokes_execute_capability(self):
        for path, src in self.sources.items():
            self.assertNotIn("execute_capability(", src, str(path))

    def test_Y_no_new_subprocess(self):
        for path, src in self.sources.items():
            self.assertNotIn("import subprocess", src, str(path))
            self.assertNotIn("Popen", src, str(path))

    def test_Z_no_unauthorized_network_path(self):
        for path, src in self.sources.items():
            for token in ("import urllib", "from urllib",
                          "import http.client", "from http.client",
                          "import requests", "import socket",
                          "urlopen"):
                self.assertNotIn(token, src, f"{token} in {path}")


if __name__ == "__main__":
    unittest.main()
