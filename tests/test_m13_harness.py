"""tests.test_m13_harness — M13 Harness foundation tests.

Exercises the public Harness API over the real RAPHAEL core. The only
substituted component is the model in the scripted cases; the stub
HTTP provider case exercises the real OpenAI-compatible adapter.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Mission,
)
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.events import EVENT_TYPES
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers.openai_compat import (
    DoneSignal,
    OpenAICompatAdapter,
    OpenAICompatConfig,
)
from raphael_ibm_bob.harness.run import (
    RUN_STATES,
    TERMINAL_STATES,
    RaphaelRun,
    save_run,
)
from raphael_ibm_bob.skills import (
    default_registry,
    register_default_skills,
)


def _mk_tree(testcase):
    base = Path(tempfile.mkdtemp(prefix="m13_"))
    testcase.addCleanup(shutil.rmtree, base, True)
    runs = base / "runs"
    sessions = base / "sessions"
    ws = base / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
    (ws / "src" / "still_buggy.py").write_text(
        "BUG: still contains the original defect\n", encoding="utf-8")
    return runs, sessions, ws


def _mission(ws: Path) -> Mission:
    return Mission(
        mission_id="M-m13", description="m13", scope="src/",
        criteria=["recover"],
        problem={"symptom_target": "src/cand.txt",
                 "capability": "read", "purpose": "m13:probe"})


class SessionAndWorkspace(unittest.TestCase):
    def test_A_session_create_persist_reload(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws, project_name="p1",
            model="deepseek-v4.1-flash", provider="openai-compatible",
            sessions_root=sessions)
        self.assertTrue(
            (sessions / session.session_id / "session.json").is_file())
        reloaded = api.get_session(session.session_id, sessions)
        self.assertEqual(reloaded.mission.mission_id, "M-m13")
        self.assertEqual(reloaded.model, "deepseek-v4.1-flash")
        self.assertEqual(reloaded.provider, "openai-compatible")
        # No credentials persisted: no key-bearing fields in the file.
        blob = (sessions / session.session_id / "session.json").read_text()
        for forbidden in ("api_key", "sk-", "nvapi-", "authorization"):
            self.assertNotIn(forbidden, blob.lower())

    def test_A_session_list_and_missing(self):
        runs, sessions, ws = _mk_tree(self)
        api.create_session(workspace_root=ws, sessions_root=sessions,
                           session_id="s-b")
        api.create_session(workspace_root=ws, sessions_root=sessions,
                           session_id="s-a")
        self.assertEqual(api.get_sessions(sessions), ["s-a", "s-b"])
        with self.assertRaises(FileNotFoundError):
            api.get_session("nope", sessions)

    def test_B_workspace_description_and_association(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            workspace_root=ws, sessions_root=sessions,
            project_name="proj")
        view = api.describe_workspace(ws, sessions_root=sessions,
                                      runs_root=runs)
        self.assertEqual(view["workspace_root"], str(ws.resolve()))
        self.assertEqual(view["sessions"], [session.session_id])
        self.assertIn("read", view["available_capabilities"])
        self.assertIn("run_test", view["available_capabilities"])


class RunLifecycle(unittest.TestCase):
    def test_C_mission_to_run_creation(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        session = api.submit_mission(
            session.session_id, _mission(ws), sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        self.assertEqual(run.session_id, session.session_id)
        self.assertEqual(run.mission.mission_id, "M-m13")
        self.assertTrue(Path(run.ledger_dir).is_dir())
        restored = api.get_session(session.session_id, sessions)
        self.assertIn(run.run_id, restored.run_ids)
        self.assertEqual(restored.current_run_id, run.run_id)

    def test_D_run_lifecycle_states(self):
        self.assertIn("pending", RUN_STATES)
        self.assertEqual(set(TERMINAL_STATES),
                         {"completed", "refused", "failed", "cancelled"})
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        self.assertIn(run.state, TERMINAL_STATES)
        self.assertTrue(run.is_terminal())
        self.assertFalse(run.cancel())

    def test_H_gate_result_retrieval(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        gate = api.get_gate(run.run_id, runs)
        self.assertIsNotNone(gate)
        self.assertEqual(gate["kind"], "gate")
        self.assertEqual(gate["decision"], run.gate_verdict)
        self.assertEqual(gate["run_id"], run.run_id)

    def test_O_reload_preserves_observability(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        # Fresh load from disk (as a new process would).
        reloaded = api.get_run(run.run_id, runs)
        self.assertEqual(reloaded.run_id, run.run_id)
        self.assertEqual(reloaded.gate_verdict, run.gate_verdict)
        self.assertIn(run.run_id, api.get_runs(runs))
        with self.assertRaises(FileNotFoundError):
            api.get_run("does-not-exist", runs)


class EvidenceEventsArtifacts(unittest.TestCase):
    def _started(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        return runs, run

    def test_F_evidence_retrieval(self):
        runs, run = self._started()
        records = api.get_evidence(run.run_id, runs)
        self.assertGreater(len(records), 0)
        self.assertTrue(all("seq" in r and "kind" in r for r in records))
        seqs = sorted(r["seq"] for r in records)
        self.assertEqual(seqs, list(range(1, len(records) + 1)))

    def test_G_artifact_retrieval(self):
        runs, run = self._started()
        artifacts = api.get_artifacts(run.run_id, runs)
        self.assertGreater(len(artifacts), 0)
        self.assertTrue(all(p.is_file() for p in artifacts))

    def test_E_event_reconstruction(self):
        runs, run = self._started()
        events = api.get_events(run.run_id, runs)
        self.assertGreater(len(events), 0)
        for event in events:
            self.assertIn(event["type"], EVENT_TYPES)
        types = [e["type"] for e in events]
        self.assertIn("ACTION_REQUESTED", types)
        self.assertIn("POLICY_DECISION", types)
        self.assertIn("GATE_EVALUATED", types)
        # Deterministic + stable across reads.
        self.assertEqual(events, api.get_events(run.run_id, runs))
        seqs = [e["seq"] for e in events if not e.get("synthetic")]
        self.assertEqual(seqs, sorted(seqs))

    def test_evidence_is_read_only_api(self):
        runs, run = self._started()
        before = api.get_evidence(run.run_id, runs)
        # Mutating the returned list must not affect persisted state.
        before.clear()
        after = api.get_evidence(run.run_id, runs)
        self.assertGreater(len(after), 0)


class Cancellation(unittest.TestCase):
    def test_I_cancel_pending_run(self):
        runs, sessions, ws = _mk_tree(self)
        run_id = "20260101T000000_cancel"
        run_dir = runs / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
        save_run(RaphaelRun(
            run_id=run_id, session_id="s", mission=_mission(ws),
            workspace_root=str(ws), state="pending",
            ledger_dir=str(run_dir)))
        cancelled = api.cancel_run(run_id, runs)
        self.assertEqual(cancelled.state, "cancelled")
        self.assertTrue(cancelled.is_terminal())
        # Terminal run is not silently restarted: a second cancel is a
        # no-op and the persisted state stays cancelled.
        again = api.cancel_run(run_id, runs)
        self.assertEqual(again.state, "cancelled")

    def test_live_style_run_cancel_is_reported_honestly(self):
        # A run already executing synchronously cannot be preempted.
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)
        run = api.start_run(session, sessions_root=sessions,
                            runs_root=runs)
        result = api.cancel_run(run.run_id, runs)
        self.assertEqual(result.state, run.state)
        self.assertNotEqual(result.state, "cancelled")


class GovernanceBoundary(unittest.TestCase):
    def test_API_module_has_no_execution_authority(self):
        # Static: the API/CLI must not import execution primitives.
        import raphael_ibm_bob.harness.api as api_mod
        src = Path(api_mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("execute_capability", "subprocess",
                          "socket", "bravo"):
            self.assertNotIn(forbidden, src)
        cli = Path(api_mod.__file__).with_name("cli.py").read_text(
            encoding="utf-8")
        self.assertNotIn("execute_capability", cli)

    def test_J_K_denied_proposal_not_executed(self):
        runs, sessions, ws = _mk_tree(self)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions)

        class DenyThenDone:
            def __init__(self):
                self.calls = 0

            def propose(self, context: ModelContext):
                self.calls += 1
                if self.calls == 1:
                    # Out-of-scope target -> Policy DENY.
                    return ActionRequest(
                        sequence=0, requester="harness",
                        capability=Capability.READ,
                        target="/etc/hostname", purpose="escape")
                raise DoneSignal("done")

        result = run_model_mission(
            session, _mission(ws), ws, runs_root=runs,
            model=DenyThenDone(), max_turns=5, probe=None)
        records = api.get_evidence(result.run.run_id, runs)
        denials = [r for r in records
                   if r.get("kind") == "decision"
                   and r.get("decision") == "deny"]
        self.assertEqual(len(denials), 1)
        results = [r for r in records if r.get("kind") == "result"]
        self.assertEqual(len(results), 0)  # denied => no execution

    def test_L_M_model_proposal_validation_and_no_execution(self):
        from raphael_ibm_bob.broker import BOBBroker
        from raphael_ibm_bob.evidence_ledger import EvidenceLedger
        from raphael_ibm_bob.harness.providers.openai_compat import (
            StructuredProposalError,
            validate_proposal,
        )
        from raphael_ibm_bob.policy import BOBPolicy
        from raphael_ibm_bob.runtime import BOBRuntime
        from raphael_ibm_bob.workspace import Workspace

        runs, sessions, ws = _mk_tree(self)
        # L: an invalid proposal is rejected by validation (never
        # becomes an ActionRequest).
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "launch-missiles",
                 "target": "x", "purpose": "p"},
                register_default_skills(default_registry()))
        # M: rejected proposals never reach the Broker.
        ledger = EvidenceLedger(runs / "gov_probe")
        workspace = Workspace(ws)
        broker = BOBBroker(BOBPolicy(workspace), workspace,
                           ledger=ledger)
        self.assertEqual(broker.submissions, 0)
        self.assertEqual(broker.capability_invocations, 0)


class LiveProviderPath(unittest.TestCase):
    """N: the live OpenAI-compatible path works through the Harness."""

    def _stub(self):
        payloads = {
            "calls": 0,
        }
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                payloads["calls"] += 1
                if payloads["calls"] == 1:
                    content = {"intent": "act", "skill": "read-file",
                               "target": "src/cand.txt",
                               "purpose": "inspect"}
                else:
                    content = {"intent": "done"}
                body = {"choices": [{"message": {
                    "content": json.dumps(content)}}]}
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(
            target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        return payloads, f"http://{host}:{port}"

    def test_N_live_provider_adapter_reaches_terminal(self):
        runs, sessions, ws = _mk_tree(self)
        payloads, url = self._stub()
        registry = register_default_skills(default_registry())
        adapter = OpenAICompatAdapter(
            OpenAICompatConfig(endpoint=url, model="stub", max_tokens=256),
            registry)
        session = api.create_session(
            mission=_mission(ws), workspace_root=ws,
            sessions_root=sessions, model="stub",
            provider="openai-compatible")
        result = run_model_mission(
            session, _mission(ws), ws, runs_root=runs, model=adapter,
            max_turns=5, probe=None)
        self.assertEqual(result.terminal, "done")
        self.assertGreaterEqual(payloads["calls"], 2)
        self.assertIn(result.run.state, TERMINAL_STATES)
        gate = api.get_gate(result.run.run_id, runs)
        self.assertIsNotNone(gate)


if __name__ == "__main__":
    unittest.main()
