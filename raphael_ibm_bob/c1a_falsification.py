"""raphael_ibm_bob.c1a_falsification — active contradiction search.

Falsification looks for a REAL counter-example: an independent C1A
invocation whose provider result hash contradicts the hash the finding
was verified against. Contradiction evidence is persisted with finding
linkage, and a VERIFIED finding transitions to REFUTED.

No counter-example is ever fabricated; if no independent observation is
available the result is INCONCLUSIVE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Optional, Tuple

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


class FalsificationOutcome(str, Enum):
    REFUTED = "refuted"
    NO_COUNTEREXAMPLE = "no-counterexample"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class C1AFalsificationResult:
    outcome: FalsificationOutcome
    detail: str
    evidence_ids: Tuple[str, ...]
    transition_applied: bool


def detect_contradiction(expected_hash: Optional[str],
                         observed_hash: Optional[str]) -> bool:
    """A contradiction exists iff both hashes are present and differ."""
    if expected_hash is None or observed_hash is None:
        return False
    return expected_hash != observed_hash


def contradiction_from_records(
        records: Iterable[Dict]) -> Optional[str]:
    """Find two differing ``result_hash`` values in evidence for one finding.

    Returns a human-readable detail string, or None when no contradiction
    is present in the persisted evidence.
    """
    hashes = []
    for record in records:
        payload = record.get("payload") or {}
        value = payload.get("result_hash")
        if isinstance(value, str) and value:
            hashes.append(value)
    distinct = sorted(set(hashes))
    if len(distinct) >= 2:
        return f"contradictory-result-hashes:{distinct}"
    return None


class C1AFalsifier:
    """Broker-mediated, finding-specific C1A falsification."""

    def __init__(self, runtime: BOBRuntime, ledger: EvidenceLedger,
                 store: Optional[FindingStore] = None):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store

    def challenge(
        self,
        finding: Finding,
        mission: Mission,
        *,
        alternate_target: Optional[str] = None,
        expected_result_hash: Optional[str] = None,
        timeout_seconds: float = 10.0,
        requester: str = "c1a-falsifier",
    ) -> C1AFalsificationResult:
        if finding.state is not FindingState.VERIFIED:
            return C1AFalsificationResult(
                FalsificationOutcome.NO_COUNTEREXAMPLE,
                f"finding-not-verified:{finding.state.value}", (), False)

        target = alternate_target or finding.target
        request = ActionRequest(
            sequence=0,
            requester=requester,
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=target,
            purpose="c1a-falsify",
            finding_id=finding.finding_id,
            timeout_seconds=timeout_seconds,
        )
        runtime_result = self._runtime.submit(request, mission)
        execution = runtime_result.execution
        provider_result = None
        if execution is not None:
            candidate = (execution.evidence or {}).get("provider_result")
            if isinstance(candidate, dict):
                provider_result = candidate
        observed_hash = (provider_result or {}).get("result_hash")
        allowed = (runtime_result.broker_result.decision.decision
                   is Decision.ALLOW)

        evidence_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
            "kind": "c1a-challenge",
            "observed_hash": observed_hash,
        }, prefix="F")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="falsifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload={
                "kind": "c1a-challenge",
                "finding_id": finding.finding_id,
                "capability": Capability.C1A_STATIC_FILE_INSPECT.value,
                "target": target,
                "allowed": allowed,
                "observed_hash": observed_hash,
            },
            finding_id=finding.finding_id,
        )
        evidence_ids = (evidence_id,)

        if not allowed or execution is None or not execution.success:
            return C1AFalsificationResult(
                FalsificationOutcome.INCONCLUSIVE,
                "challenge-not-successful", evidence_ids, False)

        if not detect_contradiction(expected_result_hash, observed_hash):
            return C1AFalsificationResult(
                FalsificationOutcome.NO_COUNTEREXAMPLE,
                "no-contradiction-observed", evidence_ids, False)

        counter_id = digest_id({
            "finding_id": finding.finding_id,
            "observed_hash": observed_hash,
            "expected_hash": expected_result_hash,
            "kind": "c1a-counterexample",
        }, prefix="C")
        self._ledger.append_evidence(
            evidence_id=counter_id,
            producer="falsifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload={
                "kind": "c1a-counterexample",
                "finding_id": finding.finding_id,
                "target": target,
                "expected_hash": expected_result_hash,
                "observed_hash": observed_hash,
                "detail": "result-hash-contradiction",
            },
            finding_id=finding.finding_id,
        )
        evidence_ids = evidence_ids + (counter_id,)

        applied = False
        if self._store is not None:
            try:
                self._store.transition(
                    finding.finding_id,
                    FindingState.REFUTED,
                    evidence_seqs=tuple(
                        s for s in (runtime_result.request_seq,
                                    runtime_result.decision_seq,
                                    runtime_result.result_seq)
                        if s is not None),
                    additional_evidence_ids=list(evidence_ids),
                    extra_payload={"kind": "c1a-refuted",
                                   "observed_hash": observed_hash},
                )
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return C1AFalsificationResult(
            FalsificationOutcome.REFUTED,
            "result-hash-contradiction", evidence_ids, applied)


__all__ = [
    "C1AFalsificationResult",
    "C1AFalsifier",
    "FalsificationOutcome",
    "contradiction_from_records",
    "detect_contradiction",
]
