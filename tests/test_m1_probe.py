"""tests.test_m1_probe — M1 containment evidence validation (fail-closed).

Validates the committed M1 evidence artifact: coverage of all 16 probe
families, per-record evidence, zero failures, and — F1 correction — that the
frozen probe argv matches the CURRENT ``build_bwrap_argv`` output (151 tokens),
not the superseded 131-token builder. No execution of T3MP3ST; the sandbox is
not launched here.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from raphael_ibm_bob.isolation_substrate import (
    FixtureRef, ProviderRef, SandboxSpec, build_bwrap_argv, NODE_RUNTIME)

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "integration" / "phase-2c-m1" / "m1-evidence.json"

PROBE_IDS = ("M1-P1", "M1-P2", "M1-P3", "M1-P4", "M1-P5", "M1-P6", "M1-P7",
             "M1-P8", "M1-P9", "M1-P10", "M1-P11", "M1-P12", "M1-P13",
             "M1-P14", "M1-P15", "M1-P16")

AUDITED_BPF = "d1574a64643907e6c95ccafbfc74e7f04977781014ade214011e57994cb65242"
AUDITED_ALLOWLIST = "8a7efc6f4d11bea59b60a9099dd88e287b8f46f300ba158befd6c922fb0ddaf2"
FIXTURE_SHA = "c033fda6e893ed965de8496ad170628d33ce69817c6ad05bbb63bcb5e1010bd1"


def _current_builder_spec():
    return SandboxSpec(
        provider=ProviderRef(root="/home/moiz/audit-repos/T3MP3ST",
                             node_modules="/home/moiz/audit-repos/T3MP3ST/node_modules"),
        fixture=FixtureRef(root=str(REPO / "fixtures" / "c1a_proof"),
                           path=str(REPO / "fixtures" / "c1a_proof" /
                                    "raphael_c1a_fixture.txt"),
                           sha256=FIXTURE_SHA))


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
        self.assertEqual(f["bpf_sha256"], AUDITED_BPF)
        self.assertEqual(f["allowlist_sha256"], AUDITED_ALLOWLIST)
        self.assertEqual(f["builder_argv_len"], 151)
        self.assertEqual(f["scratch_mode"], "NO_SCRATCH")
        self.assertEqual(f["uid_gid"], ["65534", "65534"])
        self.assertEqual(f["cap_drop"], "ALL")
        self.assertEqual(f["seccomp_fd"], "3")

    def test_5_probe_argv_matches_current_builder(self):
        """F1 regression: the frozen probe argv IS the current builder output."""
        f = self.d["freeze"]
        builder = list(build_bwrap_argv(_current_builder_spec(), seccomp_fd=3))
        self.assertEqual(len(builder), 151)
        self.assertEqual(f["builder_argv_len"], len(builder))
        recorded = hashlib.sha256("\0".join(builder).encode("utf-8")).hexdigest()
        self.assertEqual(f["builder_argv_sha256"], recorded)
        self.assertEqual(f["probe_argv_len"], len(builder) + 1)
        self.assertTrue(builder[-2].endswith("/node"))

    def test_6_argv_recapture_provenance(self):
        rc = self.d["freeze"]["argv_recapture"]
        self.assertEqual(rc["historical_builder_argv_len"], 131)
        self.assertEqual(rc["current_builder_argv_len"], 151)
        self.assertEqual(rc["delta_tokens"], 20)
        self.assertIn("--unsetenv", rc["delta"])

    def test_7_sensitive_devices_absent_or_unreadable(self):
        self.assertEqual(self.d["observations"]["dev_raw_readable"], [])

    def test_8_fail_closed_no_bare_pass(self):
        for r in self.d["records"]:
            if r["status"] == "PASS":
                self.assertTrue(r["evidence"], r["probe_id"])

    def test_9_argv_carries_the_ten_proxy_unsetenv_pairs(self):
        """The current builder (and thus the probe) unsets 10 proxy vars."""
        builder = list(build_bwrap_argv(_current_builder_spec(), seccomp_fd=3))
        self.assertEqual(builder.count("--unsetenv"), 10)


if __name__ == "__main__":
    unittest.main()
