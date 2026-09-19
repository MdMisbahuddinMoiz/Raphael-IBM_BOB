"""tests.test_b4_lifecycle — B4-LIFECYCLE fail-closed tests (R1-R7).

Covers the corrective closure:

R1 teardown provenance (direct vs m5-bound, serialized, hash-covered)
R2 fail-closed closure (no M5-less CLOSED, no M5-less ATTESTED)
R3 strict boolean M5 fields (no coercion)
R4 atomic rebind (failed rebind leaves state untouched)
R6 file-SHA helper (actual bytes, fail-closed)
R7 regression tests for the historical false-closure attacks

Assertions are on behavior/artifacts (states, transitions, hashes, raised
errors), never on ``PASS`` strings.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.b4_attestation import AttestationStatus
from raphael_ibm_bob.b4_lifecycle import (
    LifecycleError, LifecycleRecord, LifecycleState,
    TEARDOWN_PROVENANCE_DIRECT, TEARDOWN_PROVENANCE_M5_BOUND,
    attest_lifecycle, bind_m5_teardown, sha256_file, verify_file_sha256)

M5 = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
      "phase-2c-m5" / "m5-evidence.json")


def _m5():
    return (json.loads(M5.read_text()), str(M5),
            hashlib.sha256(M5.read_bytes()).hexdigest())


def _full(rec=None):
    """Record advanced to TEARDOWN_INITIATED (no teardown observed yet)."""
    rec = rec or LifecycleRecord.create("lc-1", "ps-1")
    rec.bind_sandbox("sbx-1")
    rec.bind_workload(4242, "123456789", "/sys/fs/cgroup/.../raphael-child")
    rec.start()
    rec.initiate_teardown()
    return rec


def _full_m5(rec=None):
    """Record closed via a real M5 binding."""
    ev, ref, sha = _m5()
    t = ev["tracked"]
    rec = rec or LifecycleRecord.create("lc-m5", "ps-m5")
    rec.bind_sandbox("sbx-m5")
    rec.bind_workload(t["pid"], str(t["starttime"]),
                      "/sys/fs/cgroup/.../raphael-child")
    rec.start()
    rec.initiate_teardown()
    bind_m5_teardown(rec, ev, ref, sha)
    rec.close()
    return rec, ev, ref


class LifecycleConstruction(unittest.TestCase):
    def test_1_valid_construction_and_progression(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)  # direct observation
        self.assertEqual(rec.teardown_provenance, TEARDOWN_PROVENANCE_DIRECT)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)

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
        for pid, st, cg in ((0, "1", "/c"), (-1, "1", "/c"), (True, "1", "/c"),
                            (5, "", "/c"), (5, "1", "")):
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
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        back = LifecycleRecord.from_dict(d)
        self.assertEqual(back.state, LifecycleState.CLOSED)
        self.assertEqual(back.teardown_provenance, TEARDOWN_PROVENANCE_M5_BOUND)
        bad = dict(d); bad["pid"] = 999
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(bad)


class LifecycleEvidenceAndAttestation(unittest.TestCase):
    def test_10_m5_backed_teardown_closure(self):
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc-m5", "ps-m5")
        rec.bind_sandbox("sbx-m5")
        rec.bind_workload(t["pid"], str(t["starttime"]),
                          "/sys/fs/cgroup/.../raphael-child")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref + "#teardown", sha)
        rec.close()
        res = attest_lifecycle(rec, m5_evidence=ev, m5_reference=ref)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)
        self.assertFalse(res.evidence["provider_executed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")
        self.assertEqual(res.evidence["teardown_provenance"],
                         TEARDOWN_PROVENANCE_M5_BOUND)

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
                     "teardown-evidence-present", "closure-after-teardown",
                     "teardown-provenance-m5-bound", "m5-reference-present"):
            self.assertIn(name, res.failures)

    def test_14_attestation_never_claims_provider_or_gate(self):
        rec, ev, ref = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev)
        blob = json.dumps(res.to_dict()).lower()
        for forbidden in ("provider_success", "mission_complete",
                          "quality_gate_complete", "execution_authorized"):
            self.assertNotIn(forbidden, blob)
        self.assertFalse(res.evidence["live_proof"])
        self.assertFalse(res.evidence["provider_executed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")


class TeardownProvenanceR1R2(unittest.TestCase):
    def test_15_direct_teardown_cannot_close(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)          # direct
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)
        with self.assertRaises(LifecycleError):
            rec.close()
        self.assertIsNot(rec.state, LifecycleState.CLOSED)

    def test_16_m5_bound_teardown_can_close(self):
        rec, ev, ref = _full_m5()
        self.assertEqual(rec.state, LifecycleState.CLOSED)

    def test_17_provenance_serialized_and_hash_covered(self):
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        self.assertEqual(tev["provenance"], TEARDOWN_PROVENANCE_M5_BOUND)
        self.assertTrue(tev["m5_reference"])
        self.assertTrue(tev["m5_sha256"])
        # R1: provenance is part of the hashed body.
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        expect = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(d["lifecycle_sha256"], expect)

    def test_18_provenance_tamper_breaks_hash(self):
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["provenance"] = TEARDOWN_PROVENANCE_DIRECT   # flip
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)

    def test_19_m5_unbound_attestation_fails(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)   # direct, cannot close
        res = attest_lifecycle(rec, m5_evidence=None)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("teardown-provenance-m5-bound", res.failures)
        self.assertIn("m5-reference-present", res.failures)

    def test_25_historical_false_closure_attack(self):
        # The exact previously demonstrated attack: observe -> close.
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
        with self.assertRaises(LifecycleError):
            rec.close()
        # A forged direct-provenance CLOSED record (self-consistent hash) is
        # still rejected on deserialization.
        states = ["CREATED", "SANDBOX_BOUND", "WORKLOAD_BOUND", "RUNNING",
                  "TEARDOWN_INITIATED", "TEARDOWN_OBSERVED", "CLOSED"]
        trans = []
        for i, s in enumerate(states):
            t = {"seq": i, "state": s, "at": float(i), "evidence_ref": None,
                 "evidence_sha256": None, "provenance": None,
                 "m5_reference": None, "m5_sha256": None}
            if s == "TEARDOWN_OBSERVED":
                t.update({"evidence_ref": "ref", "evidence_sha256": "a" * 64,
                          "provenance": TEARDOWN_PROVENANCE_DIRECT})
            trans.append(t)
        forged_body = {"lifecycle_id": "lc", "proof_session_id": "ps",
                       "sandbox_id": "s", "pid": 1, "pid_starttime": "1",
                       "cgroup": "/c", "transitions": trans,
                       "scope": "lifecycle_integrity_only"}
        forged = {**forged_body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(forged_body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(forged)


class M5StrictBooleanR3(unittest.TestCase):
    def _bind_with_post(self, mutate):
        ev, ref, sha = _m5()
        mutate(ev)
        rec = _full()
        return rec, ev, ref, sha

    def test_20_strict_target_terminated(self):
        for bad in (1, 0, "true", "false", "True", None, [1]):
            ev, ref, sha = _m5()
            ev["post_kill"]["target_terminated"] = bad
            rec = _full()
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, ref, sha)
        # boolean True is accepted
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(t["pid"], str(t["starttime"]), "/c")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref, sha)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)

    def test_21_strict_no_provider_execution(self):
        for bad in (1, 0, "true", "false", None, []):
            ev, ref, sha = _m5()
            ev["no_provider_execution"] = bad
            rec = _full()
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, ref, sha)
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(t["pid"], str(t["starttime"]), "/c")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref, sha)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)


class AtomicRebindR4(unittest.TestCase):
    def test_22_failed_rebind_is_atomic(self):
        # sandbox mismatch
        rec = LifecycleRecord.create("lc", "ps")
        rec.bind_sandbox("A")
        before = (rec.sandbox_id, len(rec.transitions))
        with self.assertRaises(LifecycleError):
            rec.bind_sandbox("B")
        self.assertEqual((rec.sandbox_id, len(rec.transitions)), before)

        # identity-preserving sandbox rebind is a no-op
        rec.bind_sandbox("A")
        self.assertEqual(len(rec.transitions), 2)

        rec.bind_workload(5, "10", "/c")
        before = (rec.pid, rec.pid_starttime, rec.cgroup, len(rec.transitions))
        for args in ((6, "10", "/c"), (5, "11", "/c"), (5, "10", "/d")):
            with self.assertRaises(LifecycleError):
                rec.bind_workload(*args)
            self.assertEqual(
                (rec.pid, rec.pid_starttime, rec.cgroup, len(rec.transitions)),
                before)
        # identity-preserving workload rebind is a no-op
        rec.bind_workload(5, "10", "/c")
        self.assertEqual(len(rec.transitions), before[3])

    def test_22b_m5_reference_mismatch_and_rebind(self):
        ev, ref, sha = _m5()
        t = ev["tracked"]
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(t["pid"], str(t["starttime"]), "/c")
        rec.start(); rec.initiate_teardown()
        bind_m5_teardown(rec, ev, ref, sha)
        n = len(rec.transitions)
        # rebinding (even with the same ref) is rejected, no mutation
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, sha)
        self.assertEqual(len(rec.transitions), n)
        # wrong digest rejected before mutation
        rec2 = _full()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec2, ev, ref, "nothex")
        self.assertEqual(rec2.state, LifecycleState.TEARDOWN_INITIATED)


class HashTamperingR7(unittest.TestCase):
    def test_23_lifecycle_sha_tampering(self):
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        d["lifecycle_sha256"] = "0" * 64
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)

    def test_24_modified_m5_reference_breaks_hash(self):
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["m5_reference"] = "/some/other/evidence#teardown"
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)


class FileShaHelperR6(unittest.TestCase):
    def test_26_sha256_file_actual_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m5.json"
            p.write_bytes(b"raphael-m5")
            want = hashlib.sha256(b"raphael-m5").hexdigest()
            self.assertEqual(sha256_file(str(p)), want)
            self.assertTrue(verify_file_sha256(str(p), want))
            # wrong expected digest: fail closed
            self.assertFalse(verify_file_sha256(str(p), "0" * 64))
            # malformed expected digest: fail closed
            self.assertFalse(verify_file_sha256(str(p), "deadbeef"))
            # missing file: fail closed
            self.assertFalse(verify_file_sha256(str(Path(td) / "absent"), want))
            with self.assertRaises(LifecycleError):
                sha256_file(str(Path(td) / "absent"))


if __name__ == "__main__":
    unittest.main()
