"""tests.test_m1_probe — M1 containment evidence validation (fail-closed).

Validates the committed M1 evidence artifact: coverage of all 16 probe
families, per-record evidence, zero failures, and that the pre-probe freeze
matched the audited G2 construction. No execution; T3MP3ST is not involved.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

EVIDENCE = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
            "phase-2c-m1" / "m1-evidence.json")

PROBE_IDS = ("M1-P1", "M1-P2", "M1-P3", "M1-P4", "M1-P5", "M1-P6", "M1-P7",
             "M1-P8", "M1-P9", "M1-P10", "M1-P11", "M1-P12", "M1-P13",
             "M1-P14", "M1-P15", "M1-P16")


class M1Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(EVIDENCE.read_text())

    def test_1_covers_all_probe_families(self):
        ids = {r["probe_id"] for r in self.d["records"]}
        for probe in PROBE_IDS:
            self.assertTrue(any(i.startswith(probe) for i in ids), probe)

    def test_2_every_record_has_status_expected_actual_evidence(self):
        for r in self.d["records"]:
            self.assertIn(r["status"], ("PASS", "FAIL"))
            self.assertTrue(r.get("expected"))
            self.assertIsNotNone(r.get("actual"))
            self.assertTrue(r.get("evidence"))

    def test_3_counts_consistent_and_no_failures(self):
        self.assertEqual(self.d["total"], len(self.d["records"]))
        self.assertEqual(self.d["pass"], self.d["total"])
        self.assertEqual(self.d["fail"], 0)
        self.assertEqual(self.d["fails"], [])

    def test_4_freeze_matches_audited_g2_construction(self):
        f = self.d["freeze"]
        self.assertEqual(
            f["bpf_sha256"],
            "d1574a64643907e6c95ccafbfc74e7f04977781014ade214011e57994cb65242")
        self.assertEqual(f["builder_argv_len"], 131)
        self.assertEqual(f["scratch_mode"], "NO_SCRATCH")
        self.assertEqual(f["uid_gid"], ["65534", "65534"])
        self.assertEqual(f["cap_drop"], "ALL")
        self.assertEqual(f["seccomp_fd"], "3")

    def test_5_sensitive_devices_absent_or_unreadable(self):
        self.assertEqual(self.d["observations"]["dev_raw_readable"], [])

    def test_6_fail_closed_no_bare_pass(self):
        for r in self.d["records"]:
            if r["status"] == "PASS":
                self.assertTrue(r["evidence"], r["probe_id"])


if __name__ == "__main__":
    unittest.main()
