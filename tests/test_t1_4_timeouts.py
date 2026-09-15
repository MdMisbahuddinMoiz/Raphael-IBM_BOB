"""tests.test_t1_4_timeouts — T1-4 bounded capability timeouts.

A timeout is enforced at the Broker invocation boundary and recorded
as an unsuccessful execution: never success, never rewritten as DENY.
Uses real subprocess execution (a genuinely slow test file); nothing
about the timeout path is mocked.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict

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
from raphael_ibm_bob.skills import default_registry


def _workspace(testcase: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp(prefix="t1_4_ws_"))
    testcase.addCleanup(shutil.rmtree, root, True)
    src = root / "src"
    src.mkdir()
    (src / "test_slow.py").write_text(
        "import time\n"
        "import unittest\n"
        "class SlowTest(unittest.TestCase):\n"
        "    def test_slow(self):\n"
        "        time.sleep(30)\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8")
    (src / "test_fast.py").write_text(
        "import unittest\n"
        "class FastTest(unittest.TestCase):\n"
        "    def test_fast(self):\n"
        "        self.assertTrue(True)\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8")
    return root


def _stack(testcase: unittest.TestCase, ws_root: Path,
           defaults: Dict = None):
    run_root = Path(tempfile.mkdtemp(prefix="t1_4_run_"))
    testcase.addCleanup(shutil.rmtree, run_root, True)
    workspace = Workspace(ws_root)
    ledger = EvidenceLedger(run_root)
    broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger,
                       default_timeouts=defaults)
    runtime = BOBRuntime(broker)
    mission = Mission(mission_id="M-t", description="x", scope="src/",
                      criteria=["x"])
    return workspace, ledger, broker, runtime, mission


def _submit(runtime, mission, target, timeout=None):
    return runtime.submit(ActionRequest(
        sequence=0, requester="probe", capability=Capability.RUN_TEST,
        target=target, purpose="t1-4", timeout_seconds=timeout), mission)


class TimeoutOccurs(unittest.TestCase):
    def test_slow_test_times_out(self):
        _, _, _, runtime, mission = _stack(self, _workspace(self))
        rt = _submit(runtime, mission, "src/test_slow.py", timeout=2.0)
        self.assertEqual(
            rt.broker_result.decision.decision.value, "allow")
        self.assertTrue(rt.broker_result.capability_invoked)
        self.assertIsNotNone(rt.execution)
        self.assertFalse(rt.execution.success)
        self.assertEqual(rt.execution.output, "timeout")
        self.assertIn("TimeoutExpired", rt.execution.error)
        self.assertTrue(rt.execution.evidence.get("timeout"))

    def test_timeout_recorded_in_evidence(self):
        _, ledger, _, runtime, mission = _stack(
            self, _workspace(self))
        rt = _submit(runtime, mission, "src/test_slow.py", timeout=2.0)
        exec_recs = [
            r for r in ledger.all_records()
            if r.get("kind") == "evidence"
            and r.get("producer") == "execution"
            and r.get("request_seq") == rt.request_seq]
        self.assertEqual(len(exec_recs), 1)
        self.assertTrue("timeout" in exec_recs[0]["payload"]["evidence_keys"])
        results = [
            r for r in ledger.all_records()
            if r.get("kind") == "result"
            and r.get("request_seq") == rt.request_seq]
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["success"])

    def test_timeout_is_neither_success_nor_deny(self):
        _, _, broker, runtime, mission = _stack(
            self, _workspace(self))
        before_denies = broker.denies
        rt = _submit(runtime, mission, "src/test_slow.py", timeout=2.0)
        # Decision stayed ALLOW (authorized + attempted)...
        self.assertEqual(
            rt.broker_result.decision.decision.value, "allow")
        self.assertEqual(broker.denies, before_denies)
        # ...but the execution is unsuccessful.
        self.assertFalse(rt.execution.success)


class NoTimeoutRegression(unittest.TestCase):
    def test_fast_test_still_passes(self):
        _, _, _, runtime, mission = _stack(self, _workspace(self))
        rt = _submit(runtime, mission, "src/test_fast.py")
        self.assertTrue(rt.execution.success)
        self.assertEqual(rt.execution.evidence.get("returncode"), 0)

    def test_default_run_test_bound_preserved(self):
        # Without any timeout configured, RUN_TEST still enforces its
        # 30s broker default and records it in decision evidence.
        _, ledger, _, runtime, mission = _stack(
            self, _workspace(self))
        rt = _submit(runtime, mission, "src/test_fast.py")
        self.assertTrue(rt.execution.success)
        policy_recs = [
            r for r in ledger.all_records()
            if r.get("kind") == "evidence"
            and r.get("producer") == "policy"
            and r.get("request_seq") == rt.request_seq]
        self.assertEqual(len(policy_recs), 1)
        self.assertEqual(
            policy_recs[0]["payload"]["timeout_seconds"], 30.0)

    def test_broker_default_timeouts(self):
        _, _, _, runtime, mission = _stack(
            self, _workspace(self),
            defaults={Capability.RUN_TEST: 2.0})
        rt = _submit(runtime, mission, "src/test_slow.py")
        self.assertFalse(rt.execution.success)
        self.assertEqual(rt.execution.output, "timeout")

    def test_invalid_timeout_rejected(self):
        _, _, _, runtime, mission = _stack(self, _workspace(self))
        for bad in (0.0, -1.0):
            with self.assertRaises(ValueError, msg=str(bad)):
                _submit(runtime, mission, "src/test_fast.py",
                        timeout=bad)

    def test_invalid_broker_defaults_rejected(self):
        ws_root = _workspace(self)
        workspace = Workspace(ws_root)
        policy = BOBPolicy(workspace)
        with self.assertRaises(ValueError):
            BOBBroker(policy, workspace,
                      default_timeouts={Capability.READ: 0.0})


class SkillTimeoutDefaults(unittest.TestCase):
    def test_declaration_default_applies(self):
        reg = default_registry()
        from raphael_ibm_bob.skills import SkillDefinition
        reg.register_skill(SkillDefinition(
            id="run-it", name="Run it", version="1.0",
            description="run a test", capability=Capability.RUN_TEST,
            target_schema="t", purpose_template="run:{target}"))
        proposal = reg.propose("run-it", "src/test_fast.py")
        self.assertEqual(proposal.request.timeout_seconds, 30.0)

    def test_explicit_override_wins(self):
        from raphael_ibm_bob.skills import SkillDefinition
        reg = default_registry()
        reg.register_skill(SkillDefinition(
            id="run-it", name="Run it", version="1.0",
            description="run a test", capability=Capability.RUN_TEST,
            target_schema="t", purpose_template="run:{target}"))
        proposal = reg.propose("run-it", "src/test_fast.py",
                               timeout_seconds=5.0)
        self.assertEqual(proposal.request.timeout_seconds, 5.0)
        with self.assertRaises(ValueError):
            reg.propose("run-it", "src/test_fast.py",
                        timeout_seconds=-2.0)


if __name__ == "__main__":
    unittest.main()
