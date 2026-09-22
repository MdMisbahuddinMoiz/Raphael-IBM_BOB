"""tests.test_d10_2_network_probe — the independent network behavior probe.

D10.2 closes QualityGate condition D for the deterministic HTB network
mission with GENUINE evidence. The probe is a SEPARATE governed HTTP
observation (Runtime -> Broker -> Policy -> NetworkMediator) at a documented
endpoint distinct from the flag request; it asserts an invariant independent
of flag extraction (the authorized endpoint is reachable through the governed
path and serves a well-formed, non-empty response) and is persisted as
``producer="probe"`` with ``payload.allowed is True`` only when it holds.

These eight focused tests map to the D10.2 acceptance list:
    1. successful independent probe -> D PASS
    2. failed network probe          -> D FAIL
    3. missing probe evidence        -> D FAIL
    4. payload.allowed=False         -> D FAIL
    5. primary HTTP evidence alone   -> cannot satisfy D
    6. probe is a separate invocation (distinct identity + sequences)
    7. fabricated behavior_probe_ok=True without evidence -> D FAIL
    8. successful B + C + D (+ A/E/F/G) -> COMPLETE 7/7
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    create_run_dir,
    digest_id,
)
from raphael_ibm_bob.harness.api import create_session
from raphael_ibm_bob.harness.network_run import run_network_mission
from raphael_ibm_bob.network_runtime import NetworkMediator
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile

FLAG = "HTB{deterministic_d102_fixture_flag}"

DEFAULT_ROUTES = {
    "/": (200, b"ok"),
    "/probe": (200, b"independent-probe-endpoint"),
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


class _Base(unittest.TestCase):
    mission_id = "M-HTB-D102"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d102_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n"
            "    def test_ok(self):\n        self.assertTrue(True)\n",
            encoding="utf-8")
        self.sessions = self.tmp / "sessions"
        self.runs = self.tmp / "runs"

    def mission(self, *, request_path="/flag", probe_path="/probe",
                decoy_path="/decoy", tests=("test_ok.py",)):
        problem = {
            "symptom_target": "127.0.0.1", "request_path": request_path,
            "decoy_path": decoy_path, "verification_tests": list(tests),
        }
        if probe_path is not None:
            problem["probe_path"] = probe_path
        return Mission(
            mission_id=self.mission_id,
            description="authorized network validation",
            scope="", criteria=["obtain and verify the flag"],
            problem=problem)

    def declare(self, port):
        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id=self.mission_id, locator="127.0.0.1",
            allowed_ports=[port], allowed_protocols=["http"],
            scope="127.0.0.1", authorization_ref="HTB-AUTHORIZED-D102"))
        return store

    def drive(self, mission, port):
        session = create_session(
            mission=mission, workspace_root=self.ws,
            project_name="d102", sessions_root=self.sessions)
        return run_network_mission(
            session, mission, self.ws, runs_root=self.runs,
            sessions_root=self.sessions, target_store=self.declare(port),
            mediator=NetworkMediator())

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

    def probe_records(self, run_id):
        return self.records(run_id, kind="evidence", producer="probe")

    def gate_failed(self, run_id):
        from raphael_ibm_bob.http.views.decision_trace import gate_breakdown
        gates = self.records(run_id, kind="gate")
        self.assertTrue(gates, "no gate record persisted")
        passed, failed, unknown, names = gate_breakdown(gates[-1])
        return failed


class ProbeConditions(_Base):
    def test_1_successful_probe_passes_D(self):
        with _fixture() as port:
            result = self.drive(self.mission(), port)
            self.assertEqual(result.run.state, "completed")
            self.assertEqual(result.gate_verdict, "complete")
            probes = self.probe_records(result.run.run_id)
            self.assertEqual(len(probes), 1)
            payload = probes[0]["payload"]
            self.assertIs(payload["allowed"], True)
            self.assertEqual(payload["result"], "passed")
            self.assertEqual(payload["status_code"], 200)
            self.assertGreater(payload["response_bytes"], 0)

    def test_2_failed_probe_fails_D(self):
        with _fixture() as port:
            # probe endpoint responds 404 -> probe does not succeed.
            result = self.drive(
                self.mission(probe_path="/does-not-exist"), port)
            self.assertEqual(result.run.state, "refused")
            self.assertIn("D:independent-behavior-probe",
                          self.gate_failed(result.run.run_id))
            self.assertEqual(self.probe_records(result.run.run_id), [])

    def test_3_missing_probe_evidence_fails_D(self):
        with _fixture() as port:
            # probe == primary path -> no independent probe is executed.
            result = self.drive(
                self.mission(request_path="/flag", probe_path="/flag"), port)
            self.assertEqual(result.run.state, "refused")
            self.assertIn("D:independent-behavior-probe",
                          self.gate_failed(result.run.run_id))
            self.assertEqual(self.probe_records(result.run.run_id), [])

    def test_4_probe_allowed_false_fails_D(self):
        """Even with behavior_probe_ok=True, allowed=False cannot satisfy D."""
        _run_id, run_dir = create_run_dir(self.runs)
        ledger = EvidenceLedger(run_dir)
        try:
            payload = {"kind": "probe", "result": "failed", "allowed": False}
            ledger.append_evidence(
                evidence_id=digest_id(payload, prefix="PB"),
                producer="probe", request_seq=0, decision_seq=0,
                result_seq=None, payload=payload)
            mission = Mission(
                mission_id=self.mission_id, description="d",
                scope="", criteria=["c"],
                problem={"symptom_target": "127.0.0.1"})
            evaluation = BOBQualityGate(
                ledger, target_store=TargetStore()).evaluate(GateInputs(
                    mission=mission, findings=[], regression_ok=True,
                    behavior_probe_ok=True))
        finally:
            ledger.close()
        self.assertIn("D:independent-behavior-probe",
                      list(evaluation.failed))

    def test_5_primary_http_evidence_alone_cannot_satisfy_D(self):
        with _fixture() as port:
            result = self.drive(
                self.mission(request_path="/flag", probe_path="/flag"), port)
            run_id = result.run.run_id
            # The primary governed HTTP observation DID execute and persist...
            primary = self.records(run_id, kind="evidence", producer="network")
            self.assertTrue(primary, "primary network evidence missing")
            # ...yet it cannot stand in for the independent probe.
            self.assertEqual(self.probe_records(run_id), [])
            self.assertIn("D:independent-behavior-probe",
                          self.gate_failed(run_id))

    def test_6_probe_is_a_separate_invocation(self):
        with _fixture() as port:
            result = self.drive(self.mission(), port)
            run_id = result.run.run_id
            request_path = "/flag"
            # The primary flag-fetch observation(s) only.
            primary = [
                r for r in self.records(run_id, kind="evidence",
                                        producer="network")
                if ((r.get("payload") or {}).get("network_result") or {}
                    ).get("path") == request_path]
            self.assertTrue(primary, "primary network evidence missing")
            probe = self.probe_records(run_id)[0]
            pl = probe["payload"]
            primary_invocations = {
                (r.get("payload") or {}).get("invocation_id")
                for r in primary}
            primary_request_seqs = {
                (r.get("payload") or {}).get("request_seq") for r in primary}
            self.assertNotIn(pl["invocation_id"], primary_invocations)
            self.assertNotIn(pl["request_seq"], primary_request_seqs)
            self.assertNotEqual(pl["path"], request_path)
            self.assertTrue(
                pl["invocation_id"] and pl["request_seq"] and pl["result_seq"])

    def test_7_fabricated_behavior_probe_ok_fails_D(self):
        _run_id, run_dir = create_run_dir(self.runs)
        ledger = EvidenceLedger(run_dir)
        try:
            mission = Mission(
                mission_id=self.mission_id, description="d",
                scope="", criteria=["c"],
                problem={"symptom_target": "127.0.0.1"})
            evaluation = BOBQualityGate(
                ledger, target_store=TargetStore()).evaluate(GateInputs(
                    mission=mission, findings=[], regression_ok=True,
                    behavior_probe_ok=True))
        finally:
            ledger.close()
        self.assertIn("D:independent-behavior-probe",
                      list(evaluation.failed))

    def test_8_full_evidence_reaches_complete(self):
        with _fixture() as port:
            result = self.drive(self.mission(), port)
            run_id = result.run.run_id
            from raphael_ibm_bob.http.views.decision_trace import (
                gate_breakdown)
            gates = self.records(run_id, kind="gate")
            passed, failed, unknown, names = gate_breakdown(gates[-1])
            self.assertEqual(failed, [])
            self.assertEqual(unknown, [])
            self.assertEqual(len(passed), len(names))
            self.assertEqual(result.run.state, "completed")
            self.assertEqual(result.gate_verdict, "complete")


if __name__ == "__main__":
    unittest.main()
