"""tests.test_m15_6_command_center — Command Center tests.

The Command Center is a read-only overview aggregated through
`harness.api`. These tests use the real governed stack for completed
runs and a real persisted Harness record for an active run.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers import DoneSignal
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    create_server,
    dispatch,
)
from raphael_ibm_bob.http.views import command_center as cc

PASSING_TEST = (
    "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_ok(self):\n        self.assertTrue(True)\n"
)


class _Scripted:
    def __init__(self, requests):
        self._queue = list(requests)

    def propose(self, context):
        if not self._queue:
            raise DoneSignal("done")
        return self._queue.pop(0)


class _CommandCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m156_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(PASSING_TEST,
                                                     encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs,
                                     host="127.0.0.1", port=0)
        self.server = create_server(self.cfg)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        self.addCleanup(self.server.shutdown)

    def mission(self, mid="M-cc"):
        return Mission(mission_id=mid, description="Command Center mission",
                       scope="src/", criteria=["reproduced", "verified"],
                       problem={"symptom_target": "src/cand.txt"})

    def _req(self, requester, capability, target, purpose):
        return ActionRequest(sequence=0, requester=requester,
                             capability=capability, target=target,
                             purpose=purpose)

    def _session(self):
        return api.create_session(mission=self.mission(),
                                  workspace_root=self.ws,
                                  sessions_root=self.sessions,
                                  model="stub-model", provider="stub-provider")

    def complete_run(self):
        session = self._session()
        requests = [
            self._req("skill:read-file", Capability.READ,
                      "src/cand.txt", "inspect"),
            self._req("skill:run-test", Capability.RUN_TEST,
                      "src/test_ok.py", "run tests"),
            self._req("skill:write-file", Capability.WRITE,
                      "src/cand.txt", "content=OK\n"),
        ]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=lambda: True, max_turns=6,
            sessions_root=self.sessions)
        return result.run.run_id

    def stub_run(self, run_id, state):
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(run_id=run_id, session_id="s",
                            mission=self.mission(mid="M-active"),
                            workspace_root=str(self.ws), state=state,
                            ledger_dir=str(run_dir)))
        return run_id

    def render(self):
        response = dispatch(Request(method="GET", path="/command"), self.cfg)
        return response.status, response.content_type, response.body


class RouteAndData(_CommandCase):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Command Center", html)

    def test_B_clean_empty_state(self):
        _, _, html = self.render()
        self.assertIn("No operations yet.", html)
        self.assertIn("No findings recorded.", html)
        self.assertIn("0 ACTIVE", html)

    def test_C_active_operation_renders(self):
        run_id = self.stub_run("run-active-cc", "running")
        status, _, html = self.render()
        self.assertEqual(status, 200)
        self.assertIn(run_id, html)
        self.assertIn("RUNNING", html)

    def test_D_specialist_rendering(self):
        self.complete_run()
        _, _, html = self.render()
        for role in cc.SPECIALIST_ROLES:
            self.assertIn(role, html)
        self.assertIn("SPECIALIST OPERATIONS", html)
        # states are derived, never invented availability
        self.assertNotIn(">BLOCKED<", html)
        self.assertNotIn(">READY<", html)

    def test_E_findings_rendering(self):
        run_id = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        finding_ids = [r.get("finding_id") for r in records
                       if r.get("kind") == "finding" and r.get("finding_id")]
        self.assertTrue(finding_ids)
        _, _, html = self.render()
        for fid in finding_ids:
            self.assertIn(fid, html)
        self.assertIn("UNVERIFIED", html)

    def test_F_gate_rendering(self):
        run_id = self.complete_run()
        self.assertEqual(api.get_gate(run_id, self.runs)["decision"],
                         "complete")
        _, _, html = self.render()
        self.assertIn("QUALITY GATE STATUS", html)
        self.assertIn("COMPLETE", html)
        self.assertIn("7/7", html)

    def test_F2_refuse_preserved(self):
        session = self._session()
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted([self._req("skill:read-file", Capability.READ,
                                       "/etc/hostname", "escape")]),
            probe=None, max_turns=3, sessions_root=self.sessions)
        self.assertEqual(result.run.gate_verdict, "refuse")
        _, _, html = self.render()
        self.assertIn("REFUSE", html)
        self.assertNotIn(">FAILED<", html)

    def test_G_navigation_links(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertIn('href="/operations"', html)
        self.assertIn('href="/roles"', html)
        self.assertIn('href="/skills"', html)
        self.assertIn('href="/capabilities"', html)
        self.assertIn("/operations/", html)  # per-operation links
        self.assertIn("UNAVAILABLE", html)   # unimplemented pages marked


class SafetyAndGovernance(_CommandCase):
    def test_H_no_fabricated_metrics(self):
        self.complete_run()
        data = cc.collect(runs_root=self.runs, sessions_root=self.sessions)
        self.assertEqual(len(data["active"]), 0)
        self.assertEqual(data["gate_counts"]["complete"], 1)
        self.assertEqual(data["gate_counts"]["refuse"], 0)
        _, _, html = self.render()
        # counts are the real aggregate, not invented
        self.assertIn(f'{len(data["runs"])} TOTAL', html)
        self.assertIn(f'{len(data["active"])} ACTIVE', html)
        # no fabricated metric labels / specialist availability
        self.assertNotIn("SEVERITY", html)
        self.assertNotIn("HEARTBEAT", html)
        self.assertNotIn(">BLOCKED<", html)

    def test_I_no_credentials(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html)
        self.assertNotIn("authorization", html.lower())

    def test_J_no_direct_execution_controls(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("operations/start", html)
        self.assertNotIn("runs/model", html)
        self.assertNotIn("execute_capability", html)

    def test_K_no_direct_broker_policy_runtime(self):
        root = Path(cc.__file__).resolve().parents[2]
        view = (root / "http" / "views" /
                "command_center.py").read_text("utf-8")
        route = (root / "http" / "routes" / "command.py").read_text("utf-8")
        self.assertIn("harness import api", view)
        self.assertIn("views import command_center", route)
        for name, src in (("views/command_center.py", view),
                          ("routes/command.py", route)):
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal", "append_evidence",
                          "EvidenceLedger", "LedgerWriter",
                          "run_model_mission(", "def propose(",
                          "while True"):
                self.assertNotIn(token, src, f"{token} in {name}")

    def test_L_existing_screens_still_render(self):
        run_id = self.complete_run()
        for path in (f"/operations/{run_id}/events",
                     f"/operations/{run_id}/decision-trace",
                     f"/operations/{run_id}"):
            response = dispatch(Request(method="GET", path=path), self.cfg)
            self.assertEqual(response.status, 200, path)
            self.assertIn("RAPHAEL", response.body)


if __name__ == "__main__":
    unittest.main()
