"""tests.test_d9_2_gate_presentation — QualityGate presentation correctness.

The backend QualityGate is authoritative; these tests prove the UI renders
passed/failed/unknown faithfully and never shows "7/7" alongside REFUSE.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers import DoneSignal
from raphael_ibm_bob.http.app import RaphaelHTTPConfig, Request, dispatch
from raphael_ibm_bob.http.views import decision_trace as dt

A, B, C, D, E, F, G = dt._gate_condition_names()
NAMES = list(dt._gate_condition_names())

PASSING_TEST = (
    "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_ok(self):\n        self.assertTrue(True)\n")


def _gate(decision, passed, failed):
    return {"decision": decision, "checks": list(passed) + list(failed),
            "reasons": [], "payload": {"passed": list(passed),
                                       "failed": list(failed)}}


class GateBreakdownUnit(unittest.TestCase):
    def test_payload_breakdown(self):
        passed, failed, unknown, names = dt.gate_breakdown(
            _gate("refuse", [A, B, C, E, F], [D, G]))
        self.assertEqual(passed, [A, B, C, E, F])
        self.assertEqual(failed, [D, G])
        self.assertEqual(unknown, [])
        self.assertEqual(len(names), 7)

    def test_unknown_when_omitted(self):
        gate = {"decision": "refuse", "checks": [A, B],
                "payload": {"passed": [A], "failed": [B]}}
        passed, failed, unknown, _ = dt.gate_breakdown(gate)
        self.assertEqual(passed, [A])
        self.assertEqual(failed, [B])
        self.assertEqual(len(unknown), 5)

    def test_absent_payload_classifies_reasons(self):
        # No persisted pass/fail split: the gate's own refusal reasons are
        # classified to their condition, and the rest are passes.
        passed, failed, unknown, _ = dt.gate_breakdown({
            "decision": "refuse",
            "checks": [A, B, C, E, F, G, D],
            "reasons": ["behavior_probe_ok=False (no probe proof supplied)"]})
        self.assertEqual(failed, [D])
        self.assertEqual(passed, [A, B, C, E, F, G])
        self.assertEqual(unknown, [])

    def test_unexplained_refuse_never_claims_passes(self):
        passed, failed, unknown, names = dt.gate_breakdown(
            {"decision": "refuse", "checks": list(NAMES), "reasons": []})
        self.assertEqual(passed, [])
        self.assertEqual(failed, [])
        self.assertEqual(unknown, list(NAMES))

    def test_none_gate(self):
        passed, failed, unknown, names = dt.gate_breakdown(None)
        self.assertEqual((passed, failed), ([], []))
        self.assertEqual(len(names), 7)


class StageGateUnit(unittest.TestCase):
    def test_all_pass_complete(self):
        stage = dt._stage_gate({"gate": _gate("complete", NAMES, [])})
        self.assertEqual(stage["status"], "complete")
        self.assertIn("7/7 conditions satisfied", stage["html"])
        self.assertIn("FINAL", stage["html"])
        self.assertIn("COMPLETE", stage["html"])
        self.assertNotIn("✕", stage["html"])

    def test_one_failed_g(self):
        stage = dt._stage_gate({"gate": _gate("refuse", NAMES[:-1], [G])})
        self.assertEqual(stage["status"], "refused")
        self.assertIn("6/7 conditions satisfied", stage["html"])
        self.assertIn("✕", stage["html"])
        self.assertIn("REFUSE", stage["html"])

    def test_multiple_failed(self):
        passed = [A, C, E]
        failed = [B, D, F, G]
        stage = dt._stage_gate({"gate": _gate("refuse", passed, failed)})
        self.assertIn("3/7 conditions satisfied", stage["html"])
        # exactly the failed set is shown as failed
        self.assertEqual(stage["html"].count('class="chk crit"'), 4)
        self.assertEqual(stage["html"].count('class="chk ok"'), 3)
        self.assertIn("REFUSE", stage["html"])

    def test_never_seven_of_seven_when_refuse(self):
        stage = dt._stage_gate({"gate": _gate("refuse", [A, B], [C, D, E, F, G])})
        self.assertNotIn("7/7", stage["html"])
        self.assertIn("REFUSE", stage["html"])

    def test_live_like_payload(self):
        # representative D9.1 live REFUSE: A,E,F,G passed; B,C,D failed.
        stage = dt._stage_gate({"gate": _gate(
            "refuse", [A, E, F, G], [B, C, D])})
        self.assertIn("4/7 conditions satisfied", stage["html"])
        self.assertEqual(stage["html"].count('class="chk crit"'), 3)
        self.assertIn("REFUSE", stage["html"])

    def test_unknown_styling(self):
        gate = {"decision": "refuse", "checks": [A],
                "payload": {"passed": [A], "failed": []}}
        stage = dt._stage_gate({"gate": gate})
        self.assertIn("1/7 conditions satisfied", stage["html"])
        # the six omitted conditions render as unknown (muted '?')
        self.assertEqual(stage["html"].count('class="chk muted"'), 6)
        self.assertIn("?", stage["html"])

    def test_no_gate_is_pending(self):
        stage = dt._stage_gate({"gate": None})
        self.assertEqual(stage["status"], "pending")
        self.assertIn("No Quality Gate record", stage["html"])


class _Scripted:
    def __init__(self, requests):
        self._queue = list(requests)

    def propose(self, context):
        if not self._queue:
            raise DoneSignal("done")
        return self._queue.pop(0)


class IntegrationRendering(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="d92_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(PASSING_TEST, encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs, host="127.0.0.1",
                                     port=0)

    def _mission(self):
        return Mission(
            mission_id="M-d92", description="gate presentation", scope="src/",
            criteria=["defect reproduced", "remediation applied",
                      "verification passed", "falsification survived",
                      "quality gate approval"],
            problem={"symptom_target": "src/cand.txt"})

    def _session(self):
        return api.create_session(mission=self._mission(), workspace_root=self.ws,
                                  sessions_root=self.sessions)

    def _req(self, requester, cap, target, purpose):
        return ActionRequest(sequence=0, requester=requester, capability=cap,
                             target=target, purpose=purpose)

    def _render(self, run_id):
        resp = dispatch(Request(method="GET",
                                path=f"/operations/{run_id}/decision-trace"),
                        self.cfg)
        return resp.status, resp.body

    def _complete_run(self):
        session = self._session()
        requests = [
            self._req("skill:read-file", Capability.READ, "src/cand.txt", "inspect"),
            self._req("skill:run-test", Capability.RUN_TEST, "src/test_ok.py", "tests"),
            self._req("skill:write-file", Capability.WRITE, "src/cand.txt", "content=OK\n"),
        ]
        return run_model_mission(session, self._mission(), self.ws,
                                 runs_root=self.runs, model=_Scripted(requests),
                                 probe=lambda: True, max_turns=6,
                                 sessions_root=self.sessions).run.run_id

    def _refuse_run(self):
        session = self._session()
        requests = [self._req("skill:read-file", Capability.READ,
                              "src/cand.txt", "inspect")]
        return run_model_mission(session, self._mission(), self.ws,
                                 runs_root=self.runs, model=_Scripted(requests),
                                 probe=None, max_turns=2,
                                 sessions_root=self.sessions).run.run_id

    def test_complete_renders_7_7(self):
        run_id = self._complete_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "complete")
        status, html = self._render(run_id)
        self.assertEqual(status, 200)
        self.assertIn("7/7 conditions satisfied", html)
        self.assertIn("COMPLETE", html)

    def test_refuse_never_shows_all_passed(self):
        run_id = self._refuse_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        passed = dt.gate_breakdown(gate)[0]
        self.assertLess(len(passed), 7)
        status, html = self._render(run_id)
        self.assertEqual(status, 200)
        self.assertIn(f"{len(passed)}/7 conditions satisfied", html)
        self.assertIn("REFUSE", html)
        # the misleading all-passed rendering must be gone
        self.assertNotIn("7/7 conditions satisfied", html)
        self.assertIn('class="chk crit"', html)


if __name__ == "__main__":
    unittest.main()
