"""raphael_ibm_bob.remediation — T1-2 patch propose/verify loop.

Generalizes the authkit remediation pattern (v1 false fix, probe red,
v2 real fix, probe green) into a reusable workflow over EXISTING
capabilities (WRITE/READ/RUN_TEST) and EXISTING verification
machinery (Verifier retest, Falsifier challenge). No new execution
engine, no patch platform, no scenario hardcoding.

Adapted concepts (not copied code):
- Decepticon `patch_propose` / `patch_verify`
  (`packages/decepticon/decepticon/tools/research/patch.py`):
  record the proposal BEFORE applying; verify by re-running the
  ORIGINAL proof; accept only when failure signals disappear.
- Decepticon `validate_finding` negative control / ZFP
  (`.../tools/research/tools.py:1868`): a counter-check that keeps
  verification honest.

Deliberately NOT imported: knowledge graph, severity models, sandbox
runners, agent plugins, PoC libraries. The semantic flow:

    Finding -> PatchProposal -> proposal evidence
    -> Policy-authorized WRITE application
    -> original proof retest (Verifier)
    -> negative control (Falsifier)
    -> VERIFIED, or REFUTED with diagnostic evidence for Replanner
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult
from raphael_ibm_bob.verifier import RetestSpec, Verifier


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


@dataclass(frozen=True)
class PatchProposal:
    """A remediation proposal for one finding at one target.

    `content` is the complete intended file text applied with a
    broker-mediated WRITE. `proof` re-runs the ORIGINAL failure
    signal (file content is never accepted as proof by itself).
    `negative_control`, when present, is a Falsifier challenge that
    must observe NOTHING for the fix to count; a missing control
    refuses verification rather than passing silently.
    """
    proposal_id: str
    finding_id: str
    target: str
    content: str
    parent_plan_id: Optional[str]
    rationale: str
    proof: RetestSpec
    negative_control: Optional[ChallengeSpec] = None

    @property
    def diff_hash(self) -> str:
        return hashlib.sha256(
            self.content.encode("utf-8")).hexdigest()[:16]

    def to_evidence_payload(self) -> dict:
        return {
            "kind": "patch-proposal",
            "proposal_id": self.proposal_id,
            "finding_id": self.finding_id,
            "target": self.target,
            "diff_hash": self.diff_hash,
            "parent_plan_id": self.parent_plan_id,
            "rationale": self.rationale,
        }


def propose_patch(*, finding_id: str, target: str, content: str,
                  parent_plan_id: Optional[str],
                  rationale: str, proof: RetestSpec,
                  negative_control: Optional[ChallengeSpec] = None,
                  ) -> PatchProposal:
    """Create a validated, deterministically-identified proposal."""
    if not finding_id:
        raise ValueError("finding_id is required")
    if not target:
        raise ValueError("target is required")
    if not rationale:
        raise ValueError("rationale is required")
    if not isinstance(proof, RetestSpec):
        raise ValueError("proof must be a RetestSpec")
    if (negative_control is not None
            and not isinstance(negative_control, ChallengeSpec)):
        raise ValueError("negative_control must be a ChallengeSpec")
    proposal_id = "PX-" + hashlib.sha256(_canonical({
        "finding_id": finding_id,
        "target": target,
        "content": content,
    }).encode("utf-8")).hexdigest()[:12]
    return PatchProposal(
        proposal_id=proposal_id,
        finding_id=finding_id,
        target=target,
        content=content,
        parent_plan_id=parent_plan_id,
        rationale=rationale,
        proof=proof,
        negative_control=negative_control,
    )


@dataclass(frozen=True)
class RemediationOutcome:
    """Result of applying + verifying one proposal."""
    proposal: PatchProposal
    finding: Finding
    applied: bool
    verified: bool
    refuted: bool
    reason: str
    apply_runtime: Optional[RuntimeResult] = None
    proof_runtime: Optional[RuntimeResult] = None
    control_runtime: Optional[RuntimeResult] = None


class Remediator:
    """Applies PatchProposals through the boundary and verifies them."""

    def __init__(self, runtime: BOBRuntime, ledger: EvidenceLedger,
                 store: FindingStore, verifier: Verifier,
                 falsifier: Falsifier):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._verifier = verifier
        self._falsifier = falsifier

    def record_proposal(self, proposal: PatchProposal,
                        mission: Mission) -> str:
        """Persist the proposal BEFORE applying (Decepticon pattern:
        the proposal is captured even if application later fails)."""
        known = self._store.get(proposal.finding_id)
        if known is None:
            raise KeyError(
                f"unknown finding_id: {proposal.finding_id}")
        payload = proposal.to_evidence_payload()
        evidence_id = digest_id(payload, prefix="PP")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="remediation",
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            payload=payload,
            finding_id=proposal.finding_id,
        )
        return evidence_id

    def apply(self, proposal: PatchProposal,
              mission: Mission) -> RuntimeResult:
        """Apply the proposal as a broker-mediated WRITE.

        Raises on DENY: a refused remediation is loud, never silent.
        """
        result = self._runtime.submit(ActionRequest(
            sequence=0,
            requester="remediation",
            capability=Capability.WRITE,
            target=proposal.target,
            purpose="content=" + proposal.content,
            finding_id=proposal.finding_id,
        ), mission)
        if result.broker_result.decision.decision is not Decision.ALLOW:
            raise RuntimeError(
                f"remediation WRITE denied for {proposal.target}: "
                f"{result.broker_result.decision.reason}")
        return result

    def verify(self, proposal: PatchProposal, finding: Finding,
               mission: Mission,
               requester: str = "remediation") -> RemediationOutcome:
        """Re-run the original proof, then the negative control.

        - No negative control -> refusal (no state change).
        - Proof mismatch/deny -> failure (finding left UNVERIFIED with
          diagnostic evidence; the caller may replan or revise).
        - Proof ok + control clean -> VERIFIED (via the real Verifier).
        - Proof ok + control hit -> REFUTED (via the real Falsifier)
          with counter-evidence the Replanner can consume.
        """
        if proposal.negative_control is None:
            return RemediationOutcome(
                proposal=proposal, finding=finding,
                applied=True, verified=False, refuted=False,
                reason="refused:negative-control-missing",
            )
        verify_out = self._verifier.verify(
            finding, proposal.proof, mission, requester=requester)
        if not verify_out.transition_applied:
            self._ledger.append_evidence(
                evidence_id=digest_id({
                    "proposal_id": proposal.proposal_id,
                    "finding_id": finding.finding_id,
                    "kind": "proof-mismatch",
                }, prefix="PM"),
                producer="remediation",
                request_seq=verify_out.retest_runtime.request_seq,
                decision_seq=verify_out.retest_runtime.decision_seq,
                result_seq=verify_out.retest_runtime.result_seq,
                payload={
                    "kind": "proof-mismatch",
                    "proposal_id": proposal.proposal_id,
                    "finding_id": finding.finding_id,
                },
                finding_id=finding.finding_id,
            )
            return RemediationOutcome(
                proposal=proposal,
                finding=self._store.get(finding.finding_id) or finding,
                applied=True, verified=False, refuted=False,
                reason=f"proof-failed:{verify_out.transition_reason}",
                proof_runtime=verify_out.retest_runtime,
            )
        current = self._store.get(finding.finding_id) or finding
        challenge_out = self._falsifier.challenge(
            current, proposal.negative_control, mission,
            requester=requester)
        updated = self._store.get(finding.finding_id) or current
        if challenge_out.counter_example_observed:
            return RemediationOutcome(
                proposal=proposal, finding=updated,
                applied=True, verified=False, refuted=True,
                reason="control-hit:counter-example-observed",
                proof_runtime=verify_out.retest_runtime,
                control_runtime=challenge_out.challenge_runtime,
            )
        return RemediationOutcome(
            proposal=proposal, finding=updated,
            applied=True, verified=True, refuted=False,
            reason="proof-ok:control-clean",
            proof_runtime=verify_out.retest_runtime,
            control_runtime=challenge_out.challenge_runtime,
        )


__all__ = [
    "PatchProposal",
    "RemediationOutcome",
    "Remediator",
    "propose_patch",
]
