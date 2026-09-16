"""tests.test_findings_intelligence — M15.6 Findings Intelligence tests.

The screen reads the SAME persisted ledger the system already writes
(`kind="finding"` records + `EvidenceRecord.finding_id` links) through
the read-only `harness.api` path. These tests build real ledgers with
the real `EvidenceLedger` + `FindingStore` (not a parallel store) and
assert on the rendered HTML.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import (
    ActionRequest, Capability, Finding, FindingState, Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig, Request, create_server, dispatch,
)
from raphael_ibm_bob.http.views import findings_intelligence as fi


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m156_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        self.ws.mkdir(parents=True)
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.runs.mkdir(parents=True)
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs,
                                     host="127.0.0.1", port=0)

    def mission(self, mid="M-findings"):
        return Mission(mission_id=mid, description="Findings fixture",
                       scope="src/", criteria=["c"],
                       problem={"symptom_target": "src/cand.txt"})

    def _ledger_run(self, run_id, specs):
        """Build a real ledger run with findings + linked evidence.

        specs: list of (finding_id, [states...], target, link_evidence,
                        link_request)
        `states` is the transition path starting from UNVERIFIED.
        """
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = EvidenceLedger(run_dir)
        store = FindingStore(ledger)
        for finding_id, states, target, with_ev, with_req in specs:
            store.register(Finding(
                finding_id=finding_id, state=FindingState.UNVERIFIED,
                summary=f"candidate about {target}", target=target))
            current = FindingState.UNVERIFIED
            for state in states:
                store.transition(finding_id, state)
                current = state
            if with_ev:
                ledger.append_evidence(
                    evidence_id=f"V-{finding_id}", producer="verifier",
                    request_seq=0, decision_seq=0, result_seq=None,
                    payload={"kind": "retest"}, finding_id=finding_id)
                ledger.append_evidence(
                    evidence_id=f"O-{finding_id}", producer="probe",
                    request_seq=0, decision_seq=0, result_seq=None,
                    payload={"kind": "probe", "allowed": True},
                    finding_id=finding_id)
            if with_req:
                ledger.append_request(ActionRequest(
                    sequence=0, requester="skill:read-file",
                    capability=Capability.READ, target=target,
                    purpose="retest", finding_id=finding_id))
        ledger.close()
        save_run(RaphaelRun(
            run_id=run_id, session_id="sess", mission=self.mission(),
            workspace_root=str(self.ws), state="completed",
            ledger_dir=str(run_dir)))
        return run_id

    def mixed_run(self):
        return self._ledger_run("run-findings-1", [
            ("F-unver", [], "src/a.txt", False, False),
            ("F-ver", [FindingState.VERIFIED], "src/b.txt", True, True),
            ("F-ref", [FindingState.REFUTED], "src/c.txt", True, False),
            ("F-sup", [FindingState.VERIFIED, FindingState.SUPERSEDED],
             "src/d.txt", False, False),
        ])

    def render(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/findings"), self.cfg)
        return response.status, response.content_type, response.body


class Render(_Case):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Findings Intelligence", html)

    def test_B_empty_state(self):
        status, _, html = self.render()
        self.assertEqual(status, 200)
        self.assertIn("No findings recorded", html)
        self.assertIn(">0<", html)  # TOTAL FINDINGS is zero

    def test_C_persisted_findings_render(self):
        self.mixed_run()
        _, _, html = self.render()
        for fid in ("F-unver", "F-ver", "F-ref", "F-sup"):
            self.assertIn(fid, html)

    def test_D_unverified_renders(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn('data-state="unverified"', html)
        self.assertIn(">UNVERIFIED<", html)

    def test_E_verified_renders(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn('data-state="verified"', html)
        self.assertIn(">VERIFIED<", html)

    def test_F_refuted_renders(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn('data-state="refuted"', html)
        self.assertIn(">REFUTED<", html)

    def test_G_superseded_renders(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn('data-state="superseded"', html)
        self.assertIn(">SUPERSEDED<", html)

    def test_H_counts_derived_from_persisted(self):
        self.mixed_run()
        data = fi.collect(runs_root=self.runs, sessions_root=self.sessions)
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["counts"], {"unverified": 1, "verified": 1,
                                          "refuted": 1, "superseded": 1})
        _, _, html = self.render()
        for label in ("TOTAL FINDINGS", "UNVERIFIED", "VERIFIED",
                      "REFUTED", "SUPERSEDED"):
            self.assertIn(label, html)

    def test_lifecycle_history_is_observed_not_invented(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn("OBSERVED LIFECYCLE TRANSITIONS", html)
        self.assertIn("UNVERIFIED → VERIFIED", html)
        self.assertIn("VERIFIED → SUPERSEDED", html)


class Safety(_Case):
    def test_I_no_fabricated_metrics(self):
        self.mixed_run()
        _, _, html = self.render()
        for forbidden in ("SEVERITY", "CVSS", "EXPLOITABILITY",
                          "CONFIDENCE", "PRIORITY", "RISK SCORE"):
            self.assertNotIn(forbidden, html, forbidden)

    def test_J_evidence_relationship_is_authoritative(self):
        run_id = self.mixed_run()
        _, _, html = self.render()
        # linked evidence ids must be the real ledger ids
        self.assertIn("V-F-ver", html)
        self.assertIn("O-F-ver", html)
        self.assertIn("V-F-ref", html)
        records = api.get_evidence(run_id, self.runs)
        linked = [r for r in records
                  if r.get("kind") == "evidence" and r.get("finding_id") == "F-ver"]
        self.assertEqual(len(linked), 2)

    def test_K_operation_links_use_real_run_ids(self):
        run_id = self.mixed_run()
        _, _, html = self.render()
        self.assertIn(f'href="/operations/{run_id}"', html)
        self.assertIn(f'href="/operations/{run_id}/decision-trace"', html)
        self.assertIn(f'href="/operations/{run_id}/events"', html)

    def test_L_missing_relationships_honest(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn("UNKNOWN / NOT VERIFIED", html)
        self.assertIn("NOT VERIFIED", html)

    def test_M_client_side_filter_and_search(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertIn('data-filter="verified"', html)
        self.assertIn('data-state="verified"', html)
        self.assertIn('id="search"', html)
        self.assertIn("data-search=", html)
        self.assertNotIn("?state=", html)

    def test_N_no_direct_execution_controls(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("operations/start", html)
        self.assertNotIn("runs/model", html)
        self.assertNotIn("execute_capability", html)

    def test_O_governance_static(self):
        root = Path(fi.__file__).resolve().parents[2]
        view = (root / "http" / "views" /
                "findings_intelligence.py").read_text("utf-8")
        route = (root / "http" / "routes" / "findings.py").read_text("utf-8")
        self.assertIn("harness import api", view)
        for name, src in (("views", view), ("routes", route)):
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

    def test_P_no_credentials(self):
        self.mixed_run()
        _, _, html = self.render()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html)
        self.assertNotIn("authorization", html.lower())


class ExistingScreensStillRender(_Case):
    def test_Q_command_center(self):
        response = dispatch(Request(method="GET", path="/command"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Command Center", response.body)
        self.assertIn("/operations/findings", response.body)

    def test_R_decision_trace(self):
        run_id = self.mixed_run()
        response = dispatch(
            Request(method="GET",
                    path=f"/operations/{run_id}/decision-trace"), self.cfg)
        self.assertEqual(response.status, 200)

    def test_S_event_stream(self):
        run_id = self.mixed_run()
        response = dispatch(
            Request(method="GET", path=f"/operations/{run_id}/events"),
            self.cfg)
        self.assertEqual(response.status, 200)

    def test_served_over_http(self):
        import http.client
        self.mixed_run()
        server = create_server(self.cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", "/operations/findings")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Findings Intelligence", body)


if __name__ == "__main__":
    unittest.main()
