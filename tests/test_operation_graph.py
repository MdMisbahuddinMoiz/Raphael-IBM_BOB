"""tests.test_operation_graph — M15.10 Operation Graph tests.

The graph is a read-only view of the current (fixed 5-step) task
structure, read through `harness.api`. It must not imply dynamic
branching and must not offer mutation controls.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers import DoneSignal
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig, Request, create_server, dispatch,
)
from raphael_ibm_bob.http.views import operation_graph as og

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
        self.base = Path(tempfile.mkdtemp(prefix="m1510_"))
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

    def mission(self, mid="M-graph"):
        return Mission(mission_id=mid, description="graph mission",
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

    def model_run(self):
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

    def refuted_run(self):
        session = self._session()
        result = run_model_mission(
            session, self.mission(mid="M-refuted"), self.ws,
            runs_root=self.runs,
            model=_Scripted([self._req("skill:write-file", Capability.WRITE,
                                       "src/cand.txt", "content=OK\n")]),
            probe=lambda: False, max_turns=4, sessions_root=self.sessions)
        return result.run.run_id

    def stub_run(self, run_id, state="completed"):
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(run_id=run_id, session_id="s",
                            mission=self.mission(mid="M-stub"),
                            workspace_root=str(self.ws), state=state,
                            ledger_dir=str(run_dir)))
        return run_id

    def stub_replan_run(self, run_id):
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = EvidenceLedger(run_dir)
        ledger.append_evidence(
            evidence_id="RPL-1", producer="replanner", request_seq=0,
            decision_seq=0, result_seq=None,
            payload={"kind": "replan", "parent_plan_id": "P-A",
                     "plan_b_id": "P-B", "refuted_finding_id": "F-1"},
            finding_id="F-1")
        ledger.close()
        save_run(RaphaelRun(run_id=run_id, session_id="s",
                            mission=self.mission(mid="M-replan"),
                            workspace_root=str(self.ws), state="refused",
                            ledger_dir=str(run_dir)))
        return run_id

    def render(self, run_id=None):
        query = {"run": [run_id]} if run_id else {}
        response = dispatch(Request(method="GET", path="/operations/graph",
                                    query=query), self.cfg)
        return response.status, response.content_type, response.body


class Render(_Case):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Operation Graph", html)

    def test_B_empty_state(self):
        status, _, html = self.render()
        self.assertEqual(status, 200)
        self.assertIn("No Harness-managed operations", html)

    def test_C_real_run_renders(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        self.assertIn(run_id, html)
        self.assertIn("Operation Graph", html)

    def test_D_real_mission_renders(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        self.assertIn("M-graph", html)
        self.assertIn("graph mission", html)

    def test_E_real_tasks_render(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        for step in ("investigate", "reproduce", "remediate", "verify",
                     "validate"):
            self.assertIn(step, html)

    def test_F_task_ids_real(self):
        run_id = self.model_run()
        tasks = api.get_tasks(run_id, self.runs)
        _, _, html = self.render(run_id)
        for task in tasks["root"]["subtasks"]:
            self.assertIn(task["task_id"], html)

    def test_G_task_state_real(self):
        run_id = self.model_run()
        tasks = api.get_tasks(run_id, self.runs)
        _, _, html = self.render(run_id)
        for task in tasks["root"]["subtasks"]:
            state = tasks["states"][task["task_id"]].upper()
            self.assertIn(state, html)
        self.assertIn("PERSISTED (runs/", html)

    def test_H_task_role_real(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        for role in ("investigator", "test_analyst", "remediation_planner",
                     "verifier", "evidence_analyst"):
            self.assertIn(role, html)

    def test_I_task_skill_real(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        for skill in ("read-file", "run-test", "write-file"):
            self.assertIn(skill, html)

    def test_J_task_capability_derived(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        self.assertIn("CAPABILITY (DERIVED FROM SKILL)", html)
        for cap in ("read", "run_test", "write"):
            self.assertIn(cap, html)

    def test_K_no_fabricated_edges(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        # per-task target/purpose/evidence are not persisted -> UNKNOWN
        self.assertIn("not persisted per task", html)
        # no claim of dynamic branching
        self.assertIn("NO DYNAMIC BRANCHING", html)
        self.assertNotIn("autonomous graph", html.lower())
        self.assertNotIn("adaptive graph", html.lower())

    def test_L_replan_edge_only_when_authoritative(self):
        # Negative: a refuted run with no replanner evidence says so.
        refuted = self.refuted_run()
        _, _, html = self.render(refuted)
        self.assertIn("NO REFUTATION/REPLAN RECORD", html)
        # Positive: a persisted replanner record is shown.
        replan = self.stub_replan_run("run-replan-1")
        _, _, html2 = self.render(replan)
        self.assertIn("P-A", html2)
        self.assertIn("P-B", html2)
        self.assertNotIn("NO REFUTATION/REPLAN RECORD", html2)

    def test_M_gate_relationship_real(self):
        run_id = self.model_run()
        gate = api.get_gate(run_id, self.runs)
        _, _, html = self.render(run_id)
        self.assertIn("GATE: " + gate["decision"].upper(), html)

    def test_N_evidence_finding_links_real(self):
        run_id = self.model_run()
        records = api.get_evidence(run_id, self.runs)
        findings = [r.get("finding_id") for r in records
                    if r.get("finding_id")]
        _, _, html = self.render(run_id)
        for fid in findings:
            self.assertIn(fid, html)
        self.assertIn('href="/operations/evidence"', html)
        self.assertIn('href="/operations/findings"', html)

    def test_O_multi_run_selection(self):
        persisted = self.model_run()
        derived = self.stub_run("run-derby-1")
        _, _, html_default = self.render()
        self.assertIn("/operations/graph?run=", html_default)
        _, _, html_derived = self.render(derived)
        self.assertIn("DERIVED (decompose_mission", html_derived)
        _, _, html_persisted = self.render(persisted)
        self.assertIn("PERSISTED (runs/", html_persisted)

    def test_P_search_filter(self):
        run_id = self.model_run()
        _, _, html = self.render(run_id)
        self.assertIn('id="search"', html)
        self.assertIn("data-search=", html)
        self.assertIn("graph-tasks", html)

    def test_Q_fixed_pipeline_disclosed(self):
        self.model_run()
        _, _, html = self.render()
        self.assertIn("FIXED TASK PIPELINE", html)
        self.assertIn("FIXED 5-STEP PIPELINE", html)
        self.assertIn("derived from the mission", html)


class Safety(_Case):
    def test_R_no_graph_mutation_controls(self):
        self.model_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        for control in (">ADD TASK<", ">REPLAN<", ">APPROVE<", ">CANCEL TASK<",
                        ">DELETE<", ">EDIT<"):
            self.assertNotIn(control, html, control)

    def test_S_no_execution_controls(self):
        self.model_run()
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn(">EXECUTE<", html)
        self.assertNotIn("execute_capability", html)
        self.assertNotIn("operations/start", html)

    def test_T_no_credentials(self):
        self.model_run()
        _, _, html = self.render()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html.lower())
        self.assertNotIn("authorization:", html.lower())

    def test_U_governance_static(self):
        root = Path(og.__file__).resolve().parents[2]
        view = (root / "http" / "views" / "operation_graph.py").read_text("utf-8")
        route = (root / "http" / "routes" / "graph.py").read_text("utf-8")
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
    def test_V_command_center(self):
        r = dispatch(Request(method="GET", path="/command"), self.cfg)
        self.assertEqual(r.status, 200)
        self.assertIn("/operations/graph", r.body)

    def test_W_findings(self):
        r = dispatch(Request(method="GET", path="/operations/findings"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_X_evidence(self):
        r = dispatch(Request(method="GET", path="/operations/evidence"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_Y_gate(self):
        r = dispatch(Request(method="GET", path="/operations/gate"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_Z_capabilities(self):
        r = dispatch(Request(method="GET",
                             path="/operations/capabilities"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_AA_decision_trace(self):
        run_id = self.model_run()
        r = dispatch(Request(
            method="GET", path=f"/operations/{run_id}/decision-trace"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_AB_event_stream(self):
        run_id = self.model_run()
        r = dispatch(Request(
            method="GET", path=f"/operations/{run_id}/events"), self.cfg)
        self.assertEqual(r.status, 200)

    def test_served_over_http(self):
        import http.client
        run_id = self.model_run()
        server = create_server(self.cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", f"/operations/graph?run={run_id}")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Operation Graph", body)


if __name__ == "__main__":
    unittest.main()
