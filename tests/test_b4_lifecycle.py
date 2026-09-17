"""tests.test_b4_lifecycle — B4-LIFECYCLE fail-closed tests."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from raphael_ibm_bob.b4_attestation import AttestationStatus
from raphael_ibm_bob.b4_lifecycle import (
    LifecycleError, LifecycleRecord, LifecycleState, attest_lifecycle,
    bind_m5_teardown)

M5 = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
      "phase-2c-m5" / "m5-evidence.json")


def _m5():
    return json.loads(M5.read_text()), str(M5), hashlib.sha256(M5.read_bytes()).hexdigest()


def _full(rec=None):
    rec = rec or LifecycleRecord.create("lc-1", "ps-1")
    rec.bind_sandbox("sbx-1")
    rec.bind_workload(4242, "123456789", "/sys/fs/cgroup/.../raphael-child")
    rec.start()
    rec.initiate_teardown()
    return rec


class LifecycleConstruction(unittest.TestCase):
    def test_1_valid_construction_and_progression(self):
        rec = LifecycleRecord.create("lc-1", "ps-1")
        rec.bind_sandbox("sbx-1")
        rec.bind_workload(1, "100", "/c")
        rec.start(); rec.initiate_teardown()
        rec.observe_teardown("ref", "a" * 64)
        rec.close()
        self.assertEqual(rec.state, LifecycleState.CLOSED)

    def test_2_missing_identity_rejected(self):
        with self.assertRaises(LifecycleError):
            LifecycleRecord.create("", "ps-1")
        with self.assertRaises(LifecycleError):
            LifecycleRecord.create("lc", "")

    def test_3_impossible_transition_rejected(self):
        rec = LifecycleRecord.create("lc", "ps")
        with self.assertRaises(LifecycleError):
            rec.start()                       # skip SANDBOX_BOUND/WORKLOAD_BOUND
        rec.bind_sandbox("s")
        with self.assertRaises(LifecycleError):
            rec.initiate_teardown()           # skip WORKLOAD_BOUND/RUNNING

    def test_4_mismatched_sandbox_identity(self):
        rec = LifecycleRecord.create("lc", "ps")
        rec.bind_sandbox("sbx-A")
        with self.assertRaises(LifecycleError):
            rec.bind_sandbox("sbx-B")

    def test_5_invalid_workload_identity_each(self):
        for pid, st, cg in ((0, "1", "/c"), (-1, "1", "/c"), (True, "1", "/c"), (5, "", "/c"), (5, "1", "")):
            rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
            with self.assertRaises(LifecycleError):
                rec.bind_workload(pid, st, cg)

    def test_6_teardown_requires_evidence(self):
        rec = _full()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("ref", "short")
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("", "a" * 64)

    def test_7_premature_closure_rejected(self):
        rec = _full()
        with self.assertRaises(LifecycleError):
            rec.close()

    def test_8_authority_smuggling_rejected(self):
        from raphael_ibm_bob.b4_lifecycle import _reject_authority
        for key in ("live_proof_authorized", "provider_success", "mission_complete",
                    "quality_gate_complete", "execution_authorized"):
            with self.assertRaises(LifecycleError):
                _reject_authority({"nested": [{"x": {key: True}}]}, "test")

    def test_9_serialization_roundtrip_and_integrity(self):
        rec = _full(); rec.observe_teardown("ref", "a" * 64); rec.close()
        d = rec.to_dict()
        back = LifecycleRecord.from_dict(d)
        self.assertEqual(back.state, LifecycleState.CLOSED)
        bad = dict(d); bad["pid"] = 999
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(bad)


class LifecycleEvidenceAndAttestation(unittest.TestCase):
    def test_10_m5_backed_teardown_closure(self):
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc-m5", "ps-m5")
        rec.bind_sandbox("sbx-m5")
        rec.bind_workload(t["pid"], str(t["starttime"]), "/sys/fs/cgroup/.../raphael-child")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref + "#teardown", sha)
        rec.close()
        res = attest_lifecycle(rec, m5_evidence=ev, m5_reference=ref)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)
        self.assertFalse(res.evidence["provider_executed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")

    def test_11_m5_identity_mismatch_rejected(self):
        ev, ref, sha = _m5()
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(99999999, "1", "/c"); rec.start(); rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, sha)

    def test_12_m5_missing_populated_zero_not_bindable(self):
        ev, ref, sha = _m5()
        bad = json.loads(json.dumps(ev))
        bad["teardown"]["events_after"] = "populated 1"
        rec = _full()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, bad, ref, sha)

    def test_13_attestation_fails_without_bindings(self):
        rec = LifecycleRecord.create("lc", "ps")
        res = attest_lifecycle(rec)
        self.assertIs(res.status, AttestationStatus.INVALID)
        for name in ("sandbox-identity-bound", "workload-identity-bound",
                     "teardown-evidence-present", "closure-after-teardown"):
            self.assertIn(name, res.failures)

    def test_14_attestation_never_claims_provider_or_gate(self):
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(t["pid"], str(t["starttime"]), "/c")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref, sha); rec.close()
        res = attest_lifecycle(rec, m5_evidence=ev)
        blob = json.dumps(res.to_dict()).lower()
        for forbidden in ("provider_success", "mission_complete",
                          "quality_gate_complete", "execution_authorized"):
            self.assertNotIn(forbidden, blob)
        self.assertFalse(res.evidence["live_proof"])
        self.assertFalse(res.evidence["provider_executed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")


if __name__ == "__main__":
    unittest.main()
