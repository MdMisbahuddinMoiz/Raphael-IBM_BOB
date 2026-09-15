"""tests.test_m15_4_live_stream — M15.4 live event stream + controls.

Exercises the real SSE route, the real event projection, the real
operator controls, and the real Harness. No fake SSE simulation.
"""
from __future__ import annotations

import http.client
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers import DoneSignal
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    create_server,
    dispatch,
)
from raphael_ibm_bob.http.views import decision_trace as dt
from raphael_ibm_bob.http.views import event_stream as es

PASSING_TEST = (
    "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_ok(self):\n        self.assertTrue(True)\n"
)


class _Scripted:
    def __init__(self, requests, delay=0.0):
        self._queue = list(requests)
        self._delay = delay

    def propose(self, context):
        if self._delay:
            time.sleep(self._delay)
        if not self._queue:
            raise DoneSignal("done")
        return self._queue.pop(0)


class _LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m154_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(PASSING_TEST,
                                                     encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs,
                                     host="127.0.0.1", port=0)
        self.server = create_server(self.cfg)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    # --- helpers --------------------------------------------------------

    def mission(self):
        return Mission(mission_id="M-live", description="live console",
                       scope="src/", criteria=["recover", "verified"],
                       problem={"symptom_target": "src/cand.txt"})

    def _route_map(self):
        return {
            "skill:read-file": (Capability.READ, "src/cand.txt", "inspect"),
            "skill:run-test": (Capability.RUN_TEST, "src/test_ok.py", "run"),
            "skill:write-file": (Capability.WRITE, "src/cand.txt",
                                 "content=OK\n"),
        }

    def _req(self, requester):
        cap, target, purpose = self._route_map()[requester]
        return ActionRequest(sequence=0, requester=requester,
                             capability=cap, target=target, purpose=purpose)

    def _session(self):
        return api.create_session(mission=self.mission(),
                                  workspace_root=self.ws,
                                  sessions_root=self.sessions,
                                  model="stub-model",
                                  provider="stub-provider")

    def complete_run(self):
        session = self._session()
        slow = _Scripted([self._req("skill:read-file"),
                          self._req("skill:run-test"),
                          self._req("skill:write-file")])
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=slow, probe=lambda: True, max_turns=6,
            sessions_root=self.sessions)
        return result.run.run_id

    def deny_run(self):
        session = self._session()
        requests = [ActionRequest(sequence=0, requester="skill:read-file",
                                  capability=Capability.READ,
                                  target="/etc/hostname", purpose="escape")]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=None, max_turns=3,
            sessions_root=self.sessions)
        return result.run.run_id

    def stub_run(self, run_id, state):
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(run_id=run_id, session_id="s",
                            mission=self.mission(),
                            workspace_root=str(self.ws), state=state,
                            ledger_dir=str(run_dir)))
        return run_id

    def http(self, method, path, form=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = dict(headers or {})
        payload = None
        if form is not None:
            payload = "&".join(f"{k}={v}" for k, v in form.items())
            h["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body=payload, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        ctype = resp.getheader("Content-Type")
        conn.close()
        return resp.status, ctype, data

    def page(self, path):
        status = dispatch(Request(method="GET", path=path), self.cfg)
        return status.status, (status.body if isinstance(status.body, str)
                               else "")


class SseEndpoint(_LiveCase):
    def test_A_sse_endpoint_exists(self):
        run_id = self.complete_run()
        status, ctype, _ = self.http(
            "GET", f"/runs/{run_id}/events/stream")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/event-stream"), ctype)

    def test_B_emits_persisted_events(self):
        run_id = self.complete_run()
        events = api.get_events(run_id, self.runs)
        frames = list(es.iter_frames(run_id, runs_root=self.runs))
        emitted = [f for f in frames if f.startswith(b"event: RAPHAEL_EVENT")]
        self.assertEqual(len(emitted), len(events))

    def test_C_deterministic_ordering(self):
        run_id = self.complete_run()
        frames = list(es.iter_frames(run_id, runs_root=self.runs))
        ids = [int(line.split(b": ")[1]) for f in frames
               for line in f.split(b"\n") if line.startswith(b"id: ")]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))
        again = [int(line.split(b": ")[1]) for f in
                 list(es.iter_frames(run_id, runs_root=self.runs))
                 for line in f.split(b"\n") if line.startswith(b"id: ")]
        self.assertEqual(ids, again)

    def test_D_replay_cursor(self):
        run_id = self.complete_run()
        full = list(es.iter_frames(run_id, runs_root=self.runs))
        ids = [int(l.split(b": ")[1]) for f in full
               for l in f.split(b"\n") if l.startswith(b"id: ")]
        resumed = list(es.iter_frames(run_id, runs_root=self.runs, after=3))
        rids = [int(l.split(b": ")[1]) for f in resumed
                for l in f.split(b"\n") if l.startswith(b"id: ")]
        self.assertEqual(rids[0], 4)
        self.assertEqual(rids, ids[3:])
        # HTTP cursor forms.
        status, _, body = self.http(
            "GET", f"/runs/{run_id}/events/stream?after=3")
        self.assertIn(b'id: 4', body)
        self.assertNotIn(b'id: 3\n', body)
        status, _, body = self.http(
            "GET", f"/runs/{run_id}/events/stream",
            headers={"Last-Event-ID": "5"})
        self.assertIn(b'id: 6', body)

    def test_E_terminal_closes_stream(self):
        run_id = self.complete_run()
        frames = list(es.iter_frames(run_id, runs_root=self.runs))
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))
        self.assertIn(b'"state": "completed"', frames[-1])

    def test_F_bounded_and_disconnect(self):
        # Bounded: an injected clock advances past max_seconds.
        run_id = self.stub_run("run-pending-1", "pending")
        ticks = iter([0.0, 0.5, 2.0, 9.0])

        def clock():
            return next(ticks, 9.0)

        frames = list(es.iter_frames(
            run_id, runs_root=self.runs, poll_seconds=0.0,
            max_seconds=1.0, heartbeat_seconds=99.0,
            clock=clock, sleep=lambda _s: None))
        self.assertTrue(any(b"stream-timeout" in f for f in frames))
        # Disconnect: a write error stops the pump immediately.
        class Boom(Exception):
            pass

        def pump(write):
            for frame in es.iter_frames(run_id, runs_root=self.runs,
                                        poll_seconds=0.0, max_seconds=1.0,
                                        clock=clock, sleep=lambda _s: None):
                write(frame)

        with self.assertRaises(Boom):
            pump(lambda _chunk: (_ for _ in ()).throw(Boom()))

    def test_G_missing_run_404(self):
        status, _, body = self.http(
            "GET", "/runs/nope/events/stream")
        self.assertEqual(status, 404)
        self.assertIn(b"RUN_NOT_FOUND", body)


class AuthAndSecrets(_LiveCase):
    def test_H_auth_enforced(self):
        cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                runs_root=self.runs, host="127.0.0.1",
                                port=0, api_key="sk-stream-secret")
        server = create_server(cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        run_id = self.complete_run()

        def get(headers):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            conn.request("GET", f"/runs/{run_id}/events/stream",
                         headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            return resp.status, body

        status, body = get(None)
        self.assertEqual(status, 401)
        status, _ = get({"X-API-Key": "sk-stream-secret"})
        self.assertEqual(status, 200)

    def test_I_no_secret_leakage(self):
        run_id = self.complete_run()
        frames = b"".join(es.iter_frames(run_id, runs_root=self.runs))
        self.assertNotIn(b"sk-", frames)
        _, console = self.page(f"/operations/{run_id}")
        self.assertNotIn("sk-", console)

    def test_J_no_hidden_reasoning(self):
        run_id = self.complete_run()
        blob = b"".join(es.iter_frames(run_id, runs_root=self.runs)).lower()
        for token in (b"chain of thought", b"chain-of-thought",
                      b"scratchpad", b"thinking"):
            self.assertNotIn(token, blob)
        _, console = self.page(f"/operations/{run_id}")
        for token in ("chain of thought", "chain-of-thought", "scratchpad",
                      "thinking"):
            self.assertNotIn(token, console.lower())


class LiveState(_LiveCase):
    def test_K_pipeline_updates(self):
        run_id = self.complete_run()
        data = dt.collect(run_id, runs_root=self.runs,
                          sessions_root=self.sessions)
        phases = dict(dt._pipeline(data))
        self.assertEqual(phases["REMEDIATE"], "complete")
        self.assertEqual(phases["QUALITY GATE"], "complete")
        _, console = self.page(f"/operations/{run_id}")
        for label in ("INVESTIGATE", "REPRODUCE", "REMEDIATE", "VERIFY",
                      "FALSIFY", "INDEPENDENT PROBE", "QUALITY GATE"):
            self.assertIn(f'data-phase="{label}"', console)

    def test_L_policy_allow(self):
        run_id = self.complete_run()
        frames = b"".join(es.iter_frames(run_id, runs_root=self.runs))
        self.assertIn(b'"decision": "allow"', frames)
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn("IBM BOB CONTROL PLANE", console)
        self.assertIn("ALLOW", console)

    def test_M_policy_deny(self):
        run_id = self.deny_run()
        frames = b"".join(es.iter_frames(run_id, runs_root=self.runs))
        self.assertIn(b'"decision": "deny"', frames)
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn("DENY", console)

    def test_N_gate_in_progress_before_decision(self):
        stage = dt._stage_gate({"gate": None})
        self.assertEqual(stage["status"], "pending")
        run_id = self.stub_run("run-running-1", "running")
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn('data-phase="QUALITY GATE"', console)
        self.assertNotIn(">COMPLETE<", console)

    def test_O_complete_only_after_gate_record(self):
        run_id = self.complete_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "complete")
        stage = dt._stage_gate({"gate": gate})
        self.assertEqual(stage["status"], "complete")
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn('class="gate-final">COMPLETE', console)

    def test_P_refuse_rendered(self):
        run_id = self.deny_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn('class="gate-final">REFUSE', console)


class Controls(_LiveCase):
    def test_Q_cancel_pending(self):
        run_id = self.stub_run("run-pending-2", "pending")
        status, ctype, body = self.http(
            "POST", f"/operations/{run_id}/cancel")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertEqual(api.get_run(run_id, self.runs).state, "cancelled")

    def test_R_terminal_cannot_cancel(self):
        run_id = self.complete_run()
        before = api.get_run(run_id, self.runs).state
        status, _, _ = self.http("POST", f"/operations/{run_id}/cancel")
        self.assertEqual(status, 200)
        self.assertEqual(api.get_run(run_id, self.runs).state, before)

    def test_S_running_represented_honestly(self):
        run_id = self.stub_run("run-running-2", "running")
        _, console = self.page(f"/operations/{run_id}")
        self.assertIn("cannot be force-killed", console)
        self.assertIn("disabled", console)

    def test_T_start_operation_uses_existing_api(self):
        session = self._session()
        status, ctype, body = self.http(
            "POST", "/operations/start",
            form={"session_id": session.session_id, "mode": "runner",
                  "candidate_target": "src/cand.txt"})
        self.assertEqual(status, 200)
        self.assertIn("/operations/", body.decode("utf-8"))
        runs = api.get_runs(self.runs)
        self.assertTrue(runs)
        run = api.get_run(runs[-1], self.runs)
        self.assertIn(run.state, ("completed", "refused", "failed"))


class Governance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import raphael_ibm_bob.http as http_pkg
        cls.pkg = Path(http_pkg.__file__).parent
        cls.sources = {p: p.read_text(encoding="utf-8")
                       for p in cls.pkg.rglob("*.py")
                       if "__pycache__" not in p.parts}

    def test_U_no_direct_capability(self):
        for path, src in self.sources.items():
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal"):
                self.assertNotIn(token, src, f"{token} in {path}")

    def test_V_no_second_event_store(self):
        for path, src in self.sources.items():
            for token in ("append_evidence", "append_gate", "EvidenceLedger",
                          "LedgerWriter"):
                self.assertNotIn(token, src, f"{token} in {path}")

    def test_W_no_second_model_loop(self):
        for path, src in self.sources.items():
            for token in ("run_model_mission(", "drive_turns(",
                          "def propose(", "while True"):
                self.assertNotIn(token, src, f"{token} in {path}")


class ActiveRunObservability(_LiveCase):
    def test_active_run_is_observable_and_streams(self):
        session = self._session()
        requests = [self._req("skill:read-file"),
                    self._req("skill:read-file"),
                    self._req("skill:run-test")]
        result_holder = {}

        def _work():
            result_holder["result"] = run_model_mission(
                session, self.mission(), self.ws, runs_root=self.runs,
                model=_Scripted(requests, delay=0.15), probe=None,
                max_turns=5, sessions_root=self.sessions)

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        # Discover the run while it is still executing.
        run_id = None
        for _ in range(200):
            ids = api.get_runs(self.runs)
            if ids:
                try:
                    if api.get_run(ids[-1], self.runs):
                        run_id = ids[-1]
                        break
                except FileNotFoundError:
                    pass
            time.sleep(0.01)
        self.assertIsNotNone(run_id, "active run record was not observable")
        state_mid = api.get_run(run_id, self.runs).state
        self.assertEqual(state_mid, "running")
        frames = list(es.iter_frames(
            run_id, runs_root=self.runs, poll_seconds=0.03,
            max_seconds=30.0))
        worker.join(timeout=20)
        self.assertEqual(api.get_run(run_id, self.runs).state, "refused")
        emitted = [f for f in frames if f.startswith(b"event: RAPHAEL_EVENT")]
        self.assertGreaterEqual(len(emitted), 3)
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))


if __name__ == "__main__":
    unittest.main()
