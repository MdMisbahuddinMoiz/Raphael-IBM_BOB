"""tests.test_m15_3_decision_trace — M15.3 Decision Trace screen tests.

The screen is presentation-only: it renders observable, persisted
decision/evidence data through `harness.api`. These tests use the real
governed stack (scripted model + real broker/policy/verifier/falsifier/
gate) and assert on the rendered HTML.
"""
from __future__ import annotations

import http.client
import json
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
    RaphaelHTTPConfig,
    Request,
    create_server,
    dispatch,
)
from raphael_ibm_bob.http.views import decision_trace as dt

PASSING_TEST = (
    "import unittest\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_ok(self):\n"
    "        self.assertTrue(True)\n"
)


class _Scripted:
    """Deterministic model double: returns queued proposals, then done."""

    def __init__(self, requests):
        self._queue = list(requests)

    def propose(self, context):
        if not self._queue:
            raise DoneSignal("done")
        return self._queue.pop(0)


class _TraceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m153_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(
            PASSING_TEST, encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            host="127.0.0.1", port=0)

    # --- fixtures -------------------------------------------------------

    def mission(self) -> Mission:
        return Mission(
            mission_id="M-dt", description="Trace the governed fix",
            scope="src/",
            criteria=["defect reproduced", "remediation applied",
                      "verification passed", "falsification survived",
                      "quality gate approval"],
            problem={"symptom_target": "src/cand.txt"})

    def _session(self):
        return api.create_session(
            mission=self.mission(), workspace_root=self.ws,
            sessions_root=self.sessions, model="stub-model",
            provider="stub-provider")

    def _req(self, requester, capability, target, purpose):
        return ActionRequest(sequence=0, requester=requester,
                             capability=capability, target=target,
                             purpose=purpose)

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
        return result.run.run_id, result

    def deny_run(self):
        session = self._session()
        requests = [self._req("skill:read-file", Capability.READ,
                              "/etc/hostname", "escape")]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=None, max_turns=3,
            sessions_root=self.sessions)
        return result.run.run_id, result

    def refuted_run(self):
        session = self._session()
        requests = [self._req("skill:write-file", Capability.WRITE,
                              "src/cand.txt", "content=OK\n")]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=lambda: False, max_turns=4,
            sessions_root=self.sessions)
        return result.run.run_id, result

    def render(self, run_id):
        response = dispatch(
            Request(method="GET",
                    path=f"/operations/{run_id}/decision-trace"), self.cfg)
        return response.status, response.content_type, response.body


class CompleteRunRenders(_TraceCase):
    def test_complete_run_renders_complete(self):
        run_id, result = self.complete_run()
        self.assertEqual(result.gate_verdict, "complete")
        status, ctype, html = self.render(run_id)
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn("Decision Trace", html)
        self.assertIn("COMPLETE", html)
        self.assertIn("7/7 conditions satisfied", html)
        self.assertIn("QUALITY GATE", html)

    def test_pipeline_present(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        for phase in ("INVESTIGATE", "REPRODUCE", "REMEDIATE", "VERIFY",
                      "FALSIFY", "INDEPENDENT PROBE", "QUALITY GATE"):
            self.assertIn(phase, html)

    def test_evidence_ids_correspond_to_real_evidence(self):
        run_id, _ = self.complete_run()
        records = api.get_evidence(run_id, self.runs)
        ids = [r.get("evidence_id") for r in records
               if r.get("kind") == "evidence" and r.get("evidence_id")]
        self.assertTrue(ids)
        _, _, html = self.render(run_id)
        for evidence_id in ids:
            self.assertIn(evidence_id, html)

    def test_gate_conditions_correspond_to_gate_record(self):
        run_id, _ = self.complete_run()
        gate = api.get_gate(run_id, self.runs)
        _, _, html = self.render(run_id)
        for condition in gate["checks"]:
            self.assertIn(condition, html)

    def test_specialist_authority_note(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn("SPECIALIST SELECTION", html)
        self.assertIn("ROLE ≠ PERMISSION", html)
        self.assertIn("remediation_planner", html)
        self.assertIn("investigator", html)

    def test_bob_control_plane_prominent(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        for token in ("IBM BOB CONTROL PLANE", "BOB RUNTIME", "BOB BROKER",
                      "BOB POLICY", "ALLOW", "EXECUTION"):
            self.assertIn(token, html)

    def test_model_proposal_is_observable_only(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn("MODEL PROPOSAL", html)
        self.assertIn("Only the structured, submitted proposal is shown",
                      html)

    def test_no_chain_of_thought(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        for forbidden in ("chain of thought", "chain-of-thought",
                          "scratchpad", "thought process", "<thinking",
                          "internal monologue"):
            self.assertNotIn(forbidden, html.lower())


class RefuseRunRenders(_TraceCase):
    def test_deny_policy_renders_deny(self):
        run_id, result = self.deny_run()
        self.assertEqual(result.gate_verdict, "refuse")
        status, _, html = self.render(run_id)
        self.assertEqual(status, 200)
        self.assertIn("DENY", html)
        self.assertIn("REFUSE", html)

    def test_probe_absent_is_not_run(self):
        run_id, _ = self.deny_run()
        _, _, html = self.render(run_id)
        self.assertIn("NOT RUN", html)

    def test_refuted_finding_is_shown(self):
        run_id, result = self.refuted_run()
        self.assertEqual(result.gate_verdict, "refuse")
        _, _, html = self.render(run_id)
        self.assertIn("REFUTATION", html)
        self.assertIn("FOUND", html)

    def test_no_replan_renders_not_triggered(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn("Not triggered", html)


class StageUnitTests(unittest.TestCase):
    """Edge cases rendered directly (presentation logic only)."""

    def test_replan_present(self):
        stage = dt._stage_replan({
            "replans": [{"seq": 9, "parent_plan_id": "P-A",
                         "plan_b_id": "P-B", "refuted_finding_id": "F-1"}],
            "findings": []})
        self.assertEqual(stage["status"], "active")
        self.assertIn("P-B", stage["html"])

    def test_replan_absent_clean(self):
        stage = dt._stage_replan({"replans": [],
                                  "findings": [{"state": "verified"}]})
        self.assertIn("Not triggered", stage["html"])
        self.assertEqual(stage["status"], "info")

    def test_replan_absent_with_refuted_flag(self):
        stage = dt._stage_replan({"replans": [],
                                  "findings": [{"state": "refuted"}]})
        self.assertEqual(stage["status"], "attention")

    def test_probe_absent_is_notrun(self):
        stage = dt._stage_probe({"evidence": []})
        self.assertEqual(stage["status"], "notrun")
        self.assertIn("NOT RUN", stage["html"])

    def test_probe_pass(self):
        stage = dt._stage_probe({"evidence": [
            {"evidence_id": "E9", "producer": "probe",
             "payload": {"kind": "probe", "allowed": True}}]})
        self.assertEqual(stage["status"], "complete")
        self.assertIn("PASS", stage["html"])

    def test_gate_refuse_counts(self):
        stage = dt._stage_gate({"gate": {
            "decision": "refuse",
            "checks": ["A:mission-criterion", "B:required-tests",
                       "C:regression", "E:scope", "F:evidence",
                       "G:finding-state"],
            "reasons": ["behavior_probe_ok=False"]}})
        self.assertEqual(stage["status"], "refused")
        self.assertIn("6/7 conditions satisfied", stage["html"])
        self.assertIn("✕", stage["html"])


class Governance(_TraceCase):
    def test_route_and_view_use_harness_api_only(self):
        root = Path(dt.__file__).resolve().parents[2]
        sources = {
            "routes/operations.py": (root / "http" / "routes" /
                                     "operations.py").read_text("utf-8"),
            "views/decision_trace.py": (root / "http" / "views" /
                                        "decision_trace.py").read_text("utf-8"),
        }
        for name, src in sources.items():
            self.assertIn("harness import api", src, name)
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal"):
                self.assertNotIn(token, src, f"{token} in {name}")

    def test_render_is_read_only(self):
        run_id, _ = self.complete_run()
        before = len(api.get_evidence(run_id, self.runs))
        status, _, _ = self.render(run_id)
        self.assertEqual(status, 200)
        after = len(api.get_evidence(run_id, self.runs))
        self.assertEqual(before, after)

    def test_missing_run_is_404(self):
        status, _, body = self.render("does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "RUN_NOT_FOUND")

    def test_served_over_http_as_html(self):
        run_id, _ = self.complete_run()
        server = create_server(self.cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", f"/operations/{run_id}/decision-trace")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Decision Trace", body)


if __name__ == "__main__":
    unittest.main()
