"""tests.test_t1_2_remediation — T1-2 patch propose/verify loop.

Mock-free: proposals are applied with broker-mediated WRITEs and
verified with the real Verifier/Falsifier over a synthetic workspace.
No authkit content is hardcoded; every scenario is parameterized.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob import (
    Capability,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    Workspace,
)
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import EvidenceReceipt
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.remediation import (
    Remediator,
    propose_patch,
)
from raphael_ibm_bob.replanner import Replanner
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.verifier import RetestSpec, Verifier


TARGET = "src/fix.txt"


def _world(testcase: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp(prefix="t1_2_ws_"))
    testcase.addCleanup(shutil.rmtree, root, True)
    src = root / "src"
    src.mkdir()
    (src / "fix.txt").write_text("BROKEN\n", encoding="utf-8")
    return root


_DEFAULT_CONTROL = object()


class _Stack:
    def __init__(self, testcase: unittest.TestCase):
        run_root = Path(tempfile.mkdtemp(prefix="t1_2_run_"))
        testcase.addCleanup(shutil.rmtree, run_root, True)
        self.workspace = Workspace(_world(testcase))
        self.ledger = EvidenceLedger(run_root)
        self.policy = BOBPolicy(self.workspace)
        self.broker = BOBBroker(self.policy, self.workspace,
                                ledger=self.ledger)
        self.runtime = BOBRuntime(self.broker)
        self.store = FindingStore(self.ledger)
        self.verifier = Verifier(self.runtime, self.ledger, self.store)
        self.falsifier = Falsifier(self.runtime, self.ledger, self.store)
        self.replanner = Replanner(self.store, self.ledger)
        self.gate = BOBQualityGate(self.ledger)
        self.remediator = Remediator(
            self.runtime, self.ledger, self.store,
            self.verifier, self.falsifier)
        self.mission = Mission(
            mission_id="M-px", description="x", scope="src/",
            criteria=["fix verified"])

    def finding(self, fid: str) -> Finding:
        finding = Finding(finding_id=fid, state=FindingState.UNVERIFIED,
                          summary="needs fix", target=TARGET)
        return self.store.register(finding)

    def proposal(self, fid: str, content: str,
                 control=_DEFAULT_CONTROL):
        proof = RetestSpec(capability=Capability.READ, target=TARGET,
                           expected_substring="OK")
        if control is _DEFAULT_CONTROL:
            control = ChallengeSpec(
                capability=Capability.READ, target=TARGET,
                purpose="px:control",
                forbidden_substring="STILL-BROKEN")
        return propose_patch(
            finding_id=fid, target=TARGET, content=content,
            parent_plan_id="P-parent", rationale="fix the marker",
            proof=proof, negative_control=control)


class ProposalCreation(unittest.TestCase):
    def test_fields_and_deterministic_id(self):
        proof = RetestSpec(capability=Capability.READ, target=TARGET,
                           expected_substring="OK")
        first = propose_patch(
            finding_id="F-1", target=TARGET, content="OK\n",
            parent_plan_id="P-1", rationale="r", proof=proof,
            negative_control=None)
        second = propose_patch(
            finding_id="F-1", target=TARGET, content="OK\n",
            parent_plan_id="P-9", rationale="other", proof=proof,
            negative_control=None)
        # Identity derives from claim + target + content only.
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertTrue(first.proposal_id.startswith("PX-"))
        third = propose_patch(
            finding_id="F-1", target=TARGET, content="OTHER\n",
            parent_plan_id="P-1", rationale="r", proof=proof,
            negative_control=None)
        self.assertNotEqual(first.proposal_id, third.proposal_id)
        self.assertEqual(len(first.diff_hash), 16)

    def test_missing_fields_rejected(self):
        proof = RetestSpec(capability=Capability.READ, target=TARGET,
                           expected_substring="OK")
        with self.assertRaises(ValueError):
            propose_patch(finding_id="", target=TARGET, content="x",
                          parent_plan_id=None, rationale="r", proof=proof)
        with self.assertRaises(ValueError):
            propose_patch(finding_id="F-1", target="", content="x",
                          parent_plan_id=None, rationale="r", proof=proof)
        with self.assertRaises(ValueError):
            propose_patch(finding_id="F-1", target=TARGET, content="x",
                          parent_plan_id=None, rationale="", proof=proof)


class ProposalEvidence(unittest.TestCase):
    def test_recorded_before_apply(self):
        stack = _Stack(self)
        finding = stack.finding("F-1")
        proposal = stack.proposal("F-1", "OK\n")
        evidence_id = stack.remediator.record_proposal(
            proposal, stack.mission)
        recs = [r for r in stack.ledger.all_records()
                if r.get("kind") == "evidence"
                and r.get("producer") == "remediation"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["evidence_id"], evidence_id)
        self.assertEqual(recs[0]["finding_id"], "F-1")
        payload = recs[0]["payload"]
        self.assertEqual(payload["proposal_id"], proposal.proposal_id)
        self.assertEqual(payload["diff_hash"], proposal.diff_hash)
        # Finding untouched by mere recording.
        self.assertEqual(stack.store.get("F-1").state,
                         FindingState.UNVERIFIED)
        self.assertIsNotNone(finding)

    def test_unknown_finding_rejected(self):
        stack = _Stack(self)
        proposal = stack.proposal("F-ghost", "OK\n")
        with self.assertRaises(KeyError):
            stack.remediator.record_proposal(proposal, stack.mission)


class VerifiedPatch(unittest.TestCase):
    def test_full_pass_verifies(self):
        stack = _Stack(self)
        stack.finding("F-1")
        proposal = stack.proposal("F-1", "OK\n")
        stack.remediator.record_proposal(proposal, stack.mission)
        apply_rt = stack.remediator.apply(proposal, stack.mission)
        self.assertEqual(
            apply_rt.broker_result.decision.decision.value, "allow")
        outcome = stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertTrue(outcome.verified)
        self.assertFalse(outcome.refuted)
        self.assertEqual(outcome.reason, "proof-ok:control-clean")
        self.assertEqual(outcome.finding.state, FindingState.VERIFIED)
        self.assertIsNotNone(outcome.proof_runtime)
        self.assertIsNotNone(outcome.control_runtime)
        # WRITE went through the boundary.
        self.assertEqual(
            (stack.workspace.root / TARGET).read_text(
                encoding="utf-8"), "OK\n")


class FailedVerification(unittest.TestCase):
    def test_proof_mismatch_leaves_unverified(self):
        stack = _Stack(self)
        stack.finding("F-1")
        proposal = stack.proposal("F-1", "MEH\n")
        stack.remediator.record_proposal(proposal, stack.mission)
        stack.remediator.apply(proposal, stack.mission)
        outcome = stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertFalse(outcome.verified)
        self.assertFalse(outcome.refuted)
        self.assertTrue(
            outcome.reason.startswith("proof-failed:"))
        self.assertEqual(outcome.finding.state,
                         FindingState.UNVERIFIED)
        # Diagnostic evidence persisted for the Replanner.
        kinds = [r.get("payload", {}).get("kind")
                 for r in stack.ledger.all_records()
                 if r.get("kind") == "evidence"]
        self.assertIn("proof-mismatch", kinds)


class NegativeControlMissing(unittest.TestCase):
    def test_refusal_without_state_change(self):
        stack = _Stack(self)
        stack.finding("F-1")
        proof = RetestSpec(capability=Capability.READ, target=TARGET,
                           expected_substring="OK")
        proposal = propose_patch(
            finding_id="F-1", target=TARGET, content="OK\n",
            parent_plan_id=None, rationale="r", proof=proof,
            negative_control=None)
        stack.remediator.record_proposal(proposal, stack.mission)
        stack.remediator.apply(proposal, stack.mission)
        outcome = stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertFalse(outcome.verified)
        self.assertFalse(outcome.refuted)
        self.assertEqual(outcome.reason,
                         "refused:negative-control-missing")
        self.assertEqual(stack.store.get("F-1").state,
                         FindingState.UNVERIFIED)


class FailureRefutesAndReplans(unittest.TestCase):
    def test_control_hit_refutes_then_replans(self):
        stack = _Stack(self)
        stack.finding("F-1")
        proposal = stack.proposal("F-1", "OK\nSTILL-BROKEN\n")
        stack.remediator.record_proposal(proposal, stack.mission)
        stack.remediator.apply(proposal, stack.mission)
        outcome = stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertFalse(outcome.verified)
        self.assertTrue(outcome.refuted)
        self.assertEqual(outcome.finding.state, FindingState.REFUTED)
        # Existing Replanner consumes the refutation.
        parent = Plan(plan_id="P-parent",
                      mission_id=stack.mission.mission_id, steps=[])
        records = stack.ledger.records_for_finding("F-1")
        receipts = [EvidenceReceipt(
            evidence_id=r.get("evidence_id", ""),
            sequence=r.get("seq", 0),
            producer=r.get("producer", ""),
            payload=dict(r)) for r in records
            if r.get("kind") == "evidence"]
        ctx = FocusedContext(
            refuted_claim=stack.store.get("F-1"),
            diagnostic_evidence=receipts,
            mission_scope=stack.mission.scope)
        plan_b = stack.replanner.replan(ctx, parent)
        self.assertEqual(plan_b.parent_plan_id, "P-parent")
        self.assertEqual(plan_b.steps[0].requester, "replanner")


class SuccessReachesGate(unittest.TestCase):
    def test_finding_state_no_longer_blocks(self):
        stack = _Stack(self)
        stack.finding("F-1")
        proposal = stack.proposal("F-1", "OK\n")
        stack.remediator.record_proposal(proposal, stack.mission)
        stack.remediator.apply(proposal, stack.mission)
        outcome = stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertTrue(outcome.verified)
        evaluation = stack.gate.evaluate(GateInputs(
            mission=stack.mission,
            findings=list(stack.store.all()),
            regression_ok=False, behavior_probe_ok=False))
        self.assertNotIn("G:finding-state", evaluation.failed)
        # The gate still refuses for the unrelated missing proofs.
        self.assertEqual(evaluation.verdict, GateVerdict.REFUSE)


class RegressionSafety(unittest.TestCase):
    def test_unrelated_findings_untouched(self):
        stack = _Stack(self)
        stack.finding("F-1")
        other = Finding(finding_id="F-other",
                        state=FindingState.UNVERIFIED,
                        summary="other", target=TARGET)
        stack.store.register(other)
        proposal = stack.proposal("F-1", "MEH\n")
        stack.remediator.record_proposal(proposal, stack.mission)
        stack.remediator.apply(proposal, stack.mission)
        stack.remediator.verify(
            proposal, stack.store.get("F-1"), stack.mission)
        self.assertEqual(stack.store.get("F-other").state,
                         FindingState.UNVERIFIED)

    def test_double_propose_is_idempotent(self):
        stack = _Stack(self)
        stack.finding("F-1")
        first = stack.proposal("F-1", "OK\n")
        second = stack.proposal("F-1", "OK\n")
        self.assertEqual(first.proposal_id, second.proposal_id)


if __name__ == "__main__":
    unittest.main()
