"""tests.test_checklist_consistency — Phase 2C checklist identity/schema.

N3: the checklist must use explicit head terminology and must not pretend to
embed its own not-yet-existing commit hash:

    base_head            — the pre-correction base commit
    raphael_semantic_head— the CODE commit the checklist attests to
    checklist_commit     — the commit that contains this checklist revision
                            (self-resolving; cannot embed its own hash)

Also asserts the checklist agrees with the regenerated M1 evidence.
No provider invocation; no live proof.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CL = REPO / "docs" / "integration" / "phase-2c-first-proof-checklist.json"
M1 = REPO / "docs" / "integration" / "phase-2c-m1" / "m1-evidence.json"

BASE_HEAD = "780f9bd99cf5973d61b1eba03316a30175202fac"
PREVIOUS_CORRECTION = "f72e4d6e033d2e5b7166f5d6ec26e00552827195"


class ChecklistSchemaN3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(CL.read_text())

    def test_1_explicit_head_terminology(self):
        for key in ("base_head", "raphael_semantic_head", "checklist_commit"):
            self.assertIn(key, self.d, key)
        # the old ambiguous field must be gone
        self.assertNotIn("raphael_head", self.d)

    def test_2_base_head_value(self):
        self.assertEqual(self.d["base_head"], BASE_HEAD)

    def test_3_semantic_head_is_a_commit_not_self(self):
        head = self.d["raphael_semantic_head"]
        self.assertIsInstance(head, str)
        self.assertEqual(len(head), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in head))
        self.assertNotEqual(head, "893494149")

    def test_4_checklist_commit_is_self_resolving(self):
        value = self.d["checklist_commit"]
        self.assertIsInstance(value, str)
        # honest self-resolution instruction (cannot embed its own hash)
        self.assertIn("self", value.lower())
        self.assertIn("phase-2c-first-proof-checklist.json", value)

    def test_5_no_legacy_stale_hash(self):
        blob = json.dumps(self.d)
        self.assertNotIn('"raphael_head": "893494149"', blob)

    def test_6_live_proof_not_authorized(self):
        self.assertIs(self.d["live_proof_authorized"], False)
        self.assertEqual(self.d["readiness_stage"]["live_proof"], "NOT_READY")


class ChecklistMilestones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(CL.read_text())
        cls.status = {i["id"]: i["status"] for i in cls.d["items"]}

    def test_7_milestones_probed_pass(self):
        self.assertEqual(self.status["M1"], "PROBED_PASS")
        self.assertEqual(self.status["M2"], "PROBED_PASS")
        self.assertEqual(self.status["M5"], "PROBED_PASS")

    def test_8_c1a_transport_not_ready(self):
        self.assertEqual(self.status["C1A-TRANSPORT"], "NOT_READY")

    def test_9_b4_lifecycle_recorded(self):
        self.assertEqual(self.status["B4-LIFECYCLE"],
                         "IMPLEMENTED_NOT_PROVIDER_VERIFIED")
        blob = json.dumps(self.d)
        self.assertIn("R1-R7", blob)


class ChecklistM1Agreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(CL.read_text())
        cls.m1 = json.loads(M1.read_text())

    def test_10_m1_hash_matches_evidence_file(self):
        sha = hashlib.sha256(M1.read_bytes()).hexdigest()
        self.assertEqual(self.d["m1_evidence"]["sha256"], sha)

    def test_11_m1_argv_freeze_151(self):
        self.assertEqual(self.d["m1_evidence"]["builder_argv_len"], 151)
        self.assertEqual(self.m1["freeze"]["builder_argv_len"], 151)
        self.assertEqual(self.d["m1_evidence"]["builder_argv_sha256"],
                         self.m1["freeze"]["builder_argv_sha256"])

    def test_12_current_builder_argv_length_recorded(self):
        self.assertEqual(self.d["g2_seccomp"]["current_builder_argv_length"], 151)


if __name__ == "__main__":
    unittest.main()
