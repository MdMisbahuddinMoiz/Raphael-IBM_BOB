"""tests.test_b4_lifecycle — B4-LIFECYCLE fail-closed tests (R1-R7 + B4-1..B4-7).

B4-1 fake M5-bound provenance eliminated (direct-only observe_teardown)
B4-2 M5 evidence authenticated (actual artifact bytes; caller digest alone
     never sufficient)
B4-3 cgroup.events parsed as a field, never substring
B4-4/B4-5 from_dict re-applies append invariants + authentication
B4-6 construction/mutability hardening (read-only transitions; __post_init__)
B4-7 attestation evidence key taxonomy disjoint from FORBIDDEN_AUTHORITY_KEYS

Assertions are on behavior/artifacts, never ``PASS`` strings.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.b4_attestation import AttestationStatus
from raphael_ibm_bob.b4_lifecycle import (
    FORBIDDEN_AUTHORITY_KEYS, LifecycleError, LifecycleRecord, LifecycleState,
    LifecycleTransition, TEARDOWN_PROVENANCE_DIRECT,
    TEARDOWN_PROVENANCE_M5_BOUND, attest_lifecycle, bind_m5_teardown,
    cgroup_populated, sha256_file, verify_file_sha256)

M5 = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
      "phase-2c-m5" / "m5-evidence.json")


def _m5():
    return (json.loads(M5.read_text()), str(M5),
            hashlib.sha256(M5.read_bytes()).hexdigest())


def _copy(ev):
    return json.loads(json.dumps(ev))


def _full(rec=None):
    """Record advanced to TEARDOWN_INITIATED (no teardown observed yet)."""
    rec = rec or LifecycleRecord.create("lc-1", "ps-1")
    rec.bind_sandbox("sbx-1")
    rec.bind_workload(4242, "123456789", "/sys/fs/cgroup/.../raphael-child")
    rec.start()
    rec.initiate_teardown()
    return rec


def _full_for_m5(ev, rec=None):
    """Record advanced to TEARDOWN_INITIATED with M5-matching identity."""
    t = ev["tracked"]
    rec = rec or LifecycleRecord.create("lc-m5", "ps-m5")
    rec.bind_sandbox("sbx-m5")
    rec.bind_workload(t["pid"], str(t["starttime"]),
                      "/sys/fs/cgroup/.../raphael-child")
    rec.start()
    rec.initiate_teardown()
    return rec


def _full_m5(rec=None):
    """Record closed via a real, authenticated M5 binding."""
    ev, ref, sha = _m5()
    rec = _full_for_m5(ev, rec=rec)
    bind_m5_teardown(rec, ev, ref, sha)
    rec.close()
    return rec, ev, ref


def _forged_m5_record():
    """A record whose M5-bound teardown references a non-existent artifact."""
    states = [LifecycleState(i) for i in range(7)]
    trans = []
    for i, s in enumerate(states):
        t = LifecycleTransition(seq=i, state=s, at=float(i))
        if s is LifecycleState.TEARDOWN_OBSERVED:
            t = LifecycleTransition(
                seq=i, state=s, at=float(i),
                evidence_ref="/nonexistent/fake-m5.json#teardown",
                evidence_sha256="b" * 64,
                provenance=TEARDOWN_PROVENANCE_M5_BOUND,
                m5_reference="/nonexistent/fake-m5.json#teardown",
                m5_sha256="b" * 64)
        trans.append(t)
    return LifecycleRecord(
        lifecycle_id="lc-forged", proof_session_id="ps-forged",
        sandbox_id="s", pid=1, pid_starttime="1", cgroup="/c",
        _transitions=trans)


class _ArtifactMixin:
    def write_artifact(self, ev):
        td = tempfile.mkdtemp(prefix="m5art_")
        self.addCleanup(shutil.rmtree, td, True)
        path = os.path.join(td, "m5-evidence.json")
        data = json.dumps(ev).encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        return ev, path, hashlib.sha256(data).hexdigest()


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
            rec.start()
        rec.bind_sandbox("s")
        with self.assertRaises(LifecycleError):
            rec.initiate_teardown()

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
        for key in ("live_proof_authorized", "provider_success",
                    "mission_complete", "quality_gate_complete",
                    "execution_authorized"):
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


class LifecycleEvidenceAndAttestation(unittest.TestCase, _ArtifactMixin):
    def test_10_m5_backed_teardown_closure(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        bind_m5_teardown(rec, ev, ref + "#teardown", sha)
        rec.close()
        res = attest_lifecycle(rec, m5_evidence=ev, m5_reference=ref)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)
        self.assertFalse(res.evidence["provider_execution_observed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")
        self.assertEqual(res.evidence["teardown_provenance"],
                         TEARDOWN_PROVENANCE_M5_BOUND)

    def test_11_m5_identity_mismatch_rejected(self):
        ev, ref, sha = _m5()
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(99999999, "1", "/c"); rec.start()
        rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, sha)

    def test_12_m5_missing_populated_zero_not_bindable(self):
        ev, ref, sha = _m5()
        bad = _copy(ev)
        bad["teardown"]["events_after"] = "populated 1"
        _ev, path, digest = self.write_artifact(bad)
        rec = _full_for_m5(bad)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, bad, path, digest)

    def test_13_attestation_fails_without_bindings(self):
        rec = LifecycleRecord.create("lc", "ps")
        res = attest_lifecycle(rec)
        self.assertIs(res.status, AttestationStatus.INVALID)
        for name in ("sandbox-identity-bound", "workload-identity-bound",
                     "teardown-evidence-present", "closure-after-teardown",
                     "teardown-provenance-m5-bound", "m5-reference-present",
                     "m5-reference-authenticated"):
            self.assertIn(name, res.failures)

    def test_14_attestation_never_claims_provider_or_gate(self):
        rec, ev, ref = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev)
        blob = json.dumps(res.to_dict()).lower()
        for forbidden in ("provider_success", "mission_complete",
                          "quality_gate_complete", "execution_authorized"):
            self.assertNotIn(forbidden, blob)
        self.assertFalse(res.evidence["live_proof_claimed"])
        self.assertFalse(res.evidence["provider_execution_observed"])
        self.assertEqual(res.evidence["scope"], "lifecycle_integrity_only")


class TeardownProvenanceR1R2(unittest.TestCase, _ArtifactMixin):
    def test_15_direct_teardown_cannot_close(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
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
        tev["provenance"] = TEARDOWN_PROVENANCE_DIRECT
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)

    def test_19_m5_unbound_attestation_fails(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
        res = attest_lifecycle(rec, m5_evidence=None)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("teardown-provenance-m5-bound", res.failures)
        self.assertIn("m5-reference-present", res.failures)
        self.assertIn("m5-reference-authenticated", res.failures)

    def test_25_historical_false_closure_attack(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
        with self.assertRaises(LifecycleError):
            rec.close()
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


class B41FakeM5Provenance(unittest.TestCase):
    """The blocking correction: observe_teardown cannot mint M5-bound."""

    def test_27_observe_rejects_m5_bound_provenance(self):
        rec = _full()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown(
                "ref", "a" * 64, provenance=TEARDOWN_PROVENANCE_M5_BOUND,
                m5_reference="/x#teardown", m5_sha256="a" * 64)

    def test_28_observe_rejects_m5_reference_without_provenance(self):
        rec = _full()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown(
                "ref", "a" * 64, m5_reference="/x#teardown",
                m5_sha256="a" * 64)

    def test_29_fake_observe_then_close_not_closed(self):
        rec = _full()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown(
                "ref", "a" * 64, provenance=TEARDOWN_PROVENANCE_M5_BOUND,
                m5_reference="/x#teardown", m5_sha256="a" * 64)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_INITIATED)
        with self.assertRaises(LifecycleError):
            rec.close()
        self.assertIsNot(rec.state, LifecycleState.CLOSED)

    def test_30_direct_observe_attest_never_attested(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
        res = attest_lifecycle(rec)
        self.assertIs(res.status, AttestationStatus.INVALID)

    def test_31_forged_direct_observe_is_not_m5_bound(self):
        rec = _full()
        rec.observe_teardown("ref", "a" * 64)
        self.assertEqual(rec.teardown_provenance, TEARDOWN_PROVENANCE_DIRECT)

    def test_32_legitimate_bind_still_works(self):
        rec, ev, ref = _full_m5()
        self.assertEqual(rec.teardown_provenance, TEARDOWN_PROVENANCE_M5_BOUND)
        self.assertEqual(rec.state, LifecycleState.CLOSED)


class B42M5Authentication(unittest.TestCase, _ArtifactMixin):
    def test_33_wrong_digest_rejected(self):
        ev, ref, _sha = _m5()
        rec = _full_for_m5(ev)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, "b" * 64)

    def test_34_missing_artifact_rejected(self):
        ev, _ref, _sha = _m5()
        rec = _full_for_m5(ev)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, "/nonexistent/m5.json#teardown",
                             "b" * 64)

    def test_35_malformed_digest_rejected(self):
        ev, ref, _sha = _m5()
        rec = _full_for_m5(ev)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, "nothex")

    def test_36_evidence_mismatch_rejected(self):
        ev, ref, sha = _m5()
        other = _copy(ev)
        other["provider_message"] = "different"
        rec = _full_for_m5(ev)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, other, ref, sha)

    def test_37_authenticated_artifact_required_for_close(self):
        # build a genuine record, then forge ONLY the reference path
        rec, ev, ref = _full_m5()
        d = rec.to_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["m5_reference"] = "/nonexistent/fake.json#teardown"
        tev["m5_sha256"] = "c" * 64
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        forged = {**body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}
        # recomputing the hash does NOT bypass authentication
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(forged)


class B43CgroupParsing(unittest.TestCase, _ArtifactMixin):
    def test_38_parser_semantics(self):
        self.assertEqual(cgroup_populated("populated 1\nfrozen 0"), 1)
        self.assertEqual(cgroup_populated("populated 0\nfrozen 0"), 0)
        self.assertIsNone(cgroup_populated("frozen 0"))
        self.assertIsNone(cgroup_populated("unpopulated 1"))
        self.assertIsNone(cgroup_populated("unpopulated 0"))
        # "populated 10" parses to 10; the CALLER range-checks it (rejected at
        # bind because 10 is neither 1 nor 0).
        self.assertEqual(cgroup_populated("populated 10"), 10)
        with self.assertRaises(LifecycleError):
            cgroup_populated("populated x")
        with self.assertRaises(LifecycleError):
            cgroup_populated("populated")
        with self.assertRaises(LifecycleError):
            cgroup_populated("populated 1\npopulated 0")

    def test_39_adversarial_events_rejected_at_bind(self):
        for bad in ("populated 1", "populated 10", "unpopulated 0",
                    "unpopulated 1", "populated x", "populated",
                    "populated 1\npopulated 0", "", "frozen 0"):
            ev = _copy(_m5()[0])
            ev["teardown"]["events_after"] = bad
            _ev, path, digest = self.write_artifact(ev)
            rec = _full_for_m5(ev)
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, path, digest)

    def test_40_adversarial_events_before_rejected(self):
        for bad in ("populated 0", "populated 10", "unpopulated 1",
                    "populated x", ""):
            ev = _copy(_m5()[0])
            ev["teardown"]["events_before"] = bad
            _ev, path, digest = self.write_artifact(ev)
            rec = _full_for_m5(ev)
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, path, digest)


class M5StrictBooleanR3(unittest.TestCase, _ArtifactMixin):
    def test_20_strict_target_terminated(self):
        for bad in (1, 0, "true", "false", "True", None, [1]):
            ev = _copy(_m5()[0])
            ev["post_kill"]["target_terminated"] = bad
            _ev, path, digest = self.write_artifact(ev)
            rec = _full_for_m5(ev)
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, path, digest)
        ev = _m5()[0]
        _ev, path, digest = self.write_artifact(ev)
        rec = _full_for_m5(ev)
        bind_m5_teardown(rec, ev, path, digest)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)

    def test_21_strict_no_provider_execution(self):
        for bad in (1, 0, "true", "false", None, []):
            ev = _copy(_m5()[0])
            ev["no_provider_execution"] = bad
            _ev, path, digest = self.write_artifact(ev)
            rec = _full_for_m5(ev)
            with self.assertRaises(LifecycleError):
                bind_m5_teardown(rec, ev, path, digest)
        ev = _m5()[0]
        _ev, path, digest = self.write_artifact(ev)
        rec = _full_for_m5(ev)
        bind_m5_teardown(rec, ev, path, digest)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_OBSERVED)


class AtomicRebindR4(unittest.TestCase):
    def test_22_failed_rebind_is_atomic(self):
        rec = LifecycleRecord.create("lc", "ps")
        rec.bind_sandbox("A")
        before = (rec.sandbox_id, len(rec.transitions))
        with self.assertRaises(LifecycleError):
            rec.bind_sandbox("B")
        self.assertEqual((rec.sandbox_id, len(rec.transitions)), before)
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
        rec.bind_workload(5, "10", "/c")
        self.assertEqual(len(rec.transitions), before[3])

    def test_22b_m5_reference_mismatch_and_rebind(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        bind_m5_teardown(rec, ev, ref, sha)
        n = len(rec.transitions)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, sha)
        self.assertEqual(len(rec.transitions), n)
        rec2 = _full()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec2, ev, ref, "nothex")
        self.assertEqual(rec2.state, LifecycleState.TEARDOWN_INITIATED)


class B44B45DeserializationInvariants(unittest.TestCase, _ArtifactMixin):
    def _legit_dict(self):
        rec, ev, ref = _full_m5()
        return rec.to_dict()

    def _rehash(self, body):
        return {**body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}

    def test_41_malformed_m5_sha256_rejected(self):
        d = self._legit_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["m5_sha256"] = "deadbeef"
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_42_bool_pid_rejected(self):
        d = self._legit_dict()
        d["pid"] = True
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_43_invalid_ordinal_rejected(self):
        d = self._legit_dict()
        d["transitions"][0]["at"] = 1.5
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_44_forged_m5_transition_rejected(self):
        d = self._legit_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["m5_reference"] = "/nonexistent/fake.json#teardown"
        tev["m5_sha256"] = "d" * 64
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_45_direct_provenance_with_m5_fields_rejected(self):
        d = self._legit_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["provenance"] = TEARDOWN_PROVENANCE_DIRECT
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_46_non_teardown_provenance_rejected(self):
        d = self._legit_dict()
        d["transitions"][0]["provenance"] = TEARDOWN_PROVENANCE_DIRECT
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(self._rehash(body))

    def test_47_legit_roundtrip_still_works(self):
        d = self._legit_dict()
        back = LifecycleRecord.from_dict(d)
        self.assertEqual(back.state, LifecycleState.CLOSED)
        self.assertEqual(back.to_dict(), d)


class B46ConstructionMutability(unittest.TestCase):
    def test_48_read_only_transitions(self):
        rec = _full()
        self.assertIsInstance(rec.transitions, tuple)
        with self.assertRaises(AttributeError):
            rec.transitions.append("x")  # type: ignore[attr-defined]

    def test_49_direct_invalid_closed_construction_rejected(self):
        # CLOSED with a DIRECT teardown: structurally impossible.
        trans = []
        for i, s in enumerate(LifecycleState):
            t = LifecycleTransition(seq=i, state=s, at=float(i))
            if s is LifecycleState.TEARDOWN_OBSERVED:
                t = LifecycleTransition(
                    seq=i, state=s, at=float(i), evidence_ref="r",
                    evidence_sha256="a" * 64,
                    provenance=TEARDOWN_PROVENANCE_DIRECT)
            trans.append(t)
        with self.assertRaises(LifecycleError):
            LifecycleRecord(lifecycle_id="lc", proof_session_id="ps",
                            sandbox_id="s", pid=1, pid_starttime="1",
                            cgroup="/c", _transitions=trans)

    def test_50_forged_m5_bound_direct_construction_rejected(self):
        rec = _forged_m5_record()
        self.assertIs(rec.teardown_provenance, TEARDOWN_PROVENANCE_M5_BOUND)
        # cannot serialize
        with self.assertRaises(LifecycleError):
            rec.to_dict()
        # cannot attest
        res = attest_lifecycle(rec)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("m5-reference-authenticated", res.failures)

    def test_51_invalid_transition_sequence_rejected(self):
        trans = [LifecycleTransition(seq=0, state=LifecycleState.CREATED, at=0.0),
                 LifecycleTransition(seq=2, state=LifecycleState.WORKLOAD_BOUND,
                                     at=2.0)]
        with self.assertRaises(LifecycleError):
            LifecycleRecord(lifecycle_id="lc", proof_session_id="ps",
                            _transitions=trans)


class B47AttestationTaxonomy(unittest.TestCase):
    def test_52_evidence_keys_disjoint_from_forbidden(self):
        rec, ev, ref = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev)
        overlap = set(res.evidence) & FORBIDDEN_AUTHORITY_KEYS
        self.assertEqual(overlap, set(), overlap)
        for bad in ("provider_executed", "live_proof"):
            self.assertNotIn(bad, res.evidence)


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
            self.assertFalse(verify_file_sha256(str(p), "0" * 64))
            self.assertFalse(verify_file_sha256(str(p), "deadbeef"))
            self.assertFalse(verify_file_sha256(str(Path(td) / "absent"), want))
            with self.assertRaises(LifecycleError):
                sha256_file(str(Path(td) / "absent"))


if __name__ == "__main__":
    unittest.main()
