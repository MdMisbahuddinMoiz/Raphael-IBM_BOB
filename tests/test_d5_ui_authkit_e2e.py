"""tests.test_d5_ui_authkit_e2e — D5-4 authkit UI end-to-end.

Drives the REAL authkit mission through the REAL UI HTTP route and
proves the corrected Plan-A verification semantics end to end:

  BEFORE (no mission expectation): the legacy "OK" default leaves the
  login.py finding UNVERIFIED, the Falsifier never runs, and the gate
  REFUSES with an unresolved-UNVERIFIED reason.

  AFTER (mission declares verification_expected_substring=None): the
  successful ALLOWed READ verifies the login.py finding, the Falsifier
  runs and REFUTES the shallow symptom fix, the Replanner derives Plan B
  on the real defect (session.py), the gate evaluates honestly and
  REFUSES only because the terminal finding is REFUTED without a further
  replan.

Uses the real repo workspace (read-only fixtures) and a temp runs/sessions
root. No fixture is modified; login.py is not given an "OK" marker.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPE = "fixtures/authkit"
LOGIN = "fixtures/authkit/login.py"
SESSION_PY = "fixtures/authkit/session.py"
TEST_LOGIN = "fixtures/authkit/test_login.py"


class _AuthkitUiCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_authkit_ui_"))
        self.addCleanup(shutil.rmtree, self.base, True)
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

    def _mission(self, *, declare_expectation):
        problem = {
            "symptom_target": LOGIN,
            "actual_defect_target": SESSION_PY,
            "capability": "read",
            "purpose": "d5-ui:authkit-e2e",
        }
        if declare_expectation:
            problem["verification_expected_substring"] = None
        return Mission(
            mission_id="D5-UI-E2E",
            description="Validate RAPHAEL governed authkit UI end-to-end path",
            scope=SCOPE,
            criteria=["Evidence is persisted",
                      "Finding lifecycle is visible",
                      "QualityGate produces an authoritative verdict"],
            problem=problem,
        )

    def _session(self, *, declare_expectation):
        return api.create_session(
            mission=self._mission(declare_expectation=declare_expectation),
            workspace_root=REPO_ROOT, sessions_root=self.sessions,
            model="unconfigured", provider="none")

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

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8")
        finally:
            conn.close()

    def _driving_fields(self, session):
        return {
            "session_id": session.session_id,
            "mode": "runner",
            "candidate_target": LOGIN,
            "candidate_summary": "authkit symptom probe",
            "challenger_target": SESSION_PY,
            "challenger_forbidden_substring": "BUGGY",
            "verification_tests": TEST_LOGIN,
            "max_replans": "1",
        }

    def _run_id(self, session):
        return api.get_session(session.session_id,
                               self.sessions).current_run_id

    @staticmethod
    def _finding_states(records, target):
        return [r["state"] for r in records
                if r.get("kind") == "finding" and r.get("target") == target]


class AuthkitUiBefore(_AuthkitUiCase):
    def test_A_legacy_default_leaves_finding_unverified_no_falsifier(self):
        session = self._session(declare_expectation=False)
        status, _ = self._post_start(self._driving_fields(session))
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        records = api.get_evidence(run_id, self.runs)
        self.assertEqual(self._finding_states(records, LOGIN), ["unverified"])
        self.assertEqual(
            [r for r in records if r.get("producer") == "falsifier"], [])
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        self.assertTrue(any("UNVERIFIED" in reason
                            for reason in gate.get("reasons", [])))


class AuthkitUiAfter(_AuthkitUiCase):
    def test_B_observation_semantics_refute_shallow_fix_and_replan(self):
        session = self._session(declare_expectation=True)
        status, _ = self._post_start(self._driving_fields(session))
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        run = api.get_run(run_id, self.runs)
        records = api.get_evidence(run_id, self.runs)

        # Plan-A finding on the real symptom target reached VERIFIED ...
        login_states = self._finding_states(records, LOGIN)
        self.assertIn("verified", login_states)
        self.assertIn("refuted", login_states)

        # ... the Falsifier actually ran (it only runs on VERIFIED).
        self.assertTrue([r for r in records
                         if r.get("producer") == "falsifier"])

        # ... and the Replanner derived Plan B onto the real defect.
        replans = [r for r in records if r.get("producer") == "replanner"]
        self.assertTrue(replans)
        self.assertEqual(len(run.plan_ids), 2)
        self.assertTrue(self._finding_states(records, SESSION_PY))

        # The RUN_TEST travelled through the boundary and passed.
        run_tests = [r for r in records
                     if r.get("kind") == "request"
                     and r.get("capability") == "run_test"]
        self.assertEqual([r["target"] for r in run_tests], [TEST_LOGIN])

        # Gate refuses HONESTLY: terminal finding refuted without a
        # further replan (budget exhausted), not a verification failure.
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        self.assertTrue(any("REFUTED finding without replan" in reason
                            for reason in gate.get("reasons", [])),
                        msg=gate.get("reasons"))

        # The UI renders the authoritative verdict.
        status, console = self._get(f"/operations/{run_id}")
        self.assertEqual(status, 200)
        self.assertIn('class="gate-final">REFUSE', console)
        self.assertNotIn('class="gate-final">COMPLETE', console)


if __name__ == "__main__":
    unittest.main()
