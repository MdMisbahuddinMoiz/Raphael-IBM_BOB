"""tests.test_c1a_replay — lineage, replay, and staleness guards."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.c1a_replay import (  # noqa: E402
    C1AReplayError,
    C1AReplayGuard,
    compute_lineage_hash,
    lineage_integrity_ok,
    new_lineage,
)

FIXTURE_HASH = "a" * 64


def _lineage(run_id="run-1", invocation_id="INV-1", sandbox_id="SBOX-1",
             fixture_sha256=FIXTURE_HASH):
    return new_lineage(
        run_id=run_id, invocation_id=invocation_id,
        proof_session_id="PS-1", sandbox_id=sandbox_id,
        fixture_path="/fixture/sink.bin", fixture_sha256=fixture_sha256)


class LineageIntegrity(unittest.TestCase):
    def test_lineage_hash_matches(self):
        lineage = _lineage()
        self.assertTrue(lineage_integrity_ok(lineage))
        self.assertEqual(
            lineage.lineage_hash,
            compute_lineage_hash(
                run_id=lineage.run_id, invocation_id=lineage.invocation_id,
                proof_session_id=lineage.proof_session_id,
                sandbox_id=lineage.sandbox_id,
                fixture_path=lineage.fixture_path,
                fixture_sha256=lineage.fixture_sha256,
                parent_lineage_hash=lineage.parent_lineage_hash))

    def test_tampered_lineage_fails(self):
        lineage = _lineage()
        tampered = type(lineage)(
            run_id="other", invocation_id=lineage.invocation_id,
            proof_session_id=lineage.proof_session_id,
            sandbox_id=lineage.sandbox_id, fixture_path=lineage.fixture_path,
            fixture_sha256=lineage.fixture_sha256,
            parent_lineage_hash=lineage.parent_lineage_hash,
            lineage_hash=lineage.lineage_hash)
        self.assertFalse(lineage_integrity_ok(tampered))


class ReplayGuard(unittest.TestCase):
    def setUp(self):
        self.guard = C1AReplayGuard()

    def test_register_and_replay_rejected(self):
        self.guard.register(_lineage())
        with self.assertRaises(C1AReplayError):
            self.guard.register(_lineage())
        self.assertTrue(self.guard.is_registered("INV-1"))

    def test_cross_run_substitution_rejected(self):
        self.guard.register(_lineage(run_id="run-1"))
        with self.assertRaises(C1AReplayError):
            self.guard.register(_lineage(run_id="run-2"))

    def test_tampered_lineage_rejected(self):
        lineage = _lineage()
        tampered = type(lineage)(
            run_id=lineage.run_id, invocation_id=lineage.invocation_id,
            proof_session_id=lineage.proof_session_id,
            sandbox_id=lineage.sandbox_id, fixture_path=lineage.fixture_path,
            fixture_sha256=lineage.fixture_sha256,
            parent_lineage_hash=lineage.parent_lineage_hash,
            lineage_hash="0" * 64)
        with self.assertRaises(C1AReplayError):
            self.guard.register(tampered)

    def test_check_receipt_ok(self):
        receipt = _lineage().to_dict()
        ok, reason = self.guard.check_receipt(
            receipt, expected_run_id="run-1",
            current_fixture_sha256=FIXTURE_HASH)
        self.assertTrue(ok, reason)

    def test_check_receipt_cross_run(self):
        receipt = _lineage().to_dict()
        ok, reason = self.guard.check_receipt(receipt, expected_run_id="run-2")
        self.assertFalse(ok)
        self.assertEqual(reason, "cross-run-substitution")

    def test_check_receipt_stale(self):
        receipt = _lineage().to_dict()
        ok, reason = self.guard.check_receipt(
            receipt, expected_run_id="run-1",
            current_fixture_sha256="b" * 64)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("stale-receipt"))

    def test_check_receipt_malformed(self):
        ok, reason = self.guard.check_receipt(
            {"run_id": "run-1"}, expected_run_id="run-1")
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("missing-field"))


if __name__ == "__main__":
    unittest.main()
