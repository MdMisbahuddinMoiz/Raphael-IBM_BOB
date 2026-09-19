"""tests.test_live_proof_gate — live proof is BLOCKED (CORRECTION 5)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    ProviderUnavailableError,
    T3MP3STAdapter,
)
from scripts import c1a_live_proof  # noqa: E402
from scripts.c1a_live_proof import evaluate, main  # noqa: E402


class LiveProofGate(unittest.TestCase):
    def test_default_is_blocked(self):
        result = evaluate()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["live_proof_authorized"])

    def test_provider_is_unavailable(self):
        result = evaluate()
        self.assertIn("UNAVAILABLE", result["provider_status"])
        self.assertIn("t3mp3st_provider_present", result["blockers"])

    def test_authorization_flag_default_false(self):
        self.assertFalse(c1a_live_proof.LIVE_PROOF_AUTHORIZED)

    def test_no_m1_m2_m5_claims(self):
        result = evaluate()
        for key in ("m1_status", "m2_status", "m5_status"):
            self.assertEqual(result[key], "NOT_EXECUTED")
        self.assertFalse(result["claims"]["provider_executed"])
        self.assertFalse(result["claims"]["mission_complete"])
        self.assertFalse(result["claims"]["verified"])

    def test_even_if_authorized_provider_still_blocks(self):
        result = evaluate(authorized=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(result["live_proof_authorized"])

    def test_adapter_still_fails_closed(self):
        with self.assertRaises(ProviderUnavailableError):
            T3MP3STAdapter().invoke(None, None)

    def test_main_returns_blocked_exit_code(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
