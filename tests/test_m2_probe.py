"""tests.test_m2_probe — M2 egress evidence validation (fail-closed).

Validates the committed M2 evidence: coverage, no successful egress, correct
classification, and that the PARTIAL result is not overclaimed. No execution.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

EVIDENCE = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
            "phase-2c-m2" / "m2-evidence.json")

PROBE_IDS = ("M2-P1", "M2-P2", "M2-P3", "M2-P4", "M2-P5", "M2-P6", "M2-P7",
             "M2-P8", "M2-P9", "M2-P10", "M2-P11", "M2-P12", "M2-P13")


class M2Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(EVIDENCE.read_text())

    def test_1_covers_all_probe_families(self):
        ids = {r["probe_id"] for r in self.d["records"]}
        for probe in PROBE_IDS:
            self.assertIn(probe, ids)

    def test_2_no_failures_and_no_successful_egress(self):
        self.assertEqual(self.d["fail"], 0)
        self.assertEqual(self.d["fails"], [])
        self.assertTrue(self.d["no_successful_egress"])

    def test_3_primitives_have_evidence_and_classification(self):
        for r in self.d["records"]:
            self.assertIn(r["status"], ("PASS", "FAIL", "BLOCKED"))
            self.assertIn(r["classification"], ("DIRECT", "INFERRED", "UNVERIFIED"))
            self.assertTrue(r["evidence"])

    def test_4_partial_reported_not_overclaimed(self):
        self.assertEqual(self.d["final_status"], "PARTIAL")
        self.assertGreaterEqual(self.d["blocked"], 1)
        self.assertIn("M2-P12", self.d["blocked_probes"])

    def test_5_freeze_matches_audited_construction(self):
        f = self.d["freeze"]
        self.assertEqual(
            f["bpf_sha256"],
            "d1574a64643907e6c95ccafbfc74e7f04977781014ade214011e57994cb65242")
        self.assertEqual(f["builder_argv_len"], 131)
        self.assertEqual(f["scratch_mode"], "NO_SCRATCH")
        self.assertTrue(f["unshare_net"])
        self.assertEqual(f["uid_gid"], ["65534", "65534"])

    def test_6_no_interface_beyond_loopback(self):
        self.assertEqual(self.d["observations"]["interfaces"], ["lo"])


if __name__ == "__main__":
    unittest.main()
