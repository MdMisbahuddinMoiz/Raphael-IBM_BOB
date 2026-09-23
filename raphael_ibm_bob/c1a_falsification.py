"""raphael_ibm_bob.c1a_falsification — active contradiction search.

Falsification looks for a REAL counter-example: an independent C1A
invocation whose provider result hash contradicts the hash the finding
was verified against. Contradiction evidence is persisted with finding
linkage, and a VERIFIED finding transitions to REFUTED.

No counter-example is ever fabricated; if no independent observation is
available the result is INCONCLUSIVE.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.c1a_verification import (
    ExecutionRef,
    IndependenceChecks,
    LineageValidation,
    VerificationRequest,
    VerificationRequestError,
    VerificationInProgressError,
    _safe_observation,
    _read_original_result_hash,
    _read_verified_result_hash,
    evaluate_independence,
    execution_ref_from_runtime_result,
    validate_lineage,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.runtime import BOBRuntime

#: Module-private possession token; only the governed falsifier holds it.
_FALSIFICATION_MINT = object()


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
        # D4 Phase 11: at most ONE active independent falsification per
        # finding. Deterministic and fail-closed.
        self._active_falsifications: set = set()
        self._active_lock = threading.Lock()

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

        authoritative_hash = _read_verified_result_hash(
            self._ledger, finding.finding_id)
        effective_hash = (authoritative_hash
                          if authoritative_hash is not None
                          else expected_result_hash)

        if not detect_contradiction(effective_hash, observed_hash):
            return C1AFalsificationResult(
                FalsificationOutcome.NO_COUNTEREXAMPLE,
                "no-contradiction-observed", evidence_ids, False)

        counter_id = digest_id({
            "finding_id": finding.finding_id,
            "observed_hash": observed_hash,
            "expected_hash": effective_hash,
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
                "expected_hash": effective_hash,
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

    # --- D4 governed independent falsification ----------------------------

    def challenge_independent(
        self,
        request: VerificationRequest,
        mission: Mission,
        *,
        expected_result_hash: Optional[str] = None,
        timeout_seconds: float = 10.0,
        requester: str = "c1a-falsifier",
    ) -> "FalsificationResult":
        """Run a NEW governed execution that actively challenges a finding.

        Falsification never reinterprets the original execution: it produces
        a fresh provider observation through the ordinary Broker path and
        only transitions VERIFIED -> REFUTED when its OWN execution
        contradicts the expected observation and every independence/lineage
        check passed. At most one active falsification per finding.
        """
        if request.purpose != "falsify":
            raise VerificationRequestError(
                "challenge_independent requires a purpose='falsify' request")
        with self._active_lock:
            if request.finding_id in self._active_falsifications:
                raise VerificationInProgressError(
                    f"falsification already active for finding "
                    f"{request.finding_id!r}")
            self._active_falsifications.add(request.finding_id)
        try:
            return self._execute_and_assess_falsification(
                request, mission,
                expected_result_hash=expected_result_hash,
                timeout_seconds=timeout_seconds,
                requester=requester)
        finally:
            with self._active_lock:
                self._active_falsifications.discard(request.finding_id)

    def _execute_and_assess_falsification(
        self,
        request: VerificationRequest,
        mission: Mission,
        *,
        expected_result_hash: Optional[str],
        timeout_seconds: float,
        requester: str,
    ) -> "FalsificationResult":
        # Fail closed BEFORE any provider execution when the store does not
        # own the finding or the finding is not in VERIFIED state.
        if self._store is not None:
            known = self._store.get(request.finding_id)
            if known is None or known.state is not FindingState.VERIFIED:
                state = known.state.value if known is not None else "missing"
                absent = ExecutionRef(
                    mission_id=request.mission_id, run_id="",
                    execution_id="", invocation_id="",
                    provider_result_ref="", finding_id=request.finding_id)
                checks = IndependenceChecks(
                    False, False, False, False, False, False)
                lineage = LineageValidation(
                    False, (f"finding-not-challengeable:{state}",))
                result_id = digest_id({
                    "kind": "falsification-result",
                    "verification_request_ref": request.record_id,
                    "finding_id": request.finding_id,
                    "classification": "insufficient",
                }, prefix="FRS")
                return FalsificationResult(
                    result_id=result_id,
                    classification=FalsificationClassification.INSUFFICIENT,
                    verification_request_ref=request.record_id,
                    falsification_execution=absent,
                    finding_id=request.finding_id,
                    mission_id=request.mission_id,
                    independence=checks,
                    lineage=lineage,
                    observation={},
                    evidence_ids=(),
                    transition_applied=False,
                    _mint=_FALSIFICATION_MINT,
                )
        action = ActionRequest(
            sequence=0,
            requester=requester,
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=request.target,
            purpose=f"d4-{request.purpose}",
            finding_id=request.finding_id,
            timeout_seconds=timeout_seconds,
        )
        runtime_result = self._runtime.submit(action, mission)
        execution = runtime_result.execution
        provider_result = {}
        if execution is not None:
            candidate = (execution.evidence or {}).get("provider_result")
            if isinstance(candidate, dict):
                provider_result = candidate
        falsification_execution = execution_ref_from_runtime_result(
            runtime_result, mission_id=request.mission_id,
            finding_id=request.finding_id)
        allowed = (runtime_result.broker_result.decision.decision
                   is Decision.ALLOW)
        independence = evaluate_independence(
            request=request,
            verification=falsification_execution,
            provider_result=provider_result,
            replay_guard=getattr(self._runtime.broker, "c1a_replay_guard", None),
            ledger=self._ledger,
        )
        lineage = validate_lineage(
            request=request,
            verification=falsification_execution,
            provider_result=provider_result,
            ledger=self._ledger,
        )
        observed_hash = provider_result.get("result_hash")
        authoritative_hash = _read_original_result_hash(
            self._ledger, original_execution=request.original_execution)
        effective_hash = (authoritative_hash
                          if authoritative_hash is not None
                          else expected_result_hash)
        if not independence.all_passed or not lineage.valid:
            classification = FalsificationClassification.INSUFFICIENT
        elif not allowed or execution is None or not execution.success:
            classification = FalsificationClassification.INCONCLUSIVE
        elif effective_hash is None:
            classification = FalsificationClassification.INCONCLUSIVE
        elif observed_hash is not None and observed_hash != effective_hash:
            classification = FalsificationClassification.DISPROVED
        else:
            classification = FalsificationClassification.NOT_DISPROVED

        result_id = digest_id({
            "kind": "falsification-result",
            "verification_request_ref": request.record_id,
            "finding_id": request.finding_id,
            "mission_id": request.mission_id,
            "classification": classification.value,
            "execution_id": falsification_execution.execution_id,
            "invocation_id": falsification_execution.invocation_id,
            "provider_result_ref": falsification_execution.provider_result_ref,
        }, prefix="FRS")
        result = FalsificationResult(
            result_id=result_id,
            classification=classification,
            verification_request_ref=request.record_id,
            falsification_execution=falsification_execution,
            finding_id=request.finding_id,
            mission_id=request.mission_id,
            independence=independence,
            lineage=lineage,
            observation=_safe_observation(provider_result,
                                          falsification_execution),
            evidence_ids=(),
            transition_applied=False,
            _mint=_FALSIFICATION_MINT,
        )
        payload = {
            "kind": "falsification-result",
            **result.to_dict(),
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
        }
        evidence_id = digest_id(payload, prefix="FR")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="falsifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload=payload,
            finding_id=request.finding_id,
        )

        applied = False
        if (classification is FalsificationClassification.DISPROVED
                and independence.all_passed and lineage.valid
                and self._store is not None):
            try:
                self._store.transition(
                    request.finding_id,
                    FindingState.REFUTED,
                    evidence_seqs=tuple(
                        s for s in (runtime_result.request_seq,
                                    runtime_result.decision_seq,
                                    runtime_result.result_seq)
                        if s is not None),
                    additional_evidence_ids=[evidence_id],
                    extra_payload={
                        "kind": "d4-refuted",
                        "mission_id": request.mission_id,
                        "classification": classification.value,
                        "falsification_result_id": result.result_id,
                    },
                )
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return replace(result,
                       evidence_ids=(evidence_id,) + tuple(runtime_result.evidence_ids),
                       transition_applied=applied)


class FalsificationClassification(str, Enum):
    """Factual classification of an independent falsification (NOT authority)."""
    DISPROVED = "disproved"
    NOT_DISPROVED = "not-disproved"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class FalsificationResult:
    """A minted, factual falsification classification (NOT authority)."""
    result_id: str
    classification: FalsificationClassification
    verification_request_ref: str
    falsification_execution: ExecutionRef
    finding_id: str
    mission_id: str
    independence: IndependenceChecks
    lineage: LineageValidation
    observation: Dict[str, Any]
    evidence_ids: Tuple[str, ...] = ()
    transition_applied: bool = False
    _mint: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _FALSIFICATION_MINT:
            raise VerificationRequestError(
                "FalsificationResult must be minted by the governed falsifier")

    @property
    def disproved(self) -> bool:
        return self.classification is FalsificationClassification.DISPROVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "classification": self.classification.value,
            "disproved": self.disproved,
            "verification_request_ref": self.verification_request_ref,
            "falsification_execution": self.falsification_execution.to_dict(),
            "finding_id": self.finding_id,
            "mission_id": self.mission_id,
            "independence": self.independence.to_dict(),
            "lineage": self.lineage.to_dict(),
            "observation": dict(self.observation),
            "evidence_ids": list(self.evidence_ids),
            "transition_applied": self.transition_applied,
        }


__all__ = [
    "C1AFalsificationResult",
    "C1AFalsifier",
    "FalsificationClassification",
    "FalsificationOutcome",
    "FalsificationResult",
    "contradiction_from_records",
    "detect_contradiction",
]
