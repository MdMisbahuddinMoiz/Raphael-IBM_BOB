"""tests.test_harness_e2e — integrated Harness scenario (mock-free core).

Mission -> RaphaelSession -> Harness Run -> model/skill proposal ->
ActionRequest -> Runtime -> Broker -> Policy -> Execution -> Evidence
-> Finding -> Verification -> Falsification -> Replan -> Independent
Verification -> QualityGate -> COMPLETE.

Nothing on the RAPHAEL path is mocked: the only scripted piece is the
model adapter's opening proposal (an ordinary ActionRequest that the
boundary still authorizes). The Runner, Broker, Policy, Evidence,
and Gate are all real.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Mission,
    Workspace,
)
from raphael_ibm_bob.falsifier import ChallengeSpec
from raphael_ibm_bob.harness import (
    RaphaelSession,
    ScriptedModelAdapter,
    WorkspaceContext,
    collect_events,
    load_session,
    save_session,
)
from raphael_ibm_bob.harness.events import EVENT_TYPES
from raphael_ibm_bob.harness.run import load_run, start_run


def _world(testcase: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp(prefix="h_e2e_ws_"))
    testcase.addCleanup(shutil.rmtree, root, True)
    src = root / "src"
    src.mkdir()
    (src / "cand_a.txt").write_text("OK\n", encoding="utf-8")
    (src / "cand_b.txt").write_text("OK\nDEFECT: beta\n",
                                    encoding="utf-8")
    (src / "cand_c.txt").write_text("OK\n", encoding="utf-8")
    (src / "test_ok.py").write_text(
        "import unittest\n"
        "class OkTest(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertTrue(True)\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8")
    return root


def _mission() -> Mission:
    return Mission(
        mission_id="M-harness-e2e",
        description="harness end-to-end recovery",
        scope="src/",
        criteria=["recover through the harness"],
        problem={"symptom_target": "src/cand_a.txt",
                 "capability": "read",
                 "purpose": "harness:initial-probe"})


def _specs():
    return [
        ChallengeSpec(
            capability=Capability.READ, target="src/cand_b.txt",
            purpose="harness:challenge-F1",
            forbidden_substring="DEFECT"),
        ChallengeSpec(
            capability=Capability.READ, target="src/cand_c.txt",
            purpose="harness:challenge-F2",
            forbidden_substring="ZZZ-ABSENT"),
    ]


class HarnessEndToEnd(unittest.TestCase):
    def test_full_chain_completes(self):
        ws_root = _world(self)
        base = Path(tempfile.mkdtemp(prefix="h_e2e_"))
        self.addCleanup(shutil.rmtree, base, True)
        sessions_root = base / "sessions"
        runs_root = base / "runs"

        session = RaphaelSession.create(
            mission=_mission(),
            workspace=WorkspaceContext.from_workspace(
                Workspace(ws_root), "e2e"),
            model="scripted-e2e")
        save_session(session, sessions_root)

        model = ScriptedModelAdapter({
            "M-harness-e2e": ActionRequest(
                sequence=0, requester="harness:model",
                capability=Capability.READ, target="src/cand_a.txt",
                purpose="harness:opening-probe"),
        })

        run = start_run(
            session, session.mission, ws_root,
            runs_root=runs_root, sessions_root=sessions_root,
            model=model,
            candidate_target="src/cand_a.txt",
            candidate_summary="candidate A leaves the defect",
            challenge_specs=_specs(),
            verification_tests=("src/test_ok.py",),
            max_replans=2,
        )

        # Run record references authoritative truth.
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.gate_verdict, "complete")
        self.assertEqual(len(run.plan_ids), 2)
        self.assertEqual(len(run.finding_ids), 2)
        reloaded = load_run(Path(run.ledger_dir))
        self.assertEqual(reloaded.gate_verdict, "complete")

        # Session tracks the run and persists.
        self.assertEqual(session.current_run_id, run.run_id)
        self.assertEqual(
            load_session(session.session_id,
                         sessions_root).current_run_id, run.run_id)

        # The model proposal really executed through the boundary.
        from raphael_ibm_bob.evidence_ledger import LedgerReader
        records = list(LedgerReader(
            Path(run.ledger_dir) / "evidence.jsonl").records())
        proposals = [r for r in records
                     if r.get("kind") == "request"
                     and r.get("requester") == "harness:model"]
        self.assertEqual(len(proposals), 1)
        decisions = [r for r in records
                     if r.get("kind") == "decision"
                     and r.get("request_seq") == proposals[0]["seq"]]
        self.assertEqual(decisions[0]["decision"], "allow")

        # Findings followed the lifecycle across attempts.
        states = {}
        for rec in records:
            if rec.get("kind") == "finding":
                states.setdefault(rec["finding_id"], []).append(
                    rec["state"])
        self.assertEqual(states[run.finding_ids[0]],
                         ["unverified", "verified", "refuted"])
        self.assertEqual(states[run.finding_ids[1]],
                         ["unverified", "verified"])

        # Event stream reconstructs the chain from disk.
        events = collect_events(
            records, session_id=session.session_id, run_id=run.run_id,
            mission_id=session.mission.mission_id)
        types = [e["type"] for e in events]
        for required in ("MISSION_STARTED", "PLAN_CREATED",
                         "ACTION_REQUESTED", "POLICY_DECISION",
                         "EXECUTION_RESULT", "FINDING_CHANGED",
                         "VERIFICATION_RESULT", "FALSIFICATION_RESULT",
                         "REPLAN_CREATED", "GATE_EVALUATED",
                         "RUN_COMPLETED"):
            self.assertIn(required, types, msg=required)
        for event in events:
            self.assertIn(event["type"], EVENT_TYPES)


if __name__ == "__main__":
    unittest.main()
