"""tests.test_d5_ui_governed_run — D5-2 positive governed UI path.

Proves the NEW OPERATION form can drive the EXISTING governed Runner to
a legitimate QualityGate COMPLETE through the real HTTP route, by
exposing ordinary operator inputs that map onto documented Runner
arguments. No UI-only path, no mock, no weakened gate.

Test world mirrors tests/test_harness_e2e.py: a deterministic in-scope
workspace where the candidate retest succeeds, the challenge yields no
counter-example, and a real RUN_TEST file passes.

Real seam: HTTP route -> harness.api -> Runner -> Runtime -> Broker ->
Policy -> capabilities -> ledger -> QualityGate.
"""
from __future__ import annotations

import http.client
import shutil
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.app import RaphaelHTTPConfig, create_server

PASSING_TEST = (
    "import unittest\n\n\nclass OkTest(unittest.TestCase):\n"
    "    def test_ok(self):\n        self.assertTrue(True)\n"
)
FAILING_TEST = (
    "import unittest\n\n\nclass BadTest(unittest.TestCase):\n"
    "    def test_fails(self):\n        self.assertTrue(False)\n"
)

CANDIDATE = "src/cand_ok.txt"
CHALLENGER = "src/challenger.txt"
PASSING_TARGET = "src/test_ok.py"
FAILING_TARGET = "src/test_fail.py"
SCOPE = "src/"


class _GovernedRunCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_ui_run_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        src = self.ws / "src"
        src.mkdir(parents=True)
        (src / "cand_ok.txt").write_text("OK\n", encoding="utf-8")
        (src / "challenger.txt").write_text("clean\n", encoding="utf-8")
        (src / "test_ok.py").write_text(PASSING_TEST, encoding="utf-8")
        (src / "test_fail.py").write_text(FAILING_TEST, encoding="utf-8")
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
        self.port = self.server.server_address[1]

    # --- helpers --------------------------------------------------------

    def _mission(self):
        return Mission(
            mission_id="D5-GOV-RUN",
            description="D5 governed positive UI run",
            scope=SCOPE,
            criteria=["recover through the governed loop"],
            problem={"symptom_target": CANDIDATE,
                     "capability": "read",
                     "purpose": "d5:governed-probe"},
        )

    def _session(self):
        return api.create_session(mission=self._mission(),
                                  workspace_root=self.ws,
                                  sessions_root=self.sessions,
                                  model="unconfigured", provider="none")

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8")
        finally:
            conn.close()

    def _post_start(self, fields):
        body = urllib.parse.urlencode(fields)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request(
                "POST", "/operations/start", body=body,
                headers={"Content-Type":
                         "application/x-www-form-urlencoded"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8")
        finally:
            conn.close()

    def _positive_fields(self, session, **overrides):
        fields = {
            "session_id": session.session_id,
            "mode": "runner",
            "candidate_target": CANDIDATE,
            "candidate_summary": "candidate ok",
            "challenger_target": CHALLENGER,
            "challenger_forbidden_substring": "ZZZ-ABSENT",
            "verification_tests": PASSING_TARGET,
            "max_replans": "1",
        }
        fields.update(overrides)
        return fields

    def _run_id(self, session):
        return api.get_session(session.session_id,
                               self.sessions).current_run_id


class FormControls(_GovernedRunCase):
    def test_A_form_exposes_advanced_governed_controls(self):
        self._session()
        status, html = self._get("/operations")
        self.assertEqual(status, 200)
        for field in ("candidate_summary", "challenger_target",
                      "challenger_forbidden_substring",
                      "verification_tests", "max_replans"):
            self.assertIn(f'name="{field}"', html, msg=field)

    def test_B_max_replans_is_bounded_and_validated(self):
        session = self._session()
        status, body = self._post_start(self._positive_fields(
            session, max_replans="not-a-number"))
        self.assertEqual(status, 422)
        self.assertIn("INVALID_INPUT", body)
        status, body = self._post_start(self._positive_fields(
            session, max_replans="9999"))
        self.assertEqual(status, 422)
        self.assertIn("INVALID_INPUT", body)


class PositiveGovernedRun(_GovernedRunCase):
    def test_C_positive_run_reaches_gate_complete(self):
        session = self._session()
        status, body = self._post_start(self._positive_fields(session))
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        self.assertIn(f"/operations/{run_id}", body)

        run = api.get_run(run_id, self.runs)
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.gate_verdict, "complete")
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "complete")
        self.assertEqual(gate["reasons"], [])

        records = api.get_evidence(run_id, self.runs)

        # Verification tests reached the Runner and executed via RUN_TEST.
        run_tests = [r for r in records
                     if r.get("kind") == "request"
                     and r.get("capability") == "run_test"]
        self.assertEqual([r["target"] for r in run_tests], [PASSING_TARGET])
        self.assertTrue(any(
            r.get("kind") == "decision"
            and r.get("request_seq") == run_tests[0]["seq"]
            and r.get("decision") == "allow" for r in records))

        # Challenger target reached the Runner's falsifier path.
        challenger_requests = [r for r in records
                               if r.get("kind") == "request"
                               and r.get("target") == CHALLENGER]
        self.assertTrue(challenger_requests)

        # Runner defaults for regression/probe proof are preserved.
        producers = {r.get("producer") for r in records
                     if r.get("kind") == "evidence"}
        self.assertIn("regression", producers)
        self.assertIn("probe", producers)

        # Finding lifecycle resolved (no UNVERIFIED/REFUTED terminal).
        finding_states = [r.get("state") for r in records
                          if r.get("kind") == "finding"]
        self.assertIn("verified", finding_states)

        # The console renders COMPLETE only from the persisted gate.
        status, console = self._get(f"/operations/{run_id}")
        self.assertEqual(status, 200)
        self.assertIn('class="gate-final">COMPLETE', console)

    def test_D_missing_run_test_refuses(self):
        session = self._session()
        fields = self._positive_fields(session)
        fields.pop("verification_tests")
        status, _ = self._post_start(fields)
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        run = api.get_run(run_id, self.runs)
        self.assertEqual(run.gate_verdict, "refuse")
        records = api.get_evidence(run_id, self.runs)
        self.assertFalse([r for r in records
                          if r.get("kind") == "request"
                          and r.get("capability") == "run_test"])
        status, console = self._get(f"/operations/{run_id}")
        self.assertIn('class="gate-final">REFUSE', console)
        self.assertNotIn('class="gate-final">COMPLETE', console)

    def test_E_failing_run_test_refuses(self):
        session = self._session()
        status, _ = self._post_start(self._positive_fields(
            session, verification_tests=FAILING_TARGET))
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        run = api.get_run(run_id, self.runs)
        self.assertEqual(run.gate_verdict, "refuse")
        gate = api.get_gate(run_id, self.runs)
        self.assertTrue(
            any("RUN_TEST" in reason for reason in gate.get("reasons", [])),
            msg=gate.get("reasons"))

    def test_F_out_of_scope_target_still_denied(self):
        session = self._session()
        fields = self._positive_fields(session, candidate_target="etc/passwd")
        status, _ = self._post_start(fields)
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        records = api.get_evidence(run_id, self.runs)
        denials = [r for r in records
                   if r.get("kind") == "decision"
                   and r.get("reason") == "scope-mismatch"]
        self.assertTrue(denials)
        self.assertEqual(api.get_run(run_id, self.runs).gate_verdict,
                         "refuse")

    def test_G_omitted_advanced_fields_keep_runner_defaults(self):
        session = self._session()
        # Only the historical controls: the Runner defaults must still
        # apply (default challenger target src/still_buggy.py).
        status, _ = self._post_start({
            "session_id": session.session_id,
            "mode": "runner",
            "candidate_target": CANDIDATE,
        })
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        records = api.get_evidence(run_id, self.runs)
        targets = {r.get("target") for r in records
                   if r.get("kind") == "request"}
        self.assertIn("src/still_buggy.py", targets)


if __name__ == "__main__":
    unittest.main()
