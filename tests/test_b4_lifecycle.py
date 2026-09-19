"""tests.test_b4_lifecycle — B4-LIFECYCLE fail-closed tests.

Covers R1-R7, B4-1..B4-7, and the B4-2 AUTHENTICITY correction:

  ARTIFACT INTEGRITY (bytes hash to digest)
  ARTIFACT AUTHENTICITY (minted by a live M5 trust authority for THIS lifecycle)
  LIFECYCLE INTEGRITY (record unmodified since recorded)

Critical regression (PART 13): an attacker who writes a valid M5-schema JSON
file, knows its SHA-256, and knows the schema STILL cannot obtain M5-bound
provenance or ATTESTED — because authenticity requires an observation minted
by a live authority bound to the lifecycle identity.
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
    LifecycleTransition, M5AuthorityError, M5Observation,
    M5TrustAuthority, TEARDOWN_PROVENANCE_DIRECT,
    TEARDOWN_PROVENANCE_M5_BOUND, attest_lifecycle, bind_m5_teardown,
    cgroup_populated, sha256_file, verify_file_sha256)

M5 = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
      "phase-2c-m5" / "m5-evidence.json")


def _m5():
    return (json.loads(M5.read_text()), str(M5),
            hashlib.sha256(M5.read_bytes()).hexdigest())


def _copy(ev):
    return json.loads(json.dumps(ev))


def _authority():
    """Test double for the trusted M5 producer verifier."""
    return M5TrustAuthority(verifier=lambda payload: True)


def _m5_identity(ev):
    t = ev["tracked"]
    cg = ev["delegation_context"]["child_cgroup"]
    return int(t["pid"]), str(t["starttime"]), cg


def _full_for_m5(ev, rec=None, authority=None):
    pid, start, cg = _m5_identity(ev)
    rec = rec or LifecycleRecord.create("lc-m5", "ps-m5")
    rec.bind_sandbox("sbx-m5")
    rec.bind_workload(pid, start, cg)
    rec.start()
    rec.initiate_teardown()
    return rec


def _mint(rec, ev, ref, sha, authority):
    pid, start, cg = _m5_identity(ev)
    return authority.mint(
        lifecycle_id=rec.lifecycle_id, proof_session_id=rec.proof_session_id,
        sandbox_id=rec.sandbox_id, pid=pid, pid_starttime=start, cgroup=cg,
        reference=ref, sha256=sha)


def _full_m5():
    ev, ref, sha = _m5()
    authority = _authority()
    rec = _full_for_m5(ev)
    obs = _mint(rec, ev, ref, sha, authority)
    bind_m5_teardown(rec, ev, ref, sha, observation=obs)
    rec.close()
    return rec, ev, ref, authority


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
        rec = LifecycleRecord.create("lc-1", "ps-1")
        rec.bind_sandbox("s"); rec.bind_workload(1, "1", "/c")
        rec.start(); rec.initiate_teardown()
        rec.observe_teardown("ref", "a" * 64)
        self.assertEqual(rec.teardown_provenance, TEARDOWN_PROVENANCE_DIRECT)

    def test_2_missing_identity_rejected(self):
        with self.assertRaises(LifecycleError):
            LifecycleRecord.create("", "ps")
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
        rec.bind_sandbox("A")
        with self.assertRaises(LifecycleError):
            rec.bind_sandbox("B")

    def test_5_invalid_workload_identity_each(self):
        for pid, st, cg in ((0, "1", "/c"), (-1, "1", "/c"), (True, "1", "/c"),
                            (5, "", "/c"), (5, "1", "")):
            rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
            with self.assertRaises(LifecycleError):
                rec.bind_workload(pid, st, cg)

    def test_6_teardown_requires_evidence(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("ref", "short")
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("", "a" * 64)

    def test_7_premature_closure_rejected(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            rec.close()

    def test_8_authority_smuggling_rejected(self):
        from raphael_ibm_bob.b4_lifecycle import _reject_authority
        for key in ("live_proof_authorized", "provider_success",
                    "mission_complete", "quality_gate_complete"):
            with self.assertRaises(LifecycleError):
                _reject_authority({"nested": [{key: True}]}, "test")


class M5Authenticity(unittest.TestCase, _ArtifactMixin):
    def test_10_m5_authenticated_closure_attests(self):
        rec, ev, ref, authority = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev, authority=authority)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)
        self.assertEqual(res.evidence["teardown_provenance"],
                         TEARDOWN_PROVENANCE_M5_BOUND)
        self.assertFalse(res.evidence["provider_execution_observed"])

    def test_11_observation_identity_mismatch_rejected(self):
        ev, ref, sha = _m5()
        authority = _authority()
        rec = _full_for_m5(ev)
        obs = _mint(rec, ev, ref, sha, authority)
        # different lifecycle identity
        other = LifecycleRecord.create("lc-other", "ps-m5")
        other.bind_sandbox("sbx-m5"); other.bind_workload(*_m5_identity(ev))
        other.start(); other.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(other, ev, ref, sha, observation=obs)

    def test_12_foreign_pid_rejected(self):
        ev, ref, sha = _m5()
        authority = _authority()
        rec = _full_for_m5(ev)
        pid, start, cg = _m5_identity(ev)
        obs = authority.mint(lifecycle_id=rec.lifecycle_id,
                             proof_session_id=rec.proof_session_id,
                             sandbox_id=rec.sandbox_id, pid=pid,
                             pid_starttime=start, cgroup=cg,
                             reference=ref, sha256=sha)
        rec2 = LifecycleRecord.create("lc-m5", "ps-m5"); rec2.bind_sandbox("sbx-m5")
        rec2.bind_workload(pid + 7, start, cg); rec2.start(); rec2.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec2, ev, ref, sha, observation=obs)

    def test_13_observation_seal_required(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        with self.assertRaises(TypeError):
            bind_m5_teardown(rec, ev, ref, sha)  # no observation

    def test_14_no_verifier_fails_closed(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        auth = M5TrustAuthority()  # no verifier
        pid, start, cg = _m5_identity(ev)
        with self.assertRaises(M5AuthorityError):
            auth.mint(lifecycle_id=rec.lifecycle_id,
                      proof_session_id=rec.proof_session_id,
                      sandbox_id=rec.sandbox_id, pid=pid, pid_starttime=start,
                      cgroup=cg, reference=ref, sha256=sha)

    def test_15_attest_without_authority_is_invalid(self):
        rec, ev, ref, authority = _full_m5()
        res = attest_lifecycle(rec)  # no live authority
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("m5-observation-authenticated", res.failures)

    def test_16_from_dict_requires_authority(self):
        rec, ev, ref, authority = _full_m5()
        d = rec.to_dict()
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)  # no authority -> fail closed
        back = LifecycleRecord.from_dict(d, authority=authority)
        self.assertEqual(back.state, LifecycleState.CLOSED)

    def test_17_from_dict_foreign_identity_rejected(self):
        rec, ev, ref, authority = _full_m5()
        d = rec.to_dict()
        d["pid"] = 999999          # attacker edits identity
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        d = {**body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d, authority=authority)

    def test_18_recomputed_hash_cannot_attest_forgery(self):
        rec, ev, ref, authority = _full_m5()
        d = rec.to_dict()
        tev = [t for t in d["transitions"]
               if t["state"] == "TEARDOWN_OBSERVED"][0]
        tev["m5_observation"]["evidence_sha256"] = "d" * 64
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        d = {**body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d, authority=authority)


class CriticalAttackerRegression(unittest.TestCase, _ArtifactMixin):
    """PART 13: attacker writes file + knows SHA + knows schema => no ATTESTED."""

    def test_19_attacker_valid_json_correct_digest_cannot_bind(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        # attacker has a self-authored, schema-valid, correctly-hashed artifact
        authored = _copy(ev)
        _ev, path, digest = self.write_artifact(authored)
        # (1) no observation -> cannot obtain M5-bound
        with self.assertRaises((LifecycleError, TypeError)):
            bind_m5_teardown(rec, authored, path, digest)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_INITIATED)
        # (2) forged observation object -> seal invalid
        pid, start, cg = _m5_identity(ev)
        forged = M5Observation(
            authority_id="attacker", lifecycle_id=rec.lifecycle_id,
            proof_session_id=rec.proof_session_id, sandbox_id=rec.sandbox_id,
            pid=pid, pid_starttime=start, cgroup=cg, evidence_reference=path,
            evidence_sha256=digest, no_provider_execution=True,
            target_terminated=True, seal="0" * 64)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, authored, path, digest, observation=forged)
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_INITIATED)

    def test_20_attacker_cannot_attest_even_with_authority_absent(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        authored = _copy(ev)
        _ev, path, digest = self.write_artifact(authored)
        # forge a CLOSED record directly with a bad-seal observation
        pid, start, cg = _m5_identity(ev)
        forged_obs = M5Observation(
            authority_id="attacker", lifecycle_id=rec.lifecycle_id,
            proof_session_id=rec.proof_session_id, sandbox_id=rec.sandbox_id,
            pid=pid, pid_starttime=start, cgroup=cg, evidence_reference=path,
            evidence_sha256=digest, no_provider_execution=True,
            target_terminated=True, seal="0" * 64).to_dict()
        trans = []
        for i, s in enumerate(LifecycleState):
            t = LifecycleTransition(seq=i, state=s, at=float(i))
            if s is LifecycleState.TEARDOWN_OBSERVED:
                t = LifecycleTransition(
                    seq=i, state=s, at=float(i), evidence_ref=path,
                    evidence_sha256=digest,
                    provenance=TEARDOWN_PROVENANCE_M5_BOUND, m5_reference=path,
                    m5_sha256=digest, m5_observation=forged_obs)
            trans.append(t)
        with self.assertRaises(LifecycleError):
            LifecycleRecord(lifecycle_id=rec.lifecycle_id,
                            proof_session_id=rec.proof_session_id,
                            sandbox_id=rec.sandbox_id, pid=pid,
                            pid_starttime=start, cgroup=cg, _transitions=trans)


class DirectAndParser(unittest.TestCase, _ArtifactMixin):
    def test_21_direct_teardown_cannot_close(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        rec.observe_teardown("ref", "a" * 64)
        with self.assertRaises(LifecycleError):
            rec.close()

    def test_22_observe_rejects_m5_bound(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("r", "a" * 64,
                                 provenance=TEARDOWN_PROVENANCE_M5_BOUND)

    def test_23_parser_canonical(self):
        self.assertEqual(cgroup_populated("populated 1\nfrozen 0"), 1)
        self.assertEqual(cgroup_populated("populated 0\nfrozen 0"), 0)
        self.assertIsNone(cgroup_populated("frozen 0"))
        self.assertIsNone(cgroup_populated("unpopulated 1"))
        for bad in ("populated 01", "populated -0", "populated -1",
                    "populated 10", "populated x", "populated",
                    "populated 1\npopulated 0"):
            with self.assertRaises(LifecycleError):
                cgroup_populated(bad)

    def test_24_strict_booleans(self):
        for field in ("target_terminated", "no_provider_execution"):
            for bad in (1, 0, "true", "false", None, []):
                ev = _copy(_m5()[0])
                if field == "target_terminated":
                    ev["post_kill"]["target_terminated"] = bad
                else:
                    ev["no_provider_execution"] = bad
                _ev, path, digest = self.write_artifact(ev)
                rec = LifecycleRecord.create("lc-m5", "ps-m5")
                rec.bind_sandbox("sbx-m5")
                pid, start, cg = _m5_identity(ev)
                rec.bind_workload(pid, start, cg); rec.start()
                rec.initiate_teardown()
                auth = _authority()
                with self.assertRaises(M5AuthorityError):
                    auth.mint(lifecycle_id=rec.lifecycle_id,
                              proof_session_id=rec.proof_session_id,
                              sandbox_id=rec.sandbox_id, pid=pid,
                              pid_starttime=start, cgroup=cg,
                              reference=path, sha256=digest)

    def test_25_values_not_coerced_in_parser(self):
        # canonical grammar only; "10" is not silently accepted as integer 10
        with self.assertRaises(LifecycleError):
            cgroup_populated("populated 10")


class FileShaAndTaxonomy(unittest.TestCase, _ArtifactMixin):
    def test_26_sha256_file_actual_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m5.json"
            p.write_bytes(b"raphael-m5")
            want = hashlib.sha256(b"raphael-m5").hexdigest()
            self.assertEqual(sha256_file(str(p)), want)
            self.assertTrue(verify_file_sha256(str(p), want))
            self.assertFalse(verify_file_sha256(str(p), "0" * 64))
            self.assertFalse(verify_file_sha256(str(p / "x"), want))
            with self.assertRaises(LifecycleError):
                sha256_file(str(Path(td) / "absent"))

    def test_27_attestation_taxonomy_disjoint(self):
        rec, ev, ref, authority = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev, authority=authority)
        overlap = set(res.evidence) & FORBIDDEN_AUTHORITY_KEYS
        self.assertEqual(overlap, set(), overlap)
        for bad in ("provider_executed", "live_proof"):
            self.assertNotIn(bad, res.evidence)

    def test_28_read_only_transitions(self):
        rec, ev, ref, authority = _full_m5()
        self.assertIsInstance(rec.transitions, tuple)
        with self.assertRaises(AttributeError):
            rec.transitions.append("x")  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
