"""tests.test_b4_lifecycle — B4-LIFECYCLE fail-closed tests (R1-R7 + B4-1..B4-7).

B4-2 AUTHENTICITY: M5-bound provenance requires a sealed observation minted by
the trusted-core M5 authority capability; construction of an observation is not
authenticity. Post-bind, the artifact is re-read and re-hashed at every trust
boundary.

Trust model (documented): the process-local authority is a trusted-core
CAPABILITY boundary, NOT process isolation. A compromised process can obtain
the capability (Q8 = yes). The tests below assert the removed accidents and the
required regressions, plus the real-producer positive path.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob import b4_lifecycle as B4L
from raphael_ibm_bob.b4_attestation import AttestationStatus
from raphael_ibm_bob.b4_lifecycle import (
    FORBIDDEN_AUTHORITY_KEYS, LifecycleError, LifecycleRecord, LifecycleState,
    LifecycleTransition, M5AuthorityError, M5Observation, M5TrustAuthority,
    TEARDOWN_PROVENANCE_DIRECT, TEARDOWN_PROVENANCE_M5_BOUND,
    attest_lifecycle, bind_m5_teardown, cgroup_populated, sha256_file,
    trusted_m5_authority, verify_file_sha256)

REPO = Path(__file__).resolve().parents[1]
M5 = REPO / "docs" / "integration" / "phase-2c-m5" / "m5-evidence.json"


def _m5():
    return (json.loads(M5.read_text()), str(M5),
            hashlib.sha256(M5.read_bytes()).hexdigest())


def _copy(ev):
    return json.loads(json.dumps(ev))


def _auth():
    return trusted_m5_authority()


def _m5_identity(ev):
    t = ev["tracked"]
    return int(t["pid"]), str(t["starttime"]), ev["delegation_context"]["child_cgroup"]


def _full_for_m5(ev, rec=None):
    pid, start, cg = _m5_identity(ev)
    rec = rec or LifecycleRecord.create("lc-m5", "ps-m5")
    rec.bind_sandbox("sbx-m5")
    rec.bind_workload(pid, start, cg)
    rec.start()
    rec.initiate_teardown()
    return rec


def _full_m5():
    ev, ref, sha = _m5()
    auth = _auth()
    rec = _full_for_m5(ev)
    pid, start, cg = _m5_identity(ev)
    obs = auth.mint(lifecycle_id=rec.lifecycle_id,
                    proof_session_id=rec.proof_session_id,
                    sandbox_id=rec.sandbox_id, pid=pid, pid_starttime=start,
                    cgroup=cg, reference=ref, sha256=sha)
    bind_m5_teardown(rec, ev, ref, sha, observation=obs, authority=auth)
    rec.close()
    return rec, ev, ref, auth


class _ArtifactMixin:
    def temp_artifact(self, ev):
        td = tempfile.mkdtemp(prefix="m5art_")
        self.addCleanup(shutil.rmtree, td, True)
        path = os.path.join(td, "m5-evidence.json")
        data = json.dumps(ev).encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        return ev, path, hashlib.sha256(data).hexdigest()


class LifecycleConstruction(unittest.TestCase):
    def test_1_direct_progression(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
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

    def test_4_mismatched_sandbox(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("A")
        with self.assertRaises(LifecycleError):
            rec.bind_sandbox("B")

    def test_5_invalid_workload(self):
        for pid, st, cg in ((0, "1", "/c"), (-1, "1", "/c"), (True, "1", "/c"),
                            (5, "", "/c"), (5, "1", "")):
            rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
            with self.assertRaises(LifecycleError):
                rec.bind_workload(pid, st, cg)

    def test_8_authority_smuggling_rejected(self):
        from raphael_ibm_bob.b4_lifecycle import _reject_authority
        for key in ("live_proof_authorized", "provider_success", "mission_complete"):
            with self.assertRaises(LifecycleError):
                _reject_authority({"n": [{key: True}]}, "test")


class AuthorityConstructionPART1(unittest.TestCase):
    def test_10_constructor_rejects_verifier(self):
        with self.assertRaises(TypeError):
            M5TrustAuthority(verifier=lambda payload: True)

    def test_11_constructor_requires_token(self):
        with self.assertRaises(TypeError):
            M5TrustAuthority()

    def test_12_wrong_token_rejected(self):
        with self.assertRaises(M5AuthorityError):
            M5TrustAuthority(_token=object())

    def test_13_subclass_blocked(self):
        with self.assertRaises(TypeError):
            class Evil(M5TrustAuthority):  # noqa
                pass

    def test_14_no_module_global_secret(self):
        self.assertFalse(hasattr(B4L, "_AUTHORITY_SECRET"))

    def test_15_observation_construction_is_not_authenticity(self):
        ev, ref, sha = _m5()
        pid, start, cg = _m5_identity(ev)
        rec = _full_for_m5(ev)
        forged = M5Observation(
            authority_id="attacker", lifecycle_id=rec.lifecycle_id,
            proof_session_id=rec.proof_session_id, sandbox_id=rec.sandbox_id,
            pid=pid, pid_starttime=start, cgroup=cg, evidence_reference=ref,
            evidence_sha256=sha, no_provider_execution=True,
            target_terminated=True, seal="0" * 64)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, ev, ref, sha, observation=forged,
                             authority=_auth())
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_INITIATED)


class M5Authenticity(unittest.TestCase):
    def test_16_authenticated_closure_attests(self):
        rec, ev, ref, auth = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev, authority=auth)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)

    def test_17_attest_without_authority_invalid(self):
        rec, ev, ref, auth = _full_m5()
        res = attest_lifecycle(rec)  # no authority -> fail closed
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("m5-observation-authenticated", res.failures)

    def test_18_foreign_lifecycle_rejected(self):
        ev, ref, sha = _m5()
        auth = _auth()
        rec = _full_for_m5(ev)
        pid, start, cg = _m5_identity(ev)
        obs = auth.mint(lifecycle_id=rec.lifecycle_id,
                        proof_session_id=rec.proof_session_id,
                        sandbox_id=rec.sandbox_id, pid=pid,
                        pid_starttime=start, cgroup=cg, reference=ref, sha256=sha)
        other = LifecycleRecord.create("lc-other", "ps-m5")
        other.bind_sandbox("sbx-m5"); other.bind_workload(pid, start, cg)
        other.start(); other.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(other, ev, ref, sha, observation=obs, authority=auth)

    def test_19_foreign_pid_rejected(self):
        ev, ref, sha = _m5()
        auth = _auth()
        pid, start, cg = _m5_identity(ev)
        rec_a = _full_for_m5(ev)          # real PID identity
        obs = auth.mint(lifecycle_id=rec_a.lifecycle_id,
                        proof_session_id=rec_a.proof_session_id,
                        sandbox_id=rec_a.sandbox_id, pid=pid,
                        pid_starttime=start, cgroup=cg, reference=ref, sha256=sha)
        rec_b = LifecycleRecord.create("lc-m5", "ps-m5")
        rec_b.bind_sandbox("sbx-m5")
        rec_b.bind_workload(pid + 11, start, cg)   # different PID
        rec_b.start(); rec_b.initiate_teardown()
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec_b, ev, ref, sha, observation=obs, authority=auth)

    def test_20_from_dict_requires_authority(self):
        rec, ev, ref, auth = _full_m5()
        d = rec.to_dict()
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d)
        back = LifecycleRecord.from_dict(d, authority=auth)
        self.assertEqual(back.state, LifecycleState.CLOSED)

    def test_21_from_dict_foreign_and_recomputed_rejected(self):
        rec, ev, ref, auth = _full_m5()
        d = rec.to_dict()
        d["pid"] = 999999
        body = {k: v for k, v in d.items() if k != "lifecycle_sha256"}
        d = {**body, "lifecycle_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()}
        with self.assertRaises(LifecycleError):
            LifecycleRecord.from_dict(d, authority=auth)


class PostBindIntegrityPART6(unittest.TestCase, _ArtifactMixin):
    def _bind_temp(self):
        ev, _ref, _sha = _m5()
        _ev, path, digest = self.temp_artifact(ev)
        auth = _auth()
        pid, start, cg = _m5_identity(ev)
        rec = LifecycleRecord.create("lc-m5", "ps-m5"); rec.bind_sandbox("sbx-m5")
        rec.bind_workload(pid, start, cg); rec.start(); rec.initiate_teardown()
        obs = auth.mint(lifecycle_id=rec.lifecycle_id,
                        proof_session_id=rec.proof_session_id,
                        sandbox_id=rec.sandbox_id, pid=pid, pid_starttime=start,
                        cgroup=cg, reference=path, sha256=digest)
        bind_m5_teardown(rec, ev, path, digest, observation=obs, authority=auth)
        rec.close()
        return rec, ev, path, digest, auth

    def test_22_replacement_after_bind_invalid(self):
        rec, ev, path, digest, auth = self._bind_temp()
        with open(path, "wb") as fh:
            fh.write(b'{"tampered":true}')
        res = attest_lifecycle(rec, m5_evidence=ev, authority=auth)
        self.assertIs(res.status, AttestationStatus.INVALID)
        with self.assertRaises(LifecycleError):
            rec.to_dict()

    def test_23_deletion_after_bind_invalid(self):
        rec, ev, path, digest, auth = self._bind_temp()
        os.unlink(path)
        res = attest_lifecycle(rec, m5_evidence=ev, authority=auth)
        self.assertIs(res.status, AttestationStatus.INVALID)

    def test_24_valid_authenticated_still_attests(self):
        rec, ev, path, digest, auth = self._bind_temp()
        res = attest_lifecycle(rec, m5_evidence=ev, authority=auth)
        self.assertIs(res.status, AttestationStatus.ATTESTED, res.failures)


class CriticalAttackerRegression(unittest.TestCase, _ArtifactMixin):
    def test_25_attacker_json_sha_cannot_reach_attested(self):
        ev, ref, sha = _m5()
        rec = _full_for_m5(ev)
        authored = _copy(ev)
        _ev, path, digest = self.temp_artifact(authored)
        # no observation -> rejected
        with self.assertRaises(TypeError):
            bind_m5_teardown(rec, authored, path, digest)
        # forged observation -> rejected
        pid, start, cg = _m5_identity(authored)
        forged = M5Observation(
            authority_id="attacker", lifecycle_id=rec.lifecycle_id,
            proof_session_id=rec.proof_session_id, sandbox_id=rec.sandbox_id,
            pid=pid, pid_starttime=start, cgroup=cg, evidence_reference=path,
            evidence_sha256=digest, no_provider_execution=True,
            target_terminated=True, seal="0" * 64)
        with self.assertRaises(LifecycleError):
            bind_m5_teardown(rec, authored, path, digest, observation=forged,
                             authority=_auth())
        self.assertEqual(rec.state, LifecycleState.TEARDOWN_INITIATED)


class DirectAndParser(unittest.TestCase, _ArtifactMixin):
    def test_26_direct_cannot_close(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        rec.observe_teardown("ref", "a" * 64)
        with self.assertRaises(LifecycleError):
            rec.close()

    def test_27_observe_rejects_m5_bound(self):
        rec = LifecycleRecord.create("lc", "ps"); rec.bind_sandbox("s")
        rec.bind_workload(1, "1", "/c"); rec.start(); rec.initiate_teardown()
        with self.assertRaises(LifecycleError):
            rec.observe_teardown("r", "a" * 64,
                                 provenance=TEARDOWN_PROVENANCE_M5_BOUND)

    def test_28_parser_canonical(self):
        self.assertEqual(cgroup_populated("populated 1\nfrozen 0"), 1)
        self.assertEqual(cgroup_populated("populated 0\nfrozen 0"), 0)
        self.assertIsNone(cgroup_populated("frozen 0"))
        self.assertIsNone(cgroup_populated("unpopulated 1"))
        for bad in ("populated 01", "populated -0", "populated -1",
                    "populated 10", "populated x", "populated",
                    "populated 1\npopulated 0"):
            with self.assertRaises(LifecycleError):
                cgroup_populated(bad)

    def test_29_strict_booleans(self):
        for field in ("target_terminated", "no_provider_execution"):
            for bad in (1, 0, "true", "false", None, []):
                ev = _copy(_m5()[0])
                if field == "target_terminated":
                    ev["post_kill"]["target_terminated"] = bad
                else:
                    ev["no_provider_execution"] = bad
                _ev, path, digest = self.temp_artifact(ev)
                pid, start, cg = _m5_identity(ev)
                with self.assertRaises(M5AuthorityError):
                    _auth().mint(lifecycle_id="lc", proof_session_id="ps",
                                 sandbox_id="s", pid=pid, pid_starttime=start,
                                 cgroup=cg, reference=path, sha256=digest)


class FileShaAndTaxonomy(unittest.TestCase):
    def test_30_sha256_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m5.json"
            p.write_bytes(b"raphael-m5")
            want = hashlib.sha256(b"raphael-m5").hexdigest()
            self.assertEqual(sha256_file(str(p)), want)
            self.assertTrue(verify_file_sha256(str(p), want))
            self.assertFalse(verify_file_sha256(str(p), "0" * 64))
            with self.assertRaises(LifecycleError):
                sha256_file(str(Path(td) / "absent"))

    def test_31_taxonomy_and_readonly(self):
        rec, ev, ref, auth = _full_m5()
        res = attest_lifecycle(rec, m5_evidence=ev, authority=auth)
        self.assertEqual(set(res.evidence) & FORBIDDEN_AUTHORITY_KEYS, set())
        self.assertIsInstance(rec.transitions, tuple)


@unittest.skipUnless(shutil.which("systemd-run") and hasattr(os, "getuid"),
                     "real M5 producer requires systemd-run")
class PositiveProducerPART4(unittest.TestCase):
    def test_32_real_m5_probe_produces_attested_observation(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "m5_teardown_probe.py")],
            capture_output=True, text=True, timeout=120, cwd=str(REPO))
        out = proc.stdout + proc.stderr
        self.assertIn("M5-LIFECYCLE attested", out, out[-1500:])
        self.assertEqual(proc.returncode, 0, out[-1500:])


if __name__ == "__main__":
    unittest.main()
