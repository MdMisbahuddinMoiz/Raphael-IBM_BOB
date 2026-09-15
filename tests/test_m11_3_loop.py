"""tests.test_m11_3_loop — model turn driver tests.

The loop coordinates turns around the real RAPHAEL stack (tmp
workspace, real broker/policy/ledger). Model stand-ins are tiny
scripted adapters; nothing on the governed path is mocked.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List

from raphael_ibm_bob import (
    ActionRequest,
    BOBBroker,
    BOBPolicy,
    BOBRuntime,
    Capability,
    Mission,
    Workspace,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.loop import drive_turns
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.harness.providers import (
    DoneSignal,
    StructuredProposalError,
)


def _stack(testcase: unittest.TestCase):
    ws_root = Path(tempfile.mkdtemp(prefix="m113_ws_"))
    testcase.addCleanup(shutil.rmtree, ws_root, True)
    (ws_root / "src").mkdir()
    (ws_root / "src" / "a.txt").write_text("OK\n")
    run_root = Path(tempfile.mkdtemp(prefix="m113_run_"))
    testcase.addCleanup(shutil.rmtree, run_root, True)
    workspace = Workspace(ws_root)
    ledger = EvidenceLedger(run_root)
    broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    mission = Mission(mission_id="M-loop", description="x", scope="src/",
                      criteria=["x"])
    return runtime, store, mission, broker


def _read(target: str = "src/a.txt") -> ActionRequest:
    return ActionRequest(
        sequence=0, requester="loop-test", capability=Capability.READ,
        target=target, purpose="loop probe")


class Scripted:
    """Plays a script: ActionRequests to return, exceptions to raise."""

    def __init__(self, script: List):
        self._script = list(script)
        self.calls = 0

    def propose(self, context: ModelContext):
        self.calls += 1
        action = self._script[min(self.calls - 1, len(self._script) - 1)]
        if isinstance(action, Exception):
            raise action
        return action


class DoneFirstTurn(unittest.TestCase):
    def test_done_immediately(self):
        runtime, store, mission, broker = _stack(self)
        outcome = drive_turns(
            model=Scripted([DoneSignal("finished")]),
            runtime=runtime, mission=mission, store=store)
        self.assertEqual(outcome.terminal, "done")
        self.assertEqual(outcome.turns, [])
        self.assertEqual(broker.submissions, 0)


class AllowPath(unittest.TestCase):
    def test_allow_recorded_then_done(self):
        runtime, store, mission, _ = _stack(self)
        outcome = drive_turns(
            model=Scripted([_read(), DoneSignal("finished")]),
            runtime=runtime, mission=mission, store=store,
            workspace_root="ws")
        self.assertEqual(outcome.terminal, "done")
        self.assertEqual(len(outcome.turns), 1)
        turn = outcome.turns[0]
        self.assertEqual(turn.decision, "allow")
        self.assertTrue(turn.executed)
        self.assertTrue(turn.success)
        self.assertTrue(turn.evidence_ids)
        self.assertIsNone(turn.error)


class DenyContinues(unittest.TestCase):
    def test_deny_recorded_loop_continues(self):
        runtime, store, mission, broker = _stack(self)
        outcome = drive_turns(
            model=Scripted([_read("/etc/hostname"),
                            DoneSignal("finished")]),
            runtime=runtime, mission=mission, store=store)
        self.assertEqual(outcome.terminal, "done")
        self.assertEqual(len(outcome.turns), 1)
        turn = outcome.turns[0]
        self.assertEqual(turn.decision, "deny")
        self.assertFalse(turn.executed)
        self.assertIsNone(turn.success)
        self.assertEqual(broker.denies, 1)


class ModelError(unittest.TestCase):
    def test_malformed_stops_without_submission(self):
        runtime, store, mission, broker = _stack(self)
        outcome = drive_turns(
            model=Scripted(
                [StructuredProposalError("bad shape")]),
            runtime=runtime, mission=mission, store=store)
        self.assertEqual(outcome.terminal, "model-error")
        self.assertIn("StructuredProposalError", outcome.reason)
        self.assertEqual(outcome.turns, [])
        self.assertEqual(broker.submissions, 0)


class MaxTurns(unittest.TestCase):
    def test_bounded(self):
        runtime, store, mission, _ = _stack(self)
        outcome = drive_turns(
            model=Scripted([_read()]), runtime=runtime,
            mission=mission, store=store, max_turns=3)
        self.assertEqual(outcome.terminal, "max-turns")
        self.assertEqual(len(outcome.turns), 3)
        self.assertEqual([t.index for t in outcome.turns], [0, 1, 2])

    def test_bad_max_turns_rejected(self):
        runtime, store, mission, _ = _stack(self)
        with self.assertRaises(ValueError):
            drive_turns(model=Scripted([_read()]), runtime=runtime,
                        mission=mission, store=store, max_turns=0)


class RuntimeError(unittest.TestCase):
    def test_broker_rejection_recorded(self):
        runtime, store, mission, _ = _stack(self)
        bad = ActionRequest(
            sequence=0, requester="loop-test",
            capability=Capability.READ, target="src/a.txt",
            purpose="p", timeout_seconds=-1.0)
        outcome = drive_turns(
            model=Scripted([bad]), runtime=runtime, mission=mission,
            store=store)
        self.assertEqual(outcome.terminal, "runtime-error")
        self.assertEqual(len(outcome.turns), 1)
        self.assertIn("ValueError", outcome.turns[0].error)


class Determinism(unittest.TestCase):
    def test_same_script_same_outcome(self):
        def run_once():
            runtime, store, mission, _ = _stack(self)
            return drive_turns(
                model=Scripted([_read(), DoneSignal("x")]),
                runtime=runtime, mission=mission,
                store=store).to_dict()
        first, second = run_once(), run_once()
        self.assertEqual(first["terminal"], second["terminal"])
        self.assertEqual(len(first["turns"]), len(second["turns"]))
        self.assertEqual(first["turns"][0]["decision"],
                         second["turns"][0]["decision"])


if __name__ == "__main__":
    unittest.main()
