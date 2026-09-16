"""tests.test_gate_intelligence — M15.8 Policy & Quality Gate tests.

The screen DISPLAYS the authoritative persisted QualityGate verdict and
the persisted policy decisions through the read-only `harness.api`. It
never recomputes a verdict. These tests drive the real governed stack.
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
    RaphaelHTTPConfig, Request, create_server, dispatch,
)
from raphael_ibm_bob.http.views import gate_intelligence as gi

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


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m158_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(PASSING_TEST,
                                                     encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs,
                                     host="127.0.0.1", port=0)

    def mission(self, mid="M-gate"):
        return Mission(mission_id=mid, description="gate mission",
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
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted([
                self._req("skill:read-file", Capability.READ,
                          "src/cand.txt", "inspect"),
                self._req("skill:run-test", Capability.RUN_TEST,
                          "src/test_ok.py", "run tests"),
                self._req("skill:write-file", Capability.WRITE,
                          "src/cand.txt", "content=OK\n")]),
            probe=lambda: True, max_turns=6, sessions_root=self.sessions)
        return result.run.run_id

    def deny_run(self):
        session = self._session()
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted([self._req("skill:read-file", Capability.READ,
                                       "/etc/hostname", "escape")]),
            probe=None, max_turns=3, sessions_root=self.sessions)
        return result.run.run_id

    def refuted_run(self):
        session = self._session()
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted([self._req("skill:write-file", Capability.WRITE,
                                       "src/cand.txt", "content=OK\n")]),
            probe=lambda: False, max_turns=4, sessions_root=self.sessions)
        return result.run.run_id

    def stub_run(self, run_id, state):
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(run_id=run_id, session_id="s",
                            mission=self.mission(mid="M-stub"),
                            workspace_root=str(self.ws), state=state,
                            ledger_dir=str(run_dir)))
        return run_id

    def render(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/gate"), self.cfg)
        return response.status, response.content_type, response.body


class Render(_Case):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Policy &amp; Quality Gate", html)

    def test_B_empty_state(self):
        status, _, html = self.render()
        self.assertEqual(status, 200)
        self.assertIn("No Harness-managed operations", html)
        self.assertIn(">0<", html)

    def test_C_real_complete_gate_renders(self):
        run_id = self.complete_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "complete")
        _, _, html = self.render()
        self.assertIn("COMPLETE", html)
        self.assertIn('class="gate-final ok">COMPLETE', html)

    def test_D_real_refuse_gate_renders(self):
        run_id = self.deny_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        _, _, html = self.render()
        self.assertIn('class="gate-final crit">REFUSE', html)

    def test_E_in_progress_is_honest(self):
        running = self.stub_run("run-running-gate", "running")
        failed = self.stub_run("run-failed-gate", "failed")
        _, _, html = self.render()
        self.assertIn("IN PROGRESS", html)        # running, no gate record
        self.assertIn("UNKNOWN / NOT VERIFIED", html)  # terminal, no gate

    def test_F_condition_count_from_authoritative_gate(self):
        run_id = self.complete_run()
        gate = api.get_gate(run_id, self.runs)
        data = gi.collect(runs_root=self.runs, sessions_root=self.sessions)
        op = [o for o in data["operations"] if o["run_id"] == run_id][0]
        self.assertEqual(len(op["conditions"]), len(gate["checks"]))
        _, _, html = self.render()
        self.assertIn("CONDITIONS EVALUATED", html)
        for condition in gate["checks"]:
            self.assertIn(condition, html)

    def test_G_verdict_from_gate_authority(self):
        for run_id, expected in ((self.complete_run(), "COMPLETE"),
                                 (self.deny_run(), "REFUSE")):
            gate = api.get_gate(run_id, self.runs)
            _, _, html = self.render()
            self.assertIn(expected, html)
            self.assertIn(gate["decision"], html)

    def test_H_http_does_not_calculate_verdict(self):
        # A REFUSE gate is rendered as REFUSE even though the ledger has
        # requests/decisions/results/evidence (which would "look" completable).
        run_id = self.refuted_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        records = api.get_evidence(run_id, self.runs)
        kinds = {r.get("kind") for r in records}
        self.assertTrue({"request", "decision", "result", "evidence"} <= kinds)
        _, _, html = self.render()
        self.assertIn('class="gate-final crit">REFUSE', html)
        self.assertNotIn('class="gate-final ok">COMPLETE', html)

    def test_I_policy_allow_from_real_evidence(self):
        run_id = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        allows = [r for r in records
                  if r.get("kind") == "decision" and r.get("decision") == "allow"]
        self.assertTrue(allows)
        _, _, html = self.render()
        self.assertIn("ALLOW", html)

    def test_J_policy_deny_from_real_evidence(self):
        run_id = self.deny_run()
        records = api.get_evidence(run_id, self.runs)
        denies = [r for r in records
                  if r.get("kind") == "decision" and r.get("decision") == "deny"]
        self.assertTrue(denies)
        _, _, html = self.render()
        self.assertIn("DENY", html)

    def test_K_deny_not_presented_as_execution(self):
        self.deny_run()
        _, _, html = self.render()
        self.assertIn("NOT EXECUTED (DENY)", html)

    def test_L_execution_from_real_result_records(self):
        run_id = self.complete_run()
        results = [r for r in api.get_evidence(run_id, self.runs)
                   if r.get("kind") == "result"]
        successful = [r for r in results if r.get("success") is True]
        self.assertTrue(successful)
        _, _, html = self.render()
        self.assertIn("SUCCESS", html)

    def test_M_verification_falsification_authoritative(self):
        run_id = self.complete_run()
        data = gi.collect(runs_root=self.runs, sessions_root=self.sessions)
        op = [o for o in data["operations"] if o["run_id"] == run_id][0]
        records = api.get_evidence(run_id, self.runs)
        expected = [r.get("evidence_id") for r in records
                    if r.get("producer") == "verifier"]
        self.assertEqual(op["verifications"], expected)

    def test_N_operation_links_real_runs(self):
        run_id = self.complete_run()
        _, _, html = self.render()
        self.assertIn(f'href="/operations/{run_id}"', html)

    def test_O_evidence_links_real_data(self):
        run_id = self.deny_run()
        gate = api.get_gate(run_id, self.runs)
        _, _, html = self.render()
        for ref in gate["evidence_refs"]:
            self.assertIn(ref, html)

    def test_P_finding_links_real_ids(self):
        run_id = self.deny_run()
        gate = api.get_gate(run_id, self.runs)
        _, _, html = self.render()
        for ref in gate["finding_refs"]:
            self.assertIn(ref, html)


class Safety(_Case):
    def test_Q_search_and_filter(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertIn('data-filter="COMPLETE"', html)
        self.assertIn("data-verdict=", html)
        self.assertIn('id="search"', html)
        self.assertNotIn("?verdict=", html)

    def test_R_no_fabricated_metrics(self):
        self.complete_run()
        data = gi.collect(runs_root=self.runs, sessions_root=self.sessions)
        _, _, html = self.render()
        self.assertIn(f'>{data["counts"]["operations"]}<', html)
        for forbidden in ("SEVERITY", "CVSS", "RISK SCORE", "EXPLOITABILITY"):
            self.assertNotIn(forbidden, html, forbidden)

    def test_S_no_credentials(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html)
        self.assertNotIn("authorization", html.lower())

    def test_T_no_execution_controls(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("operations/start", html)
        self.assertNotIn("execute_capability", html)
        self.assertNotIn("override", html.lower())
        self.assertNotIn(">APPROVE<", html)
        self.assertNotIn(">DENY REQUEST<", html)

    def test_U_governance_static(self):
        root = Path(gi.__file__).resolve().parents[2]
        view = (root / "http" / "views" /
                "gate_intelligence.py").read_text("utf-8")
        route = (root / "http" / "routes" / "gate.py").read_text("utf-8")
        self.assertIn("harness import api", view)
        for name, src in (("view", view), ("route", route)):
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal", "append_gate",
                          "append_evidence", "EvidenceLedger", "LedgerWriter",
                          "FindingStore", ".transition(",
                          "run_model_mission(", "while True"):
                self.assertNotIn(token, src, f"{token} in {name}")


class Regression(_Case):
    def test_V_command_center(self):
        response = dispatch(Request(method="GET", path="/command"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("/operations/gate", response.body)

    def test_W_findings(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/findings"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Findings Intelligence", response.body)

    def test_X_evidence(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/evidence"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Evidence Intelligence", response.body)

    def test_Y_decision_trace(self):
        run_id = self.complete_run()
        response = dispatch(Request(
            method="GET", path=f"/operations/{run_id}/decision-trace"), self.cfg)
        self.assertEqual(response.status, 200)

    def test_Z_event_stream(self):
        run_id = self.complete_run()
        response = dispatch(Request(
            method="GET", path=f"/operations/{run_id}/events"), self.cfg)
        self.assertEqual(response.status, 200)

    def test_served_over_http(self):
        import http.client
        self.complete_run()
        server = create_server(self.cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", "/operations/gate")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Policy &amp; Quality Gate", body)


if __name__ == "__main__":
    unittest.main()
