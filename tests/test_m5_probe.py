"""tests.test_m5_probe — M5 teardown evidence validation (fail-closed).

Validates the committed M5 evidence: delegated child cgroup teardown via
cgroup.kill, independently observed populated=0, PID/starttime anti-reuse,
and explicit leftover-process classification. No execution; no provider.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

EVIDENCE = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
            "phase-2c-m5" / "m5-evidence.json")
PROBE_IDS = ("M5-P1", "M5-P2", "M5-P3", "M5-P4", "M5-P5", "M5-P6", "M5-P7")


class M5Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(EVIDENCE.read_text())

    def test_1_covers_all_probe_families(self):
        ids = {r["probe_id"] for r in self.d["records"]}
        for probe in PROBE_IDS:
            self.assertIn(probe, ids)

    def test_2_no_failures_and_probed_pass(self):
        self.assertEqual(self.d["fail"], 0)
        self.assertEqual(self.d["fails"], [])
        self.assertEqual(self.d["final_status"], "PROBED_PASS")
        self.assertEqual(self.d["pass"], self.d["total"])

    def test_3_events_before_populated_one(self):
        self.assertIn("populated 1", self.d["teardown"]["events_before"])

    def test_4_populated_zero_independently_established(self):
        self.assertIn("populated 0", self.d["teardown"]["events_after"])
        self.assertIsNotNone(self.d["teardown"]["populated_zero_after_polls"])

    def test_5_pid_starttime_antireuse(self):
        t = self.d["tracked"]
        p = self.d["post_kill"]
        self.assertIsInstance(t["pid"], int)
        self.assertTrue(t["starttime"])
        if p["pid_after"] == "PRESENT":
            self.assertEqual(p["state_after"], "Z")          # zombie => terminated
            self.assertEqual(p["starttime_after"], t["starttime"])
            self.assertTrue(p["same_process"])
        self.assertTrue(p["target_terminated"])

    def test_6_leftover_process_classified(self):
        lo = self.d["leftover"]
        self.assertIn(lo["observation"], ("CONFIRMED_ABSENT", "CONFIRMED_PRESENT"))
        self.assertFalse(lo["target_live"])
        self.assertTrue(lo["holders_expected"])              # holder intentionally alive

    def test_7_cleanup_and_integrity(self):
        self.assertTrue(self.d["cleanup"]["child_rmdir"])
        self.assertTrue(self.d["cleanup"]["scope_gone"])
        self.assertTrue(self.d["no_provider_execution"])
        for r in self.d["records"]:
            self.assertIn(r["status"], ("PASS", "FAIL", "BLOCKED"))
            self.assertIn(r["classification"], ("DIRECT", "INFERRED", "BLOCKED", "UNVERIFIED"))
            self.assertTrue(r["evidence"])


if __name__ == "__main__":
    unittest.main()
