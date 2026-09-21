"""tests.test_c1a_identity — C1A identity, masquerading, and DENY paths.

CORRECTION 2: C1A is a first-class capability and is never aliased to READ.
CORRECTION 4: the inert provider double is test infrastructure only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    DEFAULT_TIMEOUT,
    CountingInertProvider,
    c1a_request,
    cleanup,
    make_stack,
)
from raphael_ibm_bob.contracts import ActionRequest, Capability, Decision  # noqa: E402
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    ScopeViolation,
    validate_scope,
)


class CapabilityIdentity(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)

    def test_read_cannot_masquerade_as_c1a(self):
        read_request = ActionRequest(
            sequence=1, requester="x", capability=Capability.READ,
            target=str(self.stack.fixture), purpose="p",
            timeout_seconds=DEFAULT_TIMEOUT)
        handoff = self.stack.auth.create_binding(
            decision=self.stack.policy.consult(
                c1a_request(self.stack.fixture), self.stack.mission),
            request=c1a_request(self.stack.fixture), run_id="r",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root),
            timeout_seconds=DEFAULT_TIMEOUT).handoff
        with self.assertRaises(ScopeViolation):
            validate_scope(handoff, read_request)

    def test_c1a_capability_is_distinct_from_read(self):
        self.assertNotEqual(Capability.C1A_STATIC_FILE_INSPECT,
                            Capability.READ)
        self.assertEqual(Capability.C1A_STATIC_FILE_INSPECT.value,
                         "c1a_static_file_inspect")
        self.assertEqual(Capability.READ.value, "read")


class DenyNeverReachesProvider(unittest.TestCase):
    def test_no_decision_c1a_invocation_fails(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=False)
        self.addCleanup(cleanup, stack.root)
        # Target does not exist -> Policy DENY, not an exception.
        result = stack.runtime.submit(
            c1a_request(stack.root / "missing.bin"), stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.broker_result.execution)
        self.assertEqual(provider.calls, 0)

    def test_missing_timeout_denied(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=False)
        self.addCleanup(cleanup, stack.root)
        request = c1a_request(stack.fixture, timeout=None)
        result = stack.runtime.submit(request, stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)
        self.assertEqual(result.broker_result.decision.reason,
                         "c1a-timeout-required")
        self.assertEqual(provider.calls, 0)

    def test_target_outside_workspace_denied(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=False)
        self.addCleanup(cleanup, stack.root)
        result = stack.runtime.submit(
            c1a_request("/etc/hostname"), stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)
        self.assertEqual(provider.calls, 0)


class AuthorizedC1APath(unittest.TestCase):
    def test_authorized_c1a_reaches_provider_once(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        result = stack.runtime.submit(
            c1a_request(stack.fixture), stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertEqual(provider.calls, 1)
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        self.assertTrue(result.execution.evidence["provider_untrusted"])

    def test_provider_evidence_is_labelled_untrusted(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.runtime.submit(c1a_request(stack.fixture), stack.mission)
        provider_records = [
            r for r in stack.ledger.all_records()
            if r.get("producer") == "provider"
        ]
        self.assertTrue(provider_records)
        for rec in provider_records:
            self.assertTrue(rec["payload"]["provider_untrusted"])

    def test_binding_is_single_use_after_invocation(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.runtime.submit(c1a_request(stack.fixture), stack.mission)
        # No active bindings remain after execution.
        self.assertEqual(stack.auth.active_invocations(), ())


if __name__ == "__main__":
    unittest.main()
