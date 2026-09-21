"""tests.test_c1a_lifecycle — host-side lifecycle orchestration."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import c1a_request, cleanup, make_stack  # noqa: E402
from raphael_ibm_bob.b4_lifecycle import LifecycleState  # noqa: E402
from raphael_ibm_bob.c1a_lifecycle import (  # noqa: E402
    C1ALifecycleError,
    C1ALifecycleOrchestrator,
)

SHA = "a" * 64


class _FakeTransport:
    def __init__(self, process_exited=True, late_output=False):
        self.process_exited = process_exited
        self.late_output = late_output


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        request = c1a_request(self.stack.fixture)
        decision = self.stack.policy.consult(request, self.stack.mission)
        self.binding = self.stack.auth.create_binding(
            decision=decision, request=request, run_id="run-1",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.orch = C1ALifecycleOrchestrator()

    def _advance_to_running(self):
        record = self.orch.create_for_binding(self.binding)
        self.orch.bind_workload(record, 4321, "1", "/cgroup/c1a")
        self.orch.start(record)
        self.orch.initiate_teardown(record)
        return record

    def test_full_direct_lifecycle(self):
        record = self.orch.create_for_binding(self.binding)
        self.assertIs(record.state, LifecycleState.SANDBOX_BOUND)
        self.orch.bind_workload(record, 4321, "1", "/cgroup/c1a")
        self.assertIs(record.state, LifecycleState.WORKLOAD_BOUND)
        self.orch.start(record)
        self.assertIs(record.state, LifecycleState.RUNNING)
        self.orch.initiate_teardown(record)
        self.assertIs(record.state, LifecycleState.TEARDOWN_INITIATED)
        self.orch.observe_teardown_direct(record, "/tmp/m5.json", SHA)
        self.assertIs(record.state, LifecycleState.TEARDOWN_OBSERVED)

    def test_teardown_is_host_owned(self):
        record = self._advance_to_running()
        # A transport that did not observe exit cannot advance teardown.
        advanced = self.orch.observe_teardown_from_transport(
            record, _FakeTransport(process_exited=False),
            "/tmp/m5.json", SHA)
        self.assertFalse(advanced)
        self.assertIs(record.state, LifecycleState.TEARDOWN_INITIATED)

    def test_late_output_blocks_teardown_advance(self):
        record = self._advance_to_running()
        advanced = self.orch.observe_teardown_from_transport(
            record, _FakeTransport(process_exited=True, late_output=True),
            "/tmp/m5.json", SHA)
        self.assertFalse(advanced)
        self.assertIs(record.state, LifecycleState.TEARDOWN_INITIATED)

    def test_close_requires_m5(self):
        record = self._advance_to_running()
        self.orch.observe_teardown_direct(record, "/tmp/m5.json", SHA)
        with self.assertRaises(C1ALifecycleError):
            self.orch.close(record)

    def test_foreign_lifecycle_rejected(self):
        record = self.orch.create("L-other", "PS-1")
        with self.assertRaises(C1ALifecycleError):
            self.orch.assert_binding(record, self.binding)

    def test_illegal_transition_rejected(self):
        record = self.orch.create_for_binding(self.binding)
        # start() before bind_workload() is impossible.
        with self.assertRaises(C1ALifecycleError):
            self.orch.start(record)

    def test_m5_without_authority_fails_closed(self):
        record = self._advance_to_running()
        with self.assertRaises(C1ALifecycleError):
            self.orch.observe_teardown_m5(
                record, m5_evidence={}, reference="/tmp/x", sha256=SHA,
                observation=None)

    def test_bad_teardown_digest_rejected(self):
        record = self._advance_to_running()
        with self.assertRaises(C1ALifecycleError):
            self.orch.observe_teardown_direct(record, "/tmp/m5.json", "nothex")


if __name__ == "__main__":
    unittest.main()
