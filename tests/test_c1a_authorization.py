"""tests.test_c1a_authorization — C1A authorization binding (CORRECTION 1).

Proves that the authorization binding covers the COMPLETE authoritative
identity and that creation and verification use one canonical payload.
"""
from __future__ import annotations

import hashlib
import hmac
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    DEFAULT_TIMEOUT,
    c1a_request,
    cleanup,
    make_stack,
)
from raphael_ibm_bob.c1a_authorization import (  # noqa: E402
    BINDING_FIELDS,
    C1AAuthorizationBinding,
    C1AAuthorizationError,
    binding_payload,
)
from raphael_ibm_bob.contracts import (  # noqa: E402
    Capability,
    Decision,
    PolicyDecision,
)


def _allow(sequence, target):
    return PolicyDecision(
        sequence=sequence, decision=Decision.ALLOW, reason="ok",
        capability=Capability.C1A_STATIC_FILE_INSPECT, target=str(target))


def _deny(sequence, target):
    return PolicyDecision(
        sequence=sequence, decision=Decision.DENY, reason="no",
        capability=Capability.C1A_STATIC_FILE_INSPECT, target=str(target))


class BindingCreation(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        self.binding = C1AAuthorizationBinding()
        self.decision = _allow(1, self.stack.fixture)
        self.request = c1a_request(self.stack.fixture, sequence=1)

    def _create(self, **over):
        kwargs = dict(
            decision=self.decision, request=self.request, run_id="run-1",
            mission_id="M-c1a",
            workspace_root=str(self.stack.root),
            timeout_seconds=DEFAULT_TIMEOUT)
        kwargs.update(over)
        return self.binding.create_binding(**kwargs)

    def test_valid_allow_creates_binding(self):
        b = self._create()
        self.assertEqual(b.decision_seq, 1)
        self.assertEqual(b.request_seq, 1)
        self.assertEqual(b.target, str(self.stack.fixture))
        self.assertTrue(b.invocation_id.startswith("INV-"))
        self.assertTrue(b.proof_session_id.startswith("PROOF-"))
        self.assertTrue(b.lifecycle_id.startswith("LIFE-"))
        self.assertTrue(b.sandbox_id.startswith("SBOX-"))
        self.assertEqual(b.handoff.fixture_path, str(self.stack.fixture))

    def test_deny_decision_rejected(self):
        with self.assertRaises(C1AAuthorizationError):
            self._create(decision=_deny(1, self.stack.fixture))

    def test_non_c1a_capability_rejected(self):
        from raphael_ibm_bob.contracts import ActionRequest
        read_request = ActionRequest(
            sequence=1, requester="c1a", capability=Capability.READ,
            target=str(self.stack.fixture), purpose="c1a-proof",
            timeout_seconds=DEFAULT_TIMEOUT)
        with self.assertRaises(C1AAuthorizationError):
            self._create(request=read_request)

    def test_target_mismatch_rejected(self):
        mismatch = c1a_request(self.stack.other, sequence=1)
        with self.assertRaises(C1AAuthorizationError):
            self._create(request=mismatch)

    def test_relative_target_fails_closed(self):
        rel = c1a_request("fixtures/sink.bin", sequence=1)
        decision = _allow(1, "fixtures/sink.bin")
        with self.assertRaises(C1AAuthorizationError):
            self._create(request=rel, decision=decision)

    def test_target_outside_workspace_rejected(self):
        outside = c1a_request("/etc/hostname", sequence=1)
        decision = _allow(1, "/etc/hostname")
        with self.assertRaises(C1AAuthorizationError):
            self._create(request=outside, decision=decision)

    def test_nonpositive_timeout_rejected(self):
        for bad in (None, 0, -1.0, True):
            with self.assertRaises(C1AAuthorizationError):
                self._create(timeout_seconds=bad)

    def test_replay_of_invocation_rejected(self):
        self._create()
        with self.assertRaises(C1AAuthorizationError):
            self._create()


class CanonicalPayload(unittest.TestCase):
    """CORRECTION 1: creation and verification share ONE payload builder."""

    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        self.binding_obj = C1AAuthorizationBinding()
        self.decision = _allow(1, self.stack.fixture)
        self.request = c1a_request(self.stack.fixture, sequence=1)
        self.binding = self.binding_obj.create_binding(
            decision=self.decision, request=self.request, run_id="run-1",
            mission_id="M-c1a",
            workspace_root=str(self.stack.root),
            timeout_seconds=DEFAULT_TIMEOUT)

    def test_hash_is_over_binding_payload(self):
        expected = hmac.new(
            C1AAuthorizationBinding._BINDING_SECRET,
            binding_payload(**self.binding.identity),
            hashlib.sha256).hexdigest()
        self.assertEqual(self.binding.binding_hash, expected)

    def test_binding_covers_all_identity_fields(self):
        self.assertEqual(set(self.binding.identity), set(BINDING_FIELDS))
        for field in ("run_id", "invocation_id", "proof_session_id",
                      "lifecycle_id", "sandbox_id", "capability_id",
                      "provider_id", "target", "fixture_path"):
            self.assertIn(field, self.binding.identity)

    def test_binding_payload_is_deterministic(self):
        self.assertEqual(binding_payload(**self.binding.identity),
                         binding_payload(**self.binding.identity))

    def test_binding_payload_missing_field_rejected(self):
        bad = dict(self.binding.identity)
        bad.pop("sandbox_id")
        with self.assertRaises(C1AAuthorizationError):
            binding_payload(**bad)


class BindingVerification(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        self.binding_obj = C1AAuthorizationBinding()
        self.decision = _allow(1, self.stack.fixture)
        self.request = c1a_request(self.stack.fixture, sequence=1)
        self.binding = self.binding_obj.create_binding(
            decision=self.decision, request=self.request, run_id="run-1",
            mission_id="M-c1a",
            workspace_root=str(self.stack.root),
            timeout_seconds=DEFAULT_TIMEOUT)
        self.inv = self.binding.invocation_id

    def test_original_binding_verifies(self):
        self.assertTrue(
            self.binding_obj.verify_binding(self.inv, self.decision))

    def test_foreign_decision_fails(self):
        foreign = _allow(999, self.stack.fixture)
        self.assertFalse(self.binding_obj.verify_binding(self.inv, foreign))

    def test_deny_decision_fails(self):
        self.assertFalse(
            self.binding_obj.verify_binding(
                self.inv, _deny(1, self.stack.fixture)))

    def test_unknown_invocation_fails(self):
        self.assertFalse(
            self.binding_obj.verify_binding("INV-nope", self.decision))

    def test_single_use_invalidation(self):
        self.assertTrue(
            self.binding_obj.verify_binding(self.inv, self.decision))
        self.binding_obj.invalidate_binding(self.inv)
        self.assertFalse(
            self.binding_obj.verify_binding(self.inv, self.decision))
        self.assertFalse(self.binding_obj.is_active(self.inv))

    def test_every_modified_identity_field_fails(self):
        mutations = {
            "run_id": "run-other",
            "decision_seq": 42,
            "request_seq": 42,
            "invocation_id": "INV-tampered",
            "proof_session_id": "PROOF-tampered",
            "lifecycle_id": "LIFE-tampered",
            "sandbox_id": "SBOX-tampered",
            "capability_id": "other-cap",
            "provider_id": "decepticon",
            "target": "/etc/passwd",
            "fixture_path": "/etc/passwd",
        }
        for field, value in mutations.items():
            self.assertFalse(
                self.binding_obj.verify_binding(
                    self.inv, self.decision, claimed={field: value}),
                f"modified {field} was not detected")


if __name__ == "__main__":
    unittest.main()
