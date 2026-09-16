"""tests.test_evidence_intelligence — M15.7 Evidence Intelligence tests.

The screen reads the SAME persisted append-only ledger the system
writes (`runs/<id>/evidence.jsonl`) through the read-only
`harness.api.get_evidence` path. These tests drive the real governed
stack and assert on the rendered HTML.
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
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig, Request, create_server, dispatch,
)
from raphael_ibm_bob.http.views import evidence_intelligence as ei

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
        self.base = Path(tempfile.mkdtemp(prefix="m157_"))
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

    def mission(self):
        return Mission(mission_id="M-evidence", description="evidence run",
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

    def deny_run(self):
        session = self._session()
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted([self._req("skill:read-file", Capability.READ,
                                       "/etc/hostname", "escape")]),
            probe=None, max_turns=3, sessions_root=self.sessions)
        return result.run.run_id

    def render(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/evidence"), self.cfg)
        return response.status, response.content_type, response.body


class Render(_Case):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Evidence Intelligence", html)

    def test_B_empty_state(self):
        status, _, html = self.render()
        self.assertEqual(status, 200)
        self.assertIn("No evidence records persisted", html)
        self.assertIn("0 RECORDS", html)

    def test_C_real_persisted_evidence(self):
        run_id = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        self.assertTrue(records)
        _, _, html = self.render()
        self.assertEqual(html.count('class="erow"'), len(records))

    def test_D_real_evidence_ids(self):
        run_id = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        ids = [r.get("evidence_id") for r in records
               if r.get("kind") == "evidence" and r.get("evidence_id")]
        self.assertTrue(ids)
        _, _, html = self.render()
        for evidence_id in ids:
            self.assertIn(evidence_id, html)

    def test_E_real_evidence_kinds(self):
        self.complete_run()
        _, _, html = self.render()
        for label in ("ACTION REQUEST", "POLICY DECISION", "EXECUTION RESULT",
                      "EVIDENCE", "FINDING", "GATE DECISION"):
            self.assertIn(label, html)

    def test_F_persisted_counts(self):
        run_id = self.complete_run()
        data = ei.collect(runs_root=self.runs, sessions_root=self.sessions)
        records = api.get_evidence(run_id, self.runs)
        self.assertEqual(data["total"], len(records))
        self.assertEqual(
            data["evidence_total"],
            len([r for r in records if r.get("kind") == "evidence"]))
        _, _, html = self.render()
        self.assertIn(f'{data["total"]} RECORDS', html)

    def test_G_real_operation_links(self):
        run_id = self.complete_run()
        _, _, html = self.render()
        self.assertIn(f'href="/operations/{run_id}"', html)
        self.assertIn(f'href="/operations/{run_id}/decision-trace"', html)
        self.assertIn(f'href="/operations/{run_id}/events"', html)

    def test_H_finding_links(self):
        run_id = self.complete_run()
        findings = [r for r in api.get_evidence(run_id, self.runs)
                    if r.get("finding_id")]
        self.assertTrue(findings)
        _, _, html = self.render()
        self.assertIn('href="/operations/findings"', html)

    def test_I_honest_missing_relationships(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertIn("NO FINDING REFERENCE", html)

    def test_J_verification_falsification_authoritative(self):
        run_id = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        verifiers = [r for r in records if r.get("producer") == "verifier"]
        falsifiers = [r for r in records if r.get("producer") == "falsifier"]
        data = ei.collect(runs_root=self.runs, sessions_root=self.sessions)
        cats = {r["category"] for r in data["rows"]}
        if verifiers:
            self.assertIn("verification", cats)
        if falsifiers:
            self.assertIn("falsification", cats)
        _, _, html = self.render()
        self.assertIn('data-cat="verification"', html)

    def test_K_artifact_references_authoritative(self):
        run_id = self.complete_run()
        results = [r for r in api.get_evidence(run_id, self.runs)
                   if r.get("kind") == "result" and r.get("artifact_ref")]
        self.assertTrue(results)
        _, _, html = self.render()
        self.assertIn(".json", html)


class Safety(_Case):
    def test_L_search_and_filter(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertIn('data-filter="verification"', html)
        self.assertIn('data-cat="verification"', html)
        self.assertIn('id="search"', html)
        self.assertIn("data-search=", html)
        self.assertNotIn("?kind=", html)

    def test_M_no_fabricated_metrics(self):
        self.complete_run()
        _, _, html = self.render()
        for forbidden in ("SEVERITY", "CVSS", "EXPLOITABILITY",
                          "CONFIDENCE", "RISK SCORE"):
            self.assertNotIn(forbidden, html, forbidden)

    def test_N_no_credentials(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html)
        self.assertNotIn("authorization", html.lower())

    def test_O_no_execution_controls(self):
        self.complete_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("operations/start", html)
        self.assertNotIn("execute_capability", html)

    def test_P_governance_static(self):
        root = Path(ei.__file__).resolve().parents[2]
        view = (root / "http" / "views" /
                "evidence_intelligence.py").read_text("utf-8")
        route = (root / "http" / "routes" / "evidence.py").read_text("utf-8")
        self.assertIn("harness import api", view)
        for name, src in (("view", view), ("route", route)):
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal", "append_evidence",
                          "append_gate", "EvidenceLedger", "LedgerWriter",
                          "FindingStore", ".transition(",
                          "run_model_mission(", "while True"):
                self.assertNotIn(token, src, f"{token} in {name}")


class Regression(_Case):
    def test_Q_command_center(self):
        response = dispatch(Request(method="GET", path="/command"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("/operations/evidence", response.body)

    def test_R_findings(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/findings"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Findings Intelligence", response.body)

    def test_S_decision_trace(self):
        run_id = self.complete_run()
        response = dispatch(Request(
            method="GET", path=f"/operations/{run_id}/decision-trace"), self.cfg)
        self.assertEqual(response.status, 200)

    def test_T_event_stream(self):
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
        conn.request("GET", "/operations/evidence")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Evidence Intelligence", body)


if __name__ == "__main__":
    unittest.main()
