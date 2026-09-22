"""tests.test_harness — thin Harness unit tests.

Session/run/model/events/workspace behavior with real ledger reads;
no execution mocking (nothing here executes capabilities at all,
except the CLI run-start path which drives the real stack and
honestly refuses on an empty workspace).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    Mission,
    Workspace,
)
from raphael_ibm_bob.harness import (
    ModelAdapter,
    ModelContext,
    RaphaelSession,
    ScriptedModelAdapter,
    WorkspaceContext,
    collect_events,
    load_session,
    save_session,
)
from raphael_ibm_bob.harness.cli import main as harness_main
from raphael_ibm_bob.harness.events import EVENT_TYPES
from raphael_ibm_bob.harness.run import (
    RaphaelRun,
    load_run,
    save_run,
    start_run,
)


def _mission() -> Mission:
    return Mission(
        mission_id="M-h", description="harness mission", scope="src/",
        criteria=["x"],
        problem={"symptom_target": "src/a.txt", "capability": "read",
                 "purpose": "harness probe"})


class SessionTests(unittest.TestCase):
    def test_create_save_reload(self):
        base = Path(tempfile.mkdtemp(prefix="h_sess_"))
        self.addCleanup(shutil.rmtree, base, True)
        session = RaphaelSession.create(
            mission=_mission(),
            workspace=WorkspaceContext(workspace_root="/tmp",
                                       project_name="p"),
            model="scripted")
        path = save_session(session, base)
        self.assertTrue(path.is_file())
        reloaded = load_session(session.session_id, base)
        self.assertEqual(reloaded.session_id, session.session_id)
        self.assertEqual(reloaded.mission.mission_id, "M-h")
        self.assertEqual(reloaded.workspace.project_name, "p")
        self.assertEqual(reloaded.status, "open")

    def test_missing_session_raises(self):
        base = Path(tempfile.mkdtemp(prefix="h_sess_"))
        self.addCleanup(shutil.rmtree, base, True)
        with self.assertRaises(FileNotFoundError):
            load_session("nope", base)

    def test_workspace_context_from_workspace(self):
        root = Path(tempfile.mkdtemp(prefix="h_ws_"))
        self.addCleanup(shutil.rmtree, root, True)
        ctx = WorkspaceContext.from_workspace(Workspace(root), "proj")
        self.assertEqual(ctx.workspace_root, str(root.resolve()))
        self.assertEqual(ctx.project_name, "proj")
        self.assertEqual(ctx.run_ids, [])


class ModelBoundary(unittest.TestCase):
    def test_scripted_proposal(self):
        req = ActionRequest(
            sequence=0, requester="m", capability=Capability.READ,
            target="src/a.txt", purpose="p")
        adapter = ScriptedModelAdapter({"M-h": req})
        self.assertIsInstance(adapter, ModelAdapter)
        ctx = ModelContext(mission=_mission())
        self.assertEqual(adapter.propose(ctx), req)

    def test_unknown_mission_raises(self):
        adapter = ScriptedModelAdapter({})
        with self.assertRaises(KeyError):
            adapter.propose(ModelContext(mission=_mission()))

    def test_context_summary(self):
        ctx = ModelContext(
            mission=_mission(),
            findings=[Finding(finding_id="F-1",
                              state=FindingState.VERIFIED,
                              summary="s", target="t")],
            workspace_root="/w", evidence_count=3)
        summary = ctx.summary()
        self.assertEqual(summary["mission_id"], "M-h")
        self.assertEqual(summary["findings"][0]["state"], "verified")
        self.assertNotIn("policy", json.dumps(summary))


class RunRecord(unittest.TestCase):
    def _run(self) -> RaphaelRun:
        return RaphaelRun(
            run_id="r-1", session_id="s-1", mission=_mission(),
            workspace_root="/w", state="running", ledger_dir="/tmp/x")

    def test_cancel_pending(self):
        run = self._run()
        run.state = "pending"
        self.assertTrue(run.cancel())
        self.assertEqual(run.state, "cancelled")
        self.assertIsNotNone(run.finished_at)

    def test_cancel_running_refused(self):
        run = self._run()
        self.assertFalse(run.cancel())
        self.assertEqual(run.state, "running")

    def test_save_load_roundtrip(self):
        base = Path(tempfile.mkdtemp(prefix="h_run_"))
        self.addCleanup(shutil.rmtree, base, True)
        run = self._run()
        run.ledger_dir = str(base)
        run.gate_verdict = "refuse"
        run.plan_ids = ["P-a"]
        save_run(run)
        reloaded = load_run(base)
        self.assertEqual(reloaded.run_id, "r-1")
        self.assertEqual(reloaded.mission.mission_id, "M-h")
        self.assertEqual(reloaded.plan_ids, ["P-a"])


class EventFolding(unittest.TestCase):
    def _records(self):
        return [
            {"kind": "request", "seq": 1, "capability": "read",
             "target": "src/a.txt", "requester": "planner",
             "plan_id": "P-a"},
            {"kind": "decision", "seq": 2, "decision": "allow",
             "reason": "ok", "request_seq": 1},
            {"kind": "result", "seq": 3, "success": True,
             "request_seq": 1, "artifact_ref": "/tmp/a.json"},
            {"kind": "evidence", "seq": 4, "producer": "verifier",
             "evidence_id": "V-1", "finding_id": "F-1",
             "payload": {"kind": "retest"}},
            {"kind": "evidence", "seq": 5, "producer": "falsifier",
             "evidence_id": "F-1", "finding_id": "F-1",
             "payload": {"kind": "counter-example", "target": "src/b"}},
            {"kind": "evidence", "seq": 6, "producer": "replanner",
             "evidence_id": "R-1", "finding_id": "F-1",
             "payload": {"parent_plan_id": "P-a", "plan_b_id": "P-b",
                         "refuted_finding_id": "F-1"}},
            {"kind": "finding", "seq": 7, "finding_id": "F-1",
             "state": "refuted", "prev_state": "verified"},
            {"kind": "gate", "seq": 8, "decision": "refuse",
             "checks": ["A"], "mission_id": "M-h"},
        ]

    def test_folds_all_types(self):
        events = collect_events(
            self._records(), session_id="s", run_id="r",
            mission_id="M-h")
        types = [e["type"] for e in events]
        for expected in ("SESSION_CREATED", "MISSION_STARTED",
                         "PLAN_CREATED", "ACTION_REQUESTED",
                         "POLICY_DECISION", "EXECUTION_RESULT",
                         "VERIFICATION_RESULT", "FALSIFICATION_RESULT",
                         "REPLAN_CREATED", "FINDING_CHANGED",
                         "GATE_EVALUATED", "RUN_REFUSED"):
            self.assertIn(expected, types, msg=expected)
        seqs = [e["seq"] for e in events if not e.get("synthetic")]
        self.assertEqual(seqs, sorted(seqs))

    def test_event_types_cover_contract(self):
        for required in ("SESSION_CREATED", "MISSION_STARTED",
                         "PLAN_CREATED", "ACTION_REQUESTED",
                         "POLICY_DECISION", "EXECUTION_RESULT",
                         "EVIDENCE_RECORDED", "FINDING_CHANGED",
                         "VERIFICATION_RESULT", "FALSIFICATION_RESULT",
                         "REPLAN_CREATED", "GATE_EVALUATED",
                         "RUN_COMPLETED", "RUN_REFUSED", "RUN_FAILED",
                         "RUN_CANCELLED"):
            self.assertIn(required, EVENT_TYPES)

    def test_deterministic(self):
        first = collect_events(self._records(), session_id="s",
                               run_id="r", mission_id="M-h")
        second = collect_events(list(reversed(self._records())),
                                session_id="s", run_id="r",
                                mission_id="M-h")
        self.assertEqual(first, second)


class CliSurface(unittest.TestCase):
    def _roots(self):
        base = Path(tempfile.mkdtemp(prefix="h_cli_"))
        self.addCleanup(shutil.rmtree, base, True)
        return base / "sessions", base / "runs"

    def test_session_create_show(self):
        sessions, runs = self._roots()
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "session-create", "--project", "demo"]), 0)
        session_id = next(p.name for p in sessions.iterdir())
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "session-show", session_id]), 0)

    def test_mission_submit_then_start_refuses_honestly(self):
        sessions, runs = self._roots()
        ws = Path(tempfile.mkdtemp(prefix="h_cli_ws_"))
        self.addCleanup(shutil.rmtree, ws, True)
        (ws / "src").mkdir()
        (ws / "src" / "probe.txt").write_text("hi\n")
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "session-create", "--workspace", str(ws),
             "--with-mission", "--mission-id", "M-cli",
             "--symptom-target", "src/probe.txt"]), 0)
        session_id = next(p.name for p in sessions.iterdir())
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "mission-submit", session_id,
             "--mission-id", "M-cli",
             "--symptom-target", "src/probe.txt"]), 0)
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-start", session_id]), 0)
        run_dirs = [p for p in runs.iterdir() if p.is_dir()]
        self.assertEqual(len(run_dirs), 1)
        run = load_run(run_dirs[0])
        self.assertEqual(run.state, "refused")
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-show", str(run_dirs[0])]), 0)
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-events", str(run_dirs[0])]), 0)
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-evidence", str(run_dirs[0])]), 0)
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-artifacts", str(run_dirs[0])]), 0)

    def test_start_without_mission_fails(self):
        sessions, runs = self._roots()
        harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "session-create"])
        session_id = next(p.name for p in sessions.iterdir())
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-start", session_id]), 2)


class DefaultSkills(unittest.TestCase):
    def test_five_generic_skills(self):
        from raphael_ibm_bob.skills import (
            default_registry,
            register_default_skills,
        )
        reg = register_default_skills(default_registry())
        ids = sorted(s.id for s in reg.list_skills())
        self.assertEqual(ids, ["list-dir", "network-http-request", "read-file",
                               "run-test", "search-dir", "write-file"])
        proposal = reg.propose("read-file", "src/a.txt")
        self.assertEqual(proposal.request.capability, Capability.READ)
        self.assertEqual(proposal.request.purpose, "read-file:src/a.txt")

    def test_idempotent_registration(self):
        from raphael_ibm_bob.skills import (
            default_registry,
            register_default_skills,
        )
        reg = register_default_skills(default_registry())
        register_default_skills(reg)  # second call is a no-op
        self.assertEqual(len(reg.list_skills()), 6)


class ModelProviderOption(unittest.TestCase):
    def _session(self):
        sessions = Path(tempfile.mkdtemp(prefix="h_prov_sess_"))
        self.addCleanup(shutil.rmtree, sessions, True)
        runs = Path(tempfile.mkdtemp(prefix="h_prov_runs_"))
        self.addCleanup(shutil.rmtree, runs, True)
        ws = Path(tempfile.mkdtemp(prefix="h_prov_ws_"))
        self.addCleanup(shutil.rmtree, ws, True)
        (ws / "src").mkdir()
        (ws / "src" / "probe.txt").write_text("hi\n")
        harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "session-create", "--workspace", str(ws),
             "--with-mission", "--mission-id", "M-prov",
             "--symptom-target", "src/probe.txt"])
        session_id = next(p.name for p in sessions.iterdir())
        return sessions, runs, session_id

    def test_missing_config_exits_2(self):
        import os
        from unittest.mock import patch
        sessions, runs, session_id = self._session()
        clean = {k: v for k, v in os.environ.items()
                 if not k.startswith("RAPHAEL_MODEL_")}
        with patch.dict("os.environ", clean, clear=True):
            code = harness_main(
                ["--sessions-root", str(sessions),
                 "--runs-root", str(runs),
                 "run-start", session_id,
                 "--model-provider", "openai-compatible"])
        self.assertEqual(code, 2)

    def test_unknown_provider_exits_2(self):
        sessions, runs, session_id = self._session()
        self.assertEqual(harness_main(
            ["--sessions-root", str(sessions),
             "--runs-root", str(runs),
             "run-start", session_id,
             "--model-provider", "does-not-exist"]), 2)


if __name__ == "__main__":
    unittest.main()
