"""tests.test_d5_ui_candidate_default — D5 UI mission-derived default.

Proves the NEW OPERATION form derives `candidate_target` from the
selected session's `mission.problem["symptom_target"]` (presentation
layer only), while explicit operator input is forwarded unchanged and
Policy remains authoritative.

Real HTTP server + real router + real `harness.api`; no mocks at the
UI/Harness seam.
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
from raphael_ibm_bob.http.views import operations_console as console

REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPE = "fixtures/authkit"
SYMPTOM_TARGET = "fixtures/authkit/login.py"
OTHER_IN_SCOPE_TARGET = "fixtures/authkit/store.py"
OUT_OF_SCOPE_TARGET = "src/fixed.py"
RUNNER_DEFAULT_TARGET = "src/fixed.py"


class _UiDefaultCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_ui_def_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        self.ws.mkdir(parents=True)
        shutil.copytree(REPO_ROOT / SCOPE, self.ws / SCOPE)
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

    def _mission(self, symptom_target=SYMPTOM_TARGET):
        problem = {"capability": "read", "purpose": "d5-ui:def"}
        if symptom_target is not None:
            problem["symptom_target"] = symptom_target
        return Mission(
            mission_id="D5-UI-DEF-001",
            description="D5 UI default derivation",
            scope=SCOPE,
            criteria=["evidence persisted"],
            problem=problem,
        )

    def _session(self, mission="default"):
        if mission == "default":
            mission = self._mission()
        return api.create_session(mission=mission,
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

    def _run_id(self, session):
        return api.get_session(session.session_id,
                               self.sessions).current_run_id

    @staticmethod
    def _candidate_input(html: str) -> str:
        marker = 'name="candidate_target"'
        idx = html.index(marker)
        return html[idx:html.index(">", idx)]


class MissionDerivedDefault(_UiDefaultCase):
    def test_A_form_defaults_to_mission_symptom_target(self):
        self._session()
        status, html = self._get("/operations")
        self.assertEqual(status, 200)
        field = self._candidate_input(html)
        self.assertIn(f'value="{SYMPTOM_TARGET}"', field)
        self.assertNotIn(f'value="{RUNNER_DEFAULT_TARGET}"', field)
        # The option carries the mission-derived target for client sync.
        self.assertIn("data-candidate-target", html)

    def test_D_missing_symptom_target_falls_back_safely(self):
        self._session(mission=self._mission(symptom_target=None))
        status, html = self._get("/operations")
        self.assertEqual(status, 200)
        field = self._candidate_input(html)
        self.assertIn(f'value="{RUNNER_DEFAULT_TARGET}"', field)

    def test_E_session_without_mission_is_safe(self):
        self._session(mission=None)
        status, html = self._get("/operations")
        self.assertEqual(status, 200)
        field = self._candidate_input(html)
        self.assertIn(f'value="{RUNNER_DEFAULT_TARGET}"', field)


class ExplicitOverride(_UiDefaultCase):
    def test_B_operator_target_is_forwarded_unchanged(self):
        session = self._session()
        status, body = self._post_start({
            "session_id": session.session_id,
            "mode": "runner",
            "candidate_target": OTHER_IN_SCOPE_TARGET,
        })
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        self.assertIn(f"/operations/{run_id}", body)
        records = api.get_evidence(run_id, self.runs)
        # The Planner still derives the mission symptom target ...
        planner = [r for r in records
                   if r.get("kind") == "request"
                   and r.get("requester") == "planner"]
        self.assertEqual([r["target"] for r in planner], [SYMPTOM_TARGET])
        # ... while the candidate/finding path honours the operator value.
        findings = [r for r in records if r.get("kind") == "finding"]
        self.assertTrue(findings)
        self.assertEqual({f["target"] for f in findings},
                         {OTHER_IN_SCOPE_TARGET})
        retests = [r for r in records
                   if r.get("kind") == "request"
                   and r.get("purpose") == "verifier-retest"]
        self.assertTrue(retests)
        self.assertEqual({r["target"] for r in retests},
                         {OTHER_IN_SCOPE_TARGET})

    def test_C_out_of_scope_target_still_denied(self):
        session = self._session()
        status, _ = self._post_start({
            "session_id": session.session_id,
            "mode": "runner",
            "candidate_target": OUT_OF_SCOPE_TARGET,
        })
        self.assertEqual(status, 200)
        run_id = self._run_id(session)
        records = api.get_evidence(run_id, self.runs)
        scope_denies = [
            r for r in records
            if r.get("kind") == "decision"
            and r.get("target") == OUT_OF_SCOPE_TARGET
            and r.get("reason") == "scope-mismatch"
        ]
        self.assertTrue(scope_denies)
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")


class DefaultConstant(_UiDefaultCase):
    def test_F_fallback_constant_matches_runner_default(self):
        self.assertEqual(console.DEFAULT_CANDIDATE_TARGET,
                         RUNNER_DEFAULT_TARGET)


if __name__ == "__main__":
    unittest.main()
