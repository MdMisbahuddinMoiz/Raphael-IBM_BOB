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

    def test_blocked_while_unauthorized(self):
        result = evaluate()
        self.assertIn("live_proof_authorized", result["blockers"])
        # Even if the provider is present, live proof stays BLOCKED.
        if result["provider_status"] == "AVAILABLE":
            self.assertIn("live_proof_authorized", result["blockers"])

    def test_provider_status_reflects_reality(self):
        result = evaluate()
        self.assertIn(result["provider_status"],
                      {"AVAILABLE", "UNAVAILABLE (external dependency)"})
        if c1a_live_proof.provider_dist_available():
            self.assertEqual(result["provider_status"], "AVAILABLE")

    def test_authorization_flag_default_false(self):
        self.assertFalse(c1a_live_proof.LIVE_PROOF_AUTHORIZED)

    def test_no_m1_m2_m5_claims(self):
        result = evaluate()
        for key in ("m1_status", "m2_status", "m5_status"):
            self.assertEqual(result[key], "NOT_EXECUTED")
        self.assertFalse(result["claims"]["provider_executed"])
        self.assertFalse(result["claims"]["mission_complete"])
        self.assertFalse(result["claims"]["verified"])

    def test_authorized_but_unauthorized_provider_blocks(self):
        # Forcing authorized=True still cannot make live proof READY while
        # the gate's own provider/other prerequisites are unmet, and the
        # claims never flip.
        result = evaluate(authorized=True)
        self.assertTrue(result["live_proof_authorized"])
        self.assertFalse(result["claims"]["provider_executed"])

    def test_adapter_fails_closed_without_provider(self):
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
