"""raphael_ibm_bob.c1a_verification — independent C1A reproduction.

A C1A finding is only VERIFIED when an INDEPENDENT reproduction (a fresh
Broker-mediated C1A invocation) succeeds AND its provider result hash
matches the expectation the caller supplies. A provider success alone is
never sufficient: provider output is untrusted evidence.

Boundary: this module consumes the Runtime (Broker -> Policy) and the
FindingStore; it never touches the provider directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.runtime import BOBRuntime


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class C1AVerificationResult:
    outcome: VerificationOutcome
    reasons: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    invocation_id: Optional[str]
    provider_state: Optional[str]
    result_hash: Optional[str]
    transition_applied: bool


def _provider_result(execution) -> Optional[dict]:
    if execution is None:
        return None
    evidence = execution.evidence or {}
    result = evidence.get("provider_result")
    return result if isinstance(result, dict) else None


class C1AVerifier:
    """Broker-mediated, finding-specific C1A verification."""

    def __init__(self, runtime: BOBRuntime, ledger: EvidenceLedger,
                 store: Optional[FindingStore] = None):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store

    @property
    def store(self) -> Optional[FindingStore]:
        return self._store

    def verify(
        self,
        finding: Finding,
        mission: Mission,
        *,
        expected_result_hash: Optional[str] = None,
        timeout_seconds: float = 10.0,
        requester: str = "c1a-verifier",
    ) -> C1AVerificationResult:
        if finding.state is not FindingState.UNVERIFIED:
            return C1AVerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                reasons=(f"finding-not-unverified:{finding.state.value}",),
                evidence_ids=(), invocation_id=None,
                provider_state=None, result_hash=None,
                transition_applied=False)

        request = ActionRequest(
            sequence=0,
            requester=requester,
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=finding.target,
            purpose="c1a-verify",
            finding_id=finding.finding_id,
            timeout_seconds=timeout_seconds,
        )
        runtime_result = self._runtime.submit(request, mission)
        execution = runtime_result.execution
        provider_result = _provider_result(execution)
        provider_state = (provider_result or {}).get("state")
        result_hash = (provider_result or {}).get("result_hash")
        invocation_id = (provider_result or {}).get("invocation_id")

        allowed = (runtime_result.broker_result.decision.decision
                   is Decision.ALLOW)
        evidence_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
            "kind": "c1a-retest",
            "provider_state": provider_state,
            "result_hash": result_hash,
        }, prefix="V")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="verifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload={
                "kind": "c1a-retest",
                "finding_id": finding.finding_id,
                "capability": Capability.C1A_STATIC_FILE_INSPECT.value,
                "target": finding.target,
                "allowed": allowed,
                "provider_state": provider_state,
                "result_hash": result_hash,
                "invocation_id": invocation_id,
            },
            finding_id=finding.finding_id,
        )
        evidence_ids = (evidence_id,) + tuple(runtime_result.evidence_ids)

        if not allowed:
            return C1AVerificationResult(
                VerificationOutcome.INCONCLUSIVE,
                (f"retest-denied:{runtime_result.broker_result.decision.reason}",),
                evidence_ids, invocation_id, provider_state, result_hash, False)
        if execution is None or not execution.success:
            return C1AVerificationResult(
                VerificationOutcome.INCONCLUSIVE,
                ("retest-not-successful",), evidence_ids, invocation_id,
                provider_state, result_hash, False)
        if expected_result_hash is None:
            return C1AVerificationResult(
                VerificationOutcome.INCONCLUSIVE,
                ("no-expectation-supplied",), evidence_ids, invocation_id,
                provider_state, result_hash, False)
        if result_hash != expected_result_hash:
            return C1AVerificationResult(
                VerificationOutcome.INCONCLUSIVE,
                (f"result-hash-mismatch:{result_hash!r}",), evidence_ids,
                invocation_id, provider_state, result_hash, False)

        applied = False
        if self._store is not None:
            try:
                self._store.transition(
                    finding.finding_id,
                    FindingState.VERIFIED,
                    evidence_seqs=tuple(
                        s for s in (runtime_result.request_seq,
                                    runtime_result.decision_seq,
                                    runtime_result.result_seq)
                        if s is not None),
                    additional_evidence_ids=[evidence_id],
                    extra_payload={"kind": "c1a-verified",
                                   "result_hash": result_hash},
                )
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return C1AVerificationResult(
            VerificationOutcome.VERIFIED,
            ("independent-reproduction-matched",),
            evidence_ids, invocation_id, provider_state, result_hash, applied)


__all__ = [
    "C1AVerificationResult",
    "C1AVerifier",
    "VerificationOutcome",
]
