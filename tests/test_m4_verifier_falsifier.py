"""tests/test_m4_verifier_falsifier.py — M4 Verifier + Falsifier tests.

Stdlib-only. Real Runtime + Broker + Policy + EvidenceLedger path. NO mocks.
"""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from raphael_bob import (
    Capability,
    Finding,
    FindingState,
    Mission,
    Workspace,
)
from raphael_bob.broker import BOBBroker
from raphael_bob.evidence_ledger import EvidenceLedger
from raphael_bob.falsifier import (
    ChallengeSpec,
    Falsifier,
)
from raphael_bob.finding import FindingStore, InvalidTransitionError
from raphael_bob.policy import BOBPolicy
from raphael_bob.runtime import BOBRuntime
from raphael_bob.verifier import RetestSpec, Verifier


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

def _make_workspace(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m4_ws_")
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "hello.txt").write_text("hello-m4\n", encoding="utf-8")
    (root / "src" / "fixed.py").write_text(
        "def fixed_session(): return 'OK'\n", encoding="utf-8"
    )
    (root / "src" / "still_buggy.py").write_text(
        "BUG: still contains the original defect\n", encoding="utf-8"
    )
    (root / "src" / "test_smoke.py").write_text(textwrap.dedent("""
        import unittest
        class T(unittest.TestCase):
            def test_true(self):
                self.assertTrue(True)
        if __name__ == "__main__":
            unittest.main()
    """).strip() + "\n", encoding="utf-8")
    testcase.addCleanup(_rm, root)
    return root


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m4_run_")
    testcase.addCleanup(_rm, Path(tmp))
    return Path(tmp)


def _rm(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _mission(scope: str = "src/") -> Mission:
    return Mission(
        mission_id="M-test", description="authkit fix",
        scope=scope, criteria=["all named tests pass", "behavior probe passes"],
    )


class _Harness:
    def __init__(self, ws_root: Path, run_root: Path, scope: str = "src/"):
        self.workspace = Workspace(ws_root)
        self.ledger = EvidenceLedger(run_root)
        self.policy = BOBPolicy(self.workspace)
        self.broker = BOBBroker(self.policy, self.workspace, ledger=self.ledger)
        self.runtime = BOBRuntime(self.broker)
        self.store = FindingStore(self.ledger)
        self.verifier = Verifier(self.runtime, self.ledger, self.store)
        self.falsifier = Falsifier(self.runtime, self.ledger, self.store)
        self.mission = _mission(scope)

    def make_finding(self, fid: str, target: str = "src/fixed.py",
                     summary: str = "session.py mishandles tokens") -> Finding:
        finding = Finding(
            finding_id=fid,
            state=FindingState.UNVERIFIED,
            summary=summary,
            target=target,
        )
        self.store.register(finding)
        return finding


def _harness(testcase: unittest.TestCase, scope: str = "src/") -> _Harness:
    return _Harness(_make_workspace(testcase), _make_run_dir(testcase), scope)


# -----------------------------------------------------------------------------
# 1. retest uses Broker
# -----------------------------------------------------------------------------

class RetestUsesBroker(unittest.TestCase):
    def test_retest_increments_broker_submission_counter(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        before = h.broker.submissions
        h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        self.assertEqual(h.broker.submissions, before + 1)

    def test_retest_emits_canonical_ledger_chain(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        kinds = [r.get("kind") for r in h.ledger.all_records()]
        self.assertIn("request", kinds)
        self.assertIn("decision", kinds)
        self.assertIn("result", kinds)
        evs = [r for r in h.ledger.all_records() if r.get("kind") == "evidence"]
        producers = {r.get("producer") for r in evs}
        self.assertIn("verifier", producers)


# -----------------------------------------------------------------------------
# 2. verifier cannot bypass Policy
# -----------------------------------------------------------------------------

class VerifierCannotBypassPolicy(unittest.TestCase):
    def test_retest_outside_workspace_is_denied(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        outcome = h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.WRITE, target="/tmp/escape",
                       purpose="content=x"),
            h.mission,
        )
        self.assertFalse(outcome.transition_applied)
        self.assertIn("retest-denied", outcome.transition_reason)
        self.assertEqual(h.store.get("F-1").state, FindingState.UNVERIFIED)


# -----------------------------------------------------------------------------
# 3. denied verifier action has no side effect
# -----------------------------------------------------------------------------

class DeniedVerifierNoSideEffect(unittest.TestCase):
    def test_denied_retest_does_not_create_files_or_artifacts(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        before_artifacts = set(
            p.name for p in h.ledger._artifacts._artifacts_dir.iterdir()
        )
        outcome = h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.WRITE, target="/tmp/escape",
                       purpose="content=x"),
            h.mission,
        )
        self.assertFalse(outcome.transition_applied)
        after_artifacts = set(
            p.name for p in h.ledger._artifacts._artifacts_dir.iterdir()
        )
        self.assertEqual(before_artifacts, after_artifacts)
        kinds = [r.get("kind") for r in h.ledger.all_records()]
        self.assertNotIn("result", kinds)

    def test_denied_retest_persists_policy_receipt_not_execution(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.WRITE, target="/tmp/escape",
                       purpose="content=x"),
            h.mission,
        )
        evs = [r for r in h.ledger.all_records() if r.get("kind") == "evidence"]
        producers = {r.get("producer") for r in evs}
        self.assertIn("policy", producers)
        self.assertIn("verifier", producers)
        self.assertNotIn("execution", producers)


# -----------------------------------------------------------------------------
# 4. retest creates durable evidence
# -----------------------------------------------------------------------------

class RetestCreatesDurableEvidence(unittest.TestCase):
    def test_reopen_ledger_sees_verifier_evidence(self):
        ws_root = _make_workspace(self)
        run_root = _make_run_dir(self)
        workspace = Workspace(ws_root)
        ledger = EvidenceLedger(run_root)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        store = FindingStore(ledger)
        verifier = Verifier(runtime, ledger, store)
        mission = _mission()
        f = Finding(finding_id="F-1", state=FindingState.UNVERIFIED,
                   summary="x", target="src/fixed.py")
        store.register(f)
        verifier.verify(f, RetestSpec(capability=Capability.READ,
                                      target="src/fixed.py",
                                      expected_substring="OK"), mission)
        ledger._writer.close()
        reopened = EvidenceLedger(run_root)
        evs = [r for r in reopened.all_records() if r.get("kind") == "evidence"
               and r.get("producer") == "verifier"]
        self.assertGreaterEqual(len(evs), 1)
        self.assertTrue(any(r.get("finding_id") == "F-1" for r in evs))


# -----------------------------------------------------------------------------
# 5. finding becomes VERIFIED only after valid retest
# -----------------------------------------------------------------------------

class VerifiesOnlyAfterValidRetest(unittest.TestCase):
    def test_valid_retest_transitions_to_verified(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        outcome = h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        self.assertTrue(outcome.transition_applied)
        self.assertEqual(outcome.finding.state, FindingState.VERIFIED)
        self.assertEqual(h.store.get("F-1").state, FindingState.VERIFIED)

    def test_retest_with_wrong_expected_substring_does_not_verify(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        outcome = h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="NOT-PRESENT"),
            h.mission,
        )
        self.assertFalse(outcome.transition_applied)
        self.assertIn("retest-output-mismatch", outcome.transition_reason)
        self.assertEqual(h.store.get("F-1").state, FindingState.UNVERIFIED)


# -----------------------------------------------------------------------------
# 6 + 7 + 8. Falsifier: counter-example, durable evidence, REFUTED
# -----------------------------------------------------------------------------

class FalsifierCounterExample(unittest.TestCase):
    def test_falsifier_observes_real_counter_example(self):
        h = _harness(self)
        finding = h.make_finding("F-1", target="src/still_buggy.py")
        h.store.transition("F-1", FindingState.VERIFIED, evidence_seqs=(1,))
        # READ still_buggy.py; the file content still contains the bug.
        outcome = h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ,
                          target="src/still_buggy.py",
                          forbidden_substring="BUG: still contains the original defect"),
            h.mission,
        )
        self.assertTrue(outcome.counter_example_observed)
        self.assertIn("counter-example-observed", outcome.transition_reason)
        self.assertTrue(outcome.transition_applied)
        self.assertEqual(h.store.get("F-1").state, FindingState.REFUTED)

    def test_falsifier_without_counter_example_leaves_verified(self):
        h = _harness(self)
        finding = h.make_finding("F-1", target="src/fixed.py")
        h.store.transition("F-1", FindingState.VERIFIED, evidence_seqs=(1,))
        outcome = h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ,
                          target="src/fixed.py",
                          forbidden_substring="NONEXISTENT-FRAGMENT"),
            h.mission,
        )
        self.assertFalse(outcome.counter_example_observed)
        self.assertFalse(outcome.transition_applied)
        self.assertEqual(h.store.get("F-1").state, FindingState.VERIFIED)

    def test_counter_example_persists_durable_evidence(self):
        h = _harness(self)
        finding = h.make_finding("F-1", target="src/still_buggy.py")
        h.store.transition("F-1", FindingState.VERIFIED, evidence_seqs=(1,))
        h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ,
                          target="src/still_buggy.py",
                          forbidden_substring="BUG: still contains the original defect"),
            h.mission,
        )
        evs = [r for r in h.ledger.all_records() if r.get("kind") == "evidence"
               and r.get("producer") == "falsifier"]
        self.assertEqual(len(evs), 2)
        kinds = sorted(r.get("payload", {}).get("kind") for r in evs)
        self.assertEqual(kinds, ["challenge", "counter-example"])
        self.assertTrue(all(r.get("finding_id") == "F-1" for r in evs))


# -----------------------------------------------------------------------------
# 9. finding provenance can be reconstructed from the ledger
# -----------------------------------------------------------------------------

class FindingProvenanceReconstructable(unittest.TestCase):
    def test_records_for_finding_returns_chronological_chain(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ, target="src/fixed.py",
                          forbidden_substring="DOES-NOT-EXIST"),
            h.mission,
        )
        records = h.ledger.records_for_finding("F-1")
        seqs = [r.get("seq") for r in records]
        self.assertEqual(seqs, sorted(seqs))
        self.assertGreater(len(records), 0)
        kinds = [r.get("kind") for r in records]
        self.assertIn("finding", kinds)
        self.assertIn("evidence", kinds)

    def test_records_for_unknown_finding_returns_empty(self):
        h = _harness(self)
        self.assertEqual(h.ledger.records_for_finding("DOES-NOT-EXIST"), [])


# -----------------------------------------------------------------------------
# 10. UNVERIFIED findings cannot masquerade as VERIFIED
# -----------------------------------------------------------------------------

class UnverifiedCannotMasquerade(unittest.TestCase):
    def test_finding_unverified_after_denied_retest(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        outcome = h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.WRITE, target="/tmp/escape",
                       purpose="content=x"),
            h.mission,
        )
        self.assertFalse(outcome.transition_applied)
        self.assertEqual(h.store.get("F-1").state, FindingState.UNVERIFIED)
        self.assertEqual(outcome.finding.state, FindingState.UNVERIFIED)

    def test_falsifier_on_unverified_finding_does_not_transition(self):
        h = _harness(self)
        finding = h.make_finding("F-1")
        outcome = h.falsifier.challenge(
            finding,
            ChallengeSpec(capability=Capability.READ, target="src/fixed.py",
                          forbidden_substring="BUG"),
            h.mission,
        )
        self.assertFalse(outcome.transition_applied)
        self.assertEqual(outcome.finding.state, FindingState.UNVERIFIED)

    def test_invalid_transition_unverified_to_superseded_raises(self):
        h = _harness(self)
        h.make_finding("F-1")
        with self.assertRaises(InvalidTransitionError):
            h.store.transition("F-1", FindingState.SUPERSEDED, evidence_seqs=(1,))


# -----------------------------------------------------------------------------
# 11. Full UNVERIFIED -> VERIFIED -> REFUTED lifecycle
# -----------------------------------------------------------------------------

class FullLifecycleLedger(unittest.TestCase):
    def test_full_unverified_verified_refuted_cycle(self):
        h = _harness(self)
        f1 = h.make_finding("F-1", target="src/still_buggy.py",
                            summary="session.py mishandles tokens")
        # Verify F-1 against fixed.py (with the fix in place).
        out1 = h.verifier.verify(
            f1,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        self.assertTrue(out1.transition_applied)
        self.assertEqual(h.store.get("F-1").state, FindingState.VERIFIED)
        # Falsify F-1: still_buggy.py STILL contains the bug.
        out1c = h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ,
                          target="src/still_buggy.py",
                          forbidden_substring="BUG: still contains the original defect"),
            h.mission,
        )
        self.assertTrue(out1c.transition_applied)
        self.assertEqual(h.store.get("F-1").state, FindingState.REFUTED)
        # F-2: verified through, no counter-example.
        f2 = h.make_finding("F-2", target="src/fixed.py", summary="session.py fixed")
        out2 = h.verifier.verify(
            f2,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        self.assertTrue(out2.transition_applied)
        out2c = h.falsifier.challenge(
            h.store.get("F-2"),
            ChallengeSpec(capability=Capability.READ, target="src/fixed.py",
                          forbidden_substring="NONEXISTENT-FRAGMENT"),
            h.mission,
        )
        self.assertFalse(out2c.transition_applied)
        self.assertEqual(h.store.get("F-2").state, FindingState.VERIFIED)
        # The ledger now contains both lifecycles.
        finding_records = h.ledger.records_by_kind("finding")
        # 2 initial + 1 verified transition for F-1 + 1 refuted transition
        # for F-1 + 1 verified transition for F-2 = 5.
        self.assertEqual(len(finding_records), 5)


if __name__ == "__main__":
    unittest.main()