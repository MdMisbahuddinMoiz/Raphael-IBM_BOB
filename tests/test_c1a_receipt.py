"""tests.test_c1a_receipt — launcher receipt integrity and closed schema.

CORRECTION 4: the launcher adapter is NOT T3MP3ST. The real provider is
absent; these tests exercise the pinned launcher only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import c1a_request, cleanup, make_stack  # noqa: E402
from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    LAUNCHER_SHA256,
    LauncherIntegrityError,
    ProviderUnavailableError,
    SandboxedLauncherAdapter,
)
from raphael_ibm_bob.c1a_evidence import (  # noqa: E402
    evidence_implies_complete,
    evidence_implies_verified,
)
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    ProviderState,
    invoke_governed,
)


class LauncherReceipt(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        self.request = c1a_request(self.stack.fixture)
        decision = self.stack.policy.consult(self.request, self.stack.mission)
        self.binding = self.stack.auth.create_binding(
            decision=decision, request=self.request, run_id="run-1",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.handoff = self.binding.handoff

    def test_pinned_launcher_produces_success(self):
        adapter = SandboxedLauncherAdapter()
        result = invoke_governed(adapter, self.handoff, self.request)
        self.assertIs(result.state, ProviderState.SUCCESS)
        self.assertTrue(result.success)
        self.assertEqual(result.invocation_id, self.handoff.invocation_id)

    def test_receipt_paths_equal_fixture(self):
        adapter = SandboxedLauncherAdapter()
        result = invoke_governed(adapter, self.handoff, self.request)
        for item in result.results:
            self.assertEqual(item["path"], self.handoff.fixture_path)

    def test_receipt_has_no_authority_keys(self):
        adapter = SandboxedLauncherAdapter()
        result = invoke_governed(adapter, self.handoff, self.request)
        for key in ("verified", "refuted", "complete", "verdict", "gate",
                    "authorized", "severity", "confidence"):
            self.assertNotIn(key, result.to_dict())

    def test_launcher_digest_mismatch_fails_closed(self):
        adapter = SandboxedLauncherAdapter(expected_sha256="0" * 64)
        with self.assertRaises(LauncherIntegrityError):
            adapter.invoke(self.handoff, self.request)

    def test_missing_launcher_fails_closed(self):
        adapter = SandboxedLauncherAdapter(launcher_path="/no/such/launcher.js")
        with self.assertRaises(ProviderUnavailableError):
            adapter.invoke(self.handoff, self.request)

    def test_provider_output_cannot_verify_or_complete(self):
        adapter = SandboxedLauncherAdapter()
        result = invoke_governed(adapter, self.handoff, self.request)
        payload = result.to_dict()
        self.assertFalse(evidence_implies_verified(payload))
        self.assertFalse(evidence_implies_complete(payload))

    def test_launcher_pin_constant_is_nonempty_hex64(self):
        self.assertEqual(len(LAUNCHER_SHA256), 64)
        int(LAUNCHER_SHA256, 16)


if __name__ == "__main__":
    unittest.main()
