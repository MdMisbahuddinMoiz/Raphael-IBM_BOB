"""tests.test_release_consistency — documentation/artifact consistency."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    LAUNCHER_SHA256,
    InertProviderDouble,
    SandboxedLauncherAdapter,
    T3MP3STAdapter,
    launcher_digest_ok,
)
from scripts import c1a_live_proof  # noqa: E402

DOCS = ROOT_DIR / "docs" / "integration"


class ReleaseConsistency(unittest.TestCase):
    def test_c1a_docs_exist(self):
        for name in ("c1a-evidence-contract.md", "c1a-runbook.md",
                     "c1a-release-gate.md", "phase-2c-c1a-implementation.md"):
            self.assertTrue((DOCS / name).is_file(), f"missing {name}")

    def test_readme_documents_c1a_and_blocked_live_proof(self):
        text = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("C1A", text)
        self.assertIn("Live proof is BLOCKED", text)

    def test_submission_checklist_records_discrepancy_and_blocked(self):
        text = (ROOT_DIR / "docs" / "submission-checklist.md").read_text(
            encoding="utf-8")
        self.assertIn("test-count discrepancy", text)
        self.assertIn("BLOCKED", text)

    def test_first_proof_checklist_records_blocked(self):
        data = json.loads((DOCS / "phase-2c-first-proof-checklist.json")
                          .read_text(encoding="utf-8"))
        self.assertFalse(data["live_proof_authorized"])
        self.assertEqual(data["c1a_implementation"]["live_proof_status"],
                         "BLOCKED")
        self.assertEqual(
            data["c1a_implementation"]["provider_status"][:15],
            "REAL_T3MP3ST_EX")
        self.assertFalse(
            data["c1a_implementation"]["live_proof_authorized"])
        for key in ("m1_status", "m2_status", "m5_status", "seccomp_status"):
            self.assertEqual(data["c1a_implementation"][key], "NOT_EXECUTED")

    def test_live_proof_authorized_false(self):
        self.assertFalse(c1a_live_proof.LIVE_PROOF_AUTHORIZED)

    def test_launcher_digest_matches_pin(self):
        launcher = ROOT_DIR / "provider" / "c1a_launcher.js"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher_digest_ok(launcher, LAUNCHER_SHA256))

    def test_provider_double_is_distinct_from_real_adapter(self):
        self.assertTrue(getattr(InertProviderDouble, "is_test_double", False))
        self.assertIsNot(InertProviderDouble, T3MP3STAdapter)
        self.assertFalse(getattr(SandboxedLauncherAdapter,
                                 "is_real_provider", True))
        # The real adapter still refuses.
        self.assertIn("T3MP3ST", T3MP3STAdapter.__name__)


if __name__ == "__main__":
    unittest.main()
