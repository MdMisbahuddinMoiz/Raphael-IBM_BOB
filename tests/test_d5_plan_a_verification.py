"""tests.test_d5_plan_a_verification — D5-3 explicit Plan-A verification.

The generic Runner previously hardcoded the Plan-A retest marker
``expected_substring="OK"``. That is a fixture-era convention, not a
governed invariant: a mission whose declared semantics are "a successful
ALLOWed READ" must be able to say so, while missions that require a
content marker keep one explicitly.

This proves the resolution precedence:
    explicit Runner argument > mission.problem["verification_expected_substring"]
    > legacy default "OK"
and that the Verifier, Falsifier, and QualityGate are unchanged: a
mismatch still leaves the Finding UNVERIFIED, the Falsifier still does
not run, and the gate still REFUSES.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.harness import api

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHKIT_SCOPE = "fixtures/authkit"
AUTHKIT_LOGIN = "fixtures/authkit/login.py"
CANDIDATE = "src/cand.txt"


class _PlanACase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_plana_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"

    def _run(self, *, candidate_text, problem_extra=None, **runner_kwargs):
        (self.ws / "src" / "cand.txt").write_text(candidate_text,
                                                  encoding="utf-8")
        problem = {"symptom_target": CANDIDATE, "capability": "read",
                   "purpose": "test:plan-a"}
        if problem_extra:
            problem.update(problem_extra)
        mission = Mission(mission_id="M-PLANA", description="plan-a",
                          scope="src/", criteria=["c"], problem=problem)
        session = api.create_session(mission=mission, workspace_root=self.ws,
                                     sessions_root=self.sessions)
        run = api.start_run(session, sessions_root=self.sessions,
                            runs_root=self.runs,
                            candidate_target=CANDIDATE, **runner_kwargs)
        records = api.get_evidence(run.run_id, self.runs)
        return run, records

    @staticmethod
    def _finding_states(records):
        return [r["state"] for r in records if r.get("kind") == "finding"]

    @staticmethod
    def _falsifier_evidence(records):
        return [r for r in records if r.get("producer") == "falsifier"]


class PlanAResolution(_PlanACase):
    def test_A_legacy_default_still_requires_ok(self):
        run, records = self._run(candidate_text="OK\n")
        self.assertIn("verified", self._finding_states(records))

    def test_B_legacy_default_mismatch_leaves_unverified_and_refuses(self):
        run, records = self._run(candidate_text="no-marker-here\n")
        self.assertEqual(self._finding_states(records), ["unverified"])
        self.assertEqual(run.gate_verdict, "refuse")
        gate = api.get_gate(run.run_id, self.runs)
        self.assertTrue(any("UNVERIFIED" in reason
                            for reason in gate.get("reasons", [])))
        # Falsifier must NOT operate on an UNVERIFIED finding.
        self.assertEqual(self._falsifier_evidence(records), [])

    def test_C_explicit_arg_match_verifies(self):
        run, records = self._run(candidate_text="hello\n",
                                 candidate_expected_substring="hello")
        self.assertIn("verified", self._finding_states(records))

    def test_D_explicit_arg_mismatch_leaves_unverified(self):
        run, records = self._run(candidate_text="OK\n",
                                 candidate_expected_substring="NOPE")
        self.assertEqual(self._finding_states(records), ["unverified"])
        self.assertEqual(run.gate_verdict, "refuse")
        self.assertEqual(self._falsifier_evidence(records), [])

    def test_E_mission_declared_none_observes_successfully(self):
        run, records = self._run(
            candidate_text="no-marker-here\n",
            problem_extra={"verification_expected_substring": None})
        self.assertIn("verified", self._finding_states(records))

    def test_F_mission_declared_marker_is_used(self):
        run, records = self._run(
            candidate_text="MARK\n",
            problem_extra={"verification_expected_substring": "MARK"})
        self.assertIn("verified", self._finding_states(records))

    def test_G_explicit_arg_overrides_mission_declaration(self):
        run, records = self._run(
            candidate_text="OK\n",
            problem_extra={"verification_expected_substring": "MISSION-MARK"},
            candidate_expected_substring="OK")
        self.assertIn("verified", self._finding_states(records))


class AuthkitMissionSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d5_authkit_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"

    def test_H_authkit_login_no_longer_stuck_unverified(self):
        # The canonical authkit mission declares observation-only
        # verification (login.py has no "OK" marker). No fixture change.
        mission = Mission(
            mission_id="M-authkit-plan-a",
            description="authkit observation-only verification",
            scope=AUTHKIT_SCOPE,
            criteria=["read observation succeeds"],
            problem={"symptom_target": AUTHKIT_LOGIN,
                     "capability": "read",
                     "purpose": "plan-a:probe-symptom",
                     "verification_expected_substring": None},
        )
        session = api.create_session(mission=mission, workspace_root=REPO_ROOT,
                                     sessions_root=self.sessions)
        run = api.start_run(session, sessions_root=self.sessions,
                            runs_root=self.runs,
                            candidate_target=AUTHKIT_LOGIN,
                            challenger_target=AUTHKIT_LOGIN,
                            challenger_forbidden_substring="ZZZ-ABSENT")
        records = api.get_evidence(run.run_id, self.runs)
        states = [r["state"] for r in records if r.get("kind") == "finding"]
        self.assertIn("verified", states)
        # With the finding VERIFIED the Falsifier now actually runs.
        self.assertTrue([r for r in records
                         if r.get("producer") == "falsifier"])


if __name__ == "__main__":
    unittest.main()
