"""tests.test_d10_1_network_gate — D10.1 real B/C/D evidence tests.

Proves the deterministic HTB network mission produces the REAL,
ledger-backed evidence the existing QualityGate conditions demand:

    B  a governed RUN_TEST whose artifact reports returncode 0
    C  a producer="regression" record causally tied to that RUN_TEST
       plus >=2 distinct ALLOWed capabilities
    D  a SEPARATE governed behavior probe recorded as producer="probe"
       with allowed=True

It also proves the negative: booleans alone (regression_ok=True /
behavior_probe_ok=True) can never satisfy the gate without the matching
records, and a missing/failing test or a missing/erroring probe fails the
corresponding condition.

Deterministic and offline: the REAL HTTP app (`/operations/start`) runs with
product mode TESTING/HTB against a local stdlib HTTP fixture.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, create_run_dir
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    dispatch,
)
from raphael_ibm_bob.http.views.decision_trace import gate_breakdown
from raphael_ibm_bob.mode import Mode, ModeManager
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.target_profile import TargetStore

FLAG = "HTB{deterministic_d101_fixture_flag}"

DEFAULT_ROUTES = {
    "/": (200, b"ok"),
    "/flag": (200, f"welcome {FLAG}".encode()),
    "/verify": (200, f"confirmed {FLAG}".encode()),
    "/decoy": (200, b"nothing here"),
}


class _Handler(BaseHTTPRequestHandler):
    routes = DEFAULT_ROUTES

    def log_message(self, *args):
        pass

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        entry = self.routes.get(path)
        if entry is None:
            self._send(404, b"nope")
        else:
            self._send(*entry)


@contextmanager
def _fixture(routes=None):
    prev = _Handler.routes
    _Handler.routes = routes if routes is not None else DEFAULT_ROUTES
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        _Handler.routes = prev


class _StubVPN:
    def status(self):
        return {"state": "disconnected", "history": []}

    def connect(self, *a, **k):
        return self.status()

    def disconnect(self):
        return self.status()


class _Base(unittest.TestCase):
    mission_id = "M-HTB-001"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d101_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        self.write_test("test_ok.py", ok=True)
        self.sessions = self.tmp / "sessions"
        self.runs = self.tmp / "runs"
        self.mode = ModeManager()
        self.mode.set(Mode.TESTING, "htb")
        self.store = TargetStore()
        self.cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            mode_manager=self.mode, target_store=self.store,
            vpn_manager=_StubVPN())
        self.router = build_router()

    def write_test(self, name, ok=True):
        body = "assertTrue(True)" if ok else "assertTrue(False, 'boom')"
        (self.ws / name).write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            f"    def test_x(self):\n        self.{body}\n",
            encoding="utf-8")

    def call(self, method, path, body=None):
        return dispatch(Request(method=method, path=path, body=body),
                        self.cfg, self.router)

    def problem(self, *, request_path="/flag", probe_path=None,
                decoy_path=None, tests=None):
        problem = {"symptom_target": "127.0.0.1", "request_path": request_path}
        if probe_path is not None:
            problem["probe_path"] = probe_path
        if decoy_path is not None:
            problem["decoy_path"] = decoy_path
        if tests is not None:
            problem["verification_tests"] = list(tests)
        return problem

    def new_session(self, problem):
        mission = {
            "mission_id": self.mission_id,
            "description": "authorized HTB network validation",
            "scope": "", "criteria": ["obtain and verify the flag"],
            "problem": problem,
        }
        resp = self.call("POST", "/sessions", {
            "workspace_root": str(self.ws), "project_name": "htb",
            "mission": mission})
        self.assertEqual(resp.status, 201, resp.body)
        return resp.body["session_id"]

    def declare_target(self, port, locator="127.0.0.1"):
        resp = self.call("POST", "/htb/target", {
            "platform": "htb", "locator": locator, "allowed_ports": [port],
            "allowed_protocols": ["http"], "scope": locator,
            "authorization_ref": "HTB-AUTHORIZED-D101",
            "mission_id": self.mission_id})
        self.assertEqual(resp.status, 201, resp.body)

    def start(self, session_id):
        return self.call("POST", "/operations/start",
                         {"session_id": session_id})

    def run_id_from(self, html):
        match = re.search(r"/operations/([0-9T]+_[0-9a-f]+)", html)
        self.assertIsNotNone(match, html[:200])
        return match.group(1)

    def ledger(self, run_id):
        path = self.runs / run_id / "evidence.jsonl"
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def records(self, run_id, kind=None, producer=None, capability=None):
        out = []
        for r in self.ledger(run_id):
            if kind is not None and r.get("kind") != kind:
                continue
            if producer is not None and r.get("producer") != producer:
                continue
            if capability is not None and r.get("capability") != capability:
                continue
            out.append(r)
        return out

    def breakdown(self, run_id):
        gates = self.records(run_id, kind="gate")
        self.assertTrue(gates, "no gate record persisted")
        return gate_breakdown(gates[-1])

    def completed_run(self, run_id):
        return json.loads((self.runs / run_id / "harness.json").read_text())


class RealEvidence(_Base):
    def test_all_real_evidence_reaches_7_of_7(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/", decoy_path="/decoy",
                tests=["test_ok.py"]))
            run_id = self.run_id_from(self.start(sid).body)

            harness = self.completed_run(run_id)
            self.assertEqual(harness["state"], "completed")
            self.assertEqual(harness["gate_verdict"], "complete")

            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertEqual(len(passed), len(names), (passed, failed, unknown))
            self.assertEqual(failed, [])
            self.assertEqual(unknown, [])

            # Two distinct governed HTTP invocations: flag fetch + probe.
            net = self.records(run_id, kind="request",
                               capability="network_http_request")
            self.assertGreaterEqual(len(net), 2)
            # B: a governed RUN_TEST request AND a returncode-0 artifact.
            run_tests = self.records(run_id, kind="request",
                                     capability="run_test")
            self.assertEqual(len(run_tests), 1)
            self.assertTrue(str(run_tests[0]["target"]).endswith("test_ok.py"))
            arts = list((self.runs / run_id / "artifacts").glob("*.json"))
            self.assertTrue(any(json.loads(p.read_text()).get("evidence", {})
                                .get("returncode") == 0 for p in arts))
            # C: exactly one causal regression record.
            reg = self.records(run_id, kind="evidence", producer="regression")
            self.assertEqual(len(reg), 1)
            self.assertEqual(reg[0]["payload"]["result"], "passed")
            self.assertEqual(reg[0]["payload"]["test"], "test_ok.py")
            self.assertIn("request_seq", reg[0]["payload"])
            self.assertIn("result_seq", reg[0]["payload"])
            # D: exactly one independent probe record, allowed=True.
            probe = self.records(run_id, kind="evidence", producer="probe")
            self.assertEqual(len(probe), 1)
            self.assertTrue(probe[0]["payload"]["allowed"])
            self.assertEqual(probe[0]["payload"]["status_code"], 200)
            self.assertTrue(probe[0]["payload"]["response_sha256"])
            self.assertIn("request_seq", probe[0]["payload"])

    def test_missing_required_tests_fails_B_and_C(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/"))
            run_id = self.run_id_from(self.start(sid).body)

            harness = self.completed_run(run_id)
            self.assertEqual(harness["state"], "refused")
            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertTrue(any(c.startswith("B:") for c in failed), failed)
            self.assertTrue(any(c.startswith("C:") for c in failed), failed)
            self.assertFalse(any(c.startswith("D:") for c in failed), failed)
            # no RUN_TEST was ever submitted, and no regression claimed.
            self.assertEqual(self.records(run_id, kind="request",
                                          capability="run_test"), [])
            self.assertEqual(self.records(run_id, kind="evidence",
                                          producer="regression"), [])

    def test_failing_required_test_fails_B_and_C(self):
        self.write_test("test_fail.py", ok=False)
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/",
                tests=["test_fail.py"]))
            run_id = self.run_id_from(self.start(sid).body)

            self.assertEqual(self.completed_run(run_id)["state"], "refused")
            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertTrue(any(c.startswith("B:") for c in failed), failed)
            self.assertTrue(any(c.startswith("C:") for c in failed), failed)
            # the test really ran (a result exists) but failed -> no regression.
            self.assertEqual(self.records(run_id, kind="request",
                                          capability="run_test") != [], True)
            self.assertEqual(self.records(run_id, kind="evidence",
                                          producer="regression"), [])

    def test_denied_run_test_cannot_satisfy_B(self):
        self.write_test("notatest.py", ok=True)
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/",
                tests=["notatest.py"]))
            run_id = self.run_id_from(self.start(sid).body)

            self.assertEqual(self.completed_run(run_id)["state"], "refused")
            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertTrue(any(c.startswith("B:") for c in failed), failed)
            # the RUN_TEST was DENIED by policy: no ALLOW, no regression.
            rt = self.records(run_id, kind="request", capability="run_test")
            self.assertEqual(len(rt), 1)
            decisions = [r for r in self.records(run_id, kind="decision")
                         if r.get("request_seq") == rt[0]["seq"]]
            self.assertTrue(decisions)
            self.assertEqual(decisions[-1]["decision"], "deny")
            self.assertEqual(self.records(run_id, kind="evidence",
                                          producer="regression"), [])

    def test_probe_path_equal_request_path_fails_D(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/flag",
                tests=["test_ok.py"]))
            run_id = self.run_id_from(self.start(sid).body)

            self.assertEqual(self.completed_run(run_id)["state"], "refused")
            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertTrue(any(c.startswith("D:") for c in failed), failed)
            self.assertFalse(any(c.startswith("B:") for c in failed), failed)
            self.assertFalse(any(c.startswith("C:") for c in failed), failed)
            self.assertEqual(self.records(run_id, kind="evidence",
                                          producer="probe"), [])

    def test_probe_error_response_fails_D(self):
        with _fixture() as port:
            self.declare_target(port)
            sid = self.new_session(self.problem(
                request_path="/flag", probe_path="/missing",
                tests=["test_ok.py"]))
            run_id = self.run_id_from(self.start(sid).body)

            self.assertEqual(self.completed_run(run_id)["state"], "refused")
            passed, failed, unknown, names = self.breakdown(run_id)
            self.assertTrue(any(c.startswith("D:") for c in failed), failed)
            self.assertEqual(self.records(run_id, kind="evidence",
                                          producer="probe"), [])


class FabricatedBooleans(unittest.TestCase):
    """The gate must never accept a boolean without its evidence record."""

    def test_booleans_without_records_refuse(self):
        tmp = Path(tempfile.mkdtemp(prefix="d101f_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        runs = tmp / "runs"
        _run_id, run_dir = create_run_dir(runs)
        ledger = EvidenceLedger(run_dir)
        try:
            gate = BOBQualityGate(ledger, target_store=TargetStore())
            mission = Mission(
                mission_id="M-HTB-001", description="fabrication probe",
                scope="", criteria=["obtain and verify the flag"],
                problem={"symptom_target": "127.0.0.1"})
            evaluation = gate.evaluate(GateInputs(
                mission=mission, findings=[], regression_ok=True,
                behavior_probe_ok=True))
        finally:
            ledger.close()
        self.assertEqual(evaluation.verdict.value, "refuse")
        failed = list(evaluation.failed)
        self.assertTrue(any(c.startswith("B:") for c in failed), failed)
        self.assertTrue(any(c.startswith("C:") for c in failed), failed)
        self.assertTrue(any(c.startswith("D:") for c in failed), failed)


if __name__ == "__main__":
    unittest.main()
