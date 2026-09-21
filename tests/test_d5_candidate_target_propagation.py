"""tests.test_d5_candidate_target_propagation — D5 UI target propagation.

Regression proof that `candidate_target` submitted through the REAL
`POST /operations/start` HTTP route reaches the REAL Harness -> Runner
path and lands on the persisted Finding and verification retest.

No mocks at the seam being tested: a real HTTP server on a loopback
port, the real router, the real `harness.api`, the real Runner/Broker/
Policy stack, and the real on-disk evidence ledger. `Runner.run()` is
never called directly here — every run is started over HTTP.

Two cases:
  - WITH candidate_target=fixtures/authkit/login.py: the symptom target
    must propagate to the Finding and the runner's verification retest.
  - WITHOUT candidate_target: the documented Runner default
    `src/fixed.py` must remain, and the Planner must still derive the
    symptom target from the mission (the two targets diverge).
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
SYMPTOM_TARGET = "fixtures/authkit/login.py"
RUNNER_DEFAULT_TARGET = "src/fixed.py"


class _PropagationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_prop_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        self.ws.mkdir(parents=True)
        # Real governed workspace: the real authkit fixture tree, so the
        # symptom target genuinely exists and READ can ALLOW.
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

    def _mission(self) -> Mission:
        return Mission(
            mission_id="D5-PROP-001",
            description="D5 target propagation regression",
            scope=SCOPE,
            criteria=["evidence persisted", "finding visible",
                      "gate verdict"],
            problem={"symptom_target": SYMPTOM_TARGET,
                     "capability": "read",
                     "purpose": "d5-prop:authkit-probe"},
        )

    def _session(self):
        return api.create_session(mission=self._mission(),
                                  workspace_root=self.ws,
                                  sessions_root=self.sessions,
                                  model="unconfigured", provider="none")

    def _post_start(self, fields):
        """POST /operations/start over real TCP. Returns (status, body)."""
        body = urllib.parse.urlencode(fields)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request(
                "POST", "/operations/start", body=body,
                headers={"Content-Type":
                         "application/x-www-form-urlencoded"})
            resp = conn.getresponse()
            status, data = resp.status, resp.read()
        finally:
            conn.close()
        return status, data.decode("utf-8")

    def _newest_run(self, session) -> str:
        reloaded = api.get_session(session.session_id, self.sessions)
        run_id = reloaded.current_run_id
        self.assertIn(run_id, api.get_runs(self.runs))
        return run_id

    def _records(self, run_id):
        return api.get_evidence(run_id, self.runs)

    @staticmethod
    def _matching(records, kind, requester=None):
        return [r for r in records if r.get("kind") == kind
                and (requester is None
                     or r.get("requester") == requester)]

    @staticmethod
    def _all_targets(records):
        targets = set()
        for rec in records:
            if rec.get("target") is not None:
                targets.add(rec["target"])
            payload = rec.get("payload")
            if isinstance(payload, dict) and payload.get("target") is not None:
                targets.add(payload["target"])
        return targets


class CandidateTargetSubmitted(_PropagationCase):
    def test_A_http_candidate_target_reaches_finding_and_verification(self):
        session = self._session()
        status, body = self._post_start({
            "session_id": session.session_id,
            "mode": "runner",
            "max_turns": "14",
            "candidate_target": SYMPTOM_TARGET,
        })

        # The run was created by the real HTTP route (its response is the
        # console redirect page, which only `start_operation` renders).
        self.assertEqual(status, 200)
        run_id = self._newest_run(session)
        self.assertIn(f"/operations/{run_id}", body)

        records = self._records(run_id)

        # A) Planner initial action derives the target from the mission.
        planner = self._matching(records, "request", "planner")
        self.assertEqual([r["target"] for r in planner], [SYMPTOM_TARGET])

        # C) Finding carries the submitted candidate target.
        findings = self._matching(records, "finding")
        self.assertTrue(findings)
        self.assertEqual([f["target"] for f in findings], [SYMPTOM_TARGET])

        # B) Runner verification retest uses the submitted candidate target.
        runner = self._matching(records, "request", "runner")
        self.assertTrue(runner)
        self.assertEqual({r["target"] for r in runner}, {SYMPTOM_TARGET})

        # D) Verification evidence records the same target.
        verifier_retests = [
            r for r in records
            if r.get("producer") == "verifier"
            and isinstance(r.get("payload"), dict)
            and r["payload"].get("kind") == "retest"
        ]
        self.assertTrue(verifier_retests)
        self.assertEqual(
            {r["payload"]["target"] for r in verifier_retests},
            {SYMPTOM_TARGET})

        # The documented Runner default must NOT appear anywhere on the
        # candidate verification path.
        self.assertNotIn(RUNNER_DEFAULT_TARGET, self._all_targets(records))

        # The symptom target was ALLOWed, so no scope violation.
        scope_denies = [
            r for r in records
            if r.get("kind") == "decision"
            and r.get("reason") == "scope-mismatch"
        ]
        self.assertEqual(scope_denies, [])


class CandidateTargetOmitted(_PropagationCase):
    def test_B_omitted_candidate_target_keeps_runner_default(self):
        session = self._session()
        status, body = self._post_start({
            "session_id": session.session_id,
            "mode": "runner",
            "max_turns": "14",
        })
        self.assertEqual(status, 200)
        run_id = self._newest_run(session)
        self.assertIn(f"/operations/{run_id}", body)

        records = self._records(run_id)

        # Control: the Planner still derives the symptom target from the
        # mission ...
        planner = self._matching(records, "request", "planner")
        self.assertEqual([r["target"] for r in planner], [SYMPTOM_TARGET])

        # ... while the candidate verification path keeps the Runner's
        # documented default, which is out of mission scope.
        findings = self._matching(records, "finding")
        self.assertEqual([f["target"] for f in findings],
                         [RUNNER_DEFAULT_TARGET])
        runner = self._matching(records, "request", "runner")
        self.assertEqual({r["target"] for r in runner},
                         {RUNNER_DEFAULT_TARGET})
        scope_denies = [
            r for r in records
            if r.get("kind") == "decision"
            and r.get("target") == RUNNER_DEFAULT_TARGET
            and r.get("reason") == "scope-mismatch"
        ]
        self.assertTrue(scope_denies)


class HttpRouteIsReal(_PropagationCase):
    def test_C_start_requires_a_real_session_via_the_route(self):
        """Proves the test talks to the real route, not Runner.run().

        An unknown session is rejected by `operations.start_operation`
        (404 SESSION_NOT_FOUND) before any run is constructed — a
        boundary that only exists on the HTTP route.
        """
        status, body = self._post_start({
            "session_id": "no-such-session",
            "mode": "runner",
            "candidate_target": SYMPTOM_TARGET,
        })
        self.assertEqual(status, 404)
        self.assertIn("SESSION_NOT_FOUND", body)
        self.assertEqual(api.get_runs(self.runs), [])


if __name__ == "__main__":
    unittest.main()
