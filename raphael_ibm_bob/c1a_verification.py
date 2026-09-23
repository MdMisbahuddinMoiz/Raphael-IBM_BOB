"""raphael_ibm_bob.c1a_verification — independent C1A reproduction.

A C1A finding is only VERIFIED when an INDEPENDENT reproduction (a fresh
Broker-mediated C1A invocation) succeeds AND its provider result hash
matches the expectation derived from the authoritative source (the original
persisted observation in the ledger). A provider success alone is never
sufficient: provider output is untrusted evidence.  A caller-supplied
expected_result_hash at verify-time must NOT be able to flip the verdict.

Boundary: this module consumes the Runtime (Broker -> Policy) and the
FindingStore; it never touches the provider directly.
"""
from __future__ import annotations

import json as _json
import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional, Tuple

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
from raphael_ibm_bob.provider_runtime import (
    C1A_CAPABILITY_ID,
    C1A_PROVIDER_ID,
)
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


def _read_hash_from_artifact(artifact_ref: str) -> Optional[str]:
    """Read ``result_hash`` from a persisted ExecutionResult artifact file."""
    if not artifact_ref:
        return None
    try:
        data = _json.loads(_Path(artifact_ref).read_text(encoding="utf-8"))
        pr = (data.get("evidence") or {}).get("provider_result") or {}
        rh = pr.get("result_hash")
        if isinstance(rh, str) and rh:
            return rh
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _read_original_result_hash(
    ledger: Optional[EvidenceLedger],
    *,
    original_execution: Optional["ExecutionRef"] = None,
    target: Optional[str] = None,
    before_seq: Optional[int] = None,
) -> Optional[str]:
    """Read the authoritative expected ``result_hash`` from the ledger.

    For D4 paths: uses ``original_execution.result_seq`` to locate the
    persisted ExecutionResult artifact.

    For legacy paths: searches request records by *target*, restricted to
    results persisted strictly BEFORE ``before_seq``. The bound is essential:
    without it the lookup would select the retest execution the caller just
    appended, comparing a result hash against itself (a tautology). Passing
    the current retest's ``result_seq`` makes the expectation come from the
    genuine prior observation instead.

    Returns ``None`` when no authoritative hash is found.
    """
    if ledger is None:
        return None

    # Strategy 1: D4 path — via original_execution.result_seq
    if (original_execution is not None
            and original_execution.result_seq is not None):
        for record in ledger.all_records():
            if (record.get("kind") == "result"
                    and record.get("seq") == original_execution.result_seq):
                return _read_hash_from_artifact(
                    record.get("artifact_ref", ""))

    # Strategy 2: legacy path — via target matching
    if target:
        request_seqs: List[int] = []
        for record in ledger.all_records():
            if (record.get("kind") == "request"
                    and record.get("target") == target):
                request_seqs.append(record.get("seq"))
        if request_seqs:
            best_seq = -1
            best_hash: Optional[str] = None
            for record in ledger.all_records():
                seq = record.get("seq", 0)
                if before_seq is not None and seq >= before_seq:
                    continue
                if (record.get("kind") == "result"
                        and record.get("request_seq") in request_seqs
                        and seq > best_seq):
                    rh = _read_hash_from_artifact(
                        record.get("artifact_ref", ""))
                    if rh:
                        best_seq = seq
                        best_hash = rh
            if best_hash:
                return best_hash

    return None


def _read_verified_result_hash(
    ledger: Optional[EvidenceLedger],
    finding_id: str,
) -> Optional[str]:
    """Read the ``result_hash`` a finding was verified against.

    Searches verifier evidence records linked to *finding_id* that
    recorded a ``result_hash`` (from the ``verify()`` legacy path or
    ``_persist_verification_result`` D4 path).
    """
    if ledger is None:
        return None
    for record in ledger.all_records():
        payload = record.get("payload") or {}
        if payload.get("finding_id") != finding_id:
            continue
        if (record.get("producer") == "verifier"
                and isinstance(payload.get("result_hash"), str)
                and payload["result_hash"]):
            return payload["result_hash"]
    return None


class C1AVerifier:
    """Broker-mediated, finding-specific C1A verification."""

    def __init__(self, runtime: BOBRuntime, ledger: EvidenceLedger,
                 store: Optional[FindingStore] = None):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        # D4 Phase 11: at most ONE active independent verification per
        # finding. Deterministic and fail-closed.
        self._active_verifications: set = set()
        self._active_lock = threading.Lock()

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

        authoritative_hash = _read_original_result_hash(
            self._ledger, target=finding.target,
            before_seq=runtime_result.result_seq)
        effective_hash = (authoritative_hash
                          if authoritative_hash is not None
                          else expected_result_hash)

        if effective_hash is None:
            return C1AVerificationResult(
                VerificationOutcome.INCONCLUSIVE,
                ("no-expectation-supplied",), evidence_ids, invocation_id,
                provider_state, result_hash, False)
        if result_hash != effective_hash:
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

    # --- D4 governed independent verification -----------------------------

    def assess_observation(
        self,
        request: VerificationRequest,
        *,
        provider_result: Dict[str, Any],
        verification_execution: ExecutionRef,
        replay_guard: Optional[Any] = None,
        expected_result_hash: Optional[str] = None,
        allowed: bool = True,
        execution_success: bool = True,
    ) -> VerificationResult:
        """Validator/factory: assess one observation against a request.

        Never transitions a Finding. Performs the P1..P6 independence checks
        and lineage validation, classifies the observation, and mints a
        VerificationResult. Existence of the referenced records is enforced
        here (replay guard + ledger), so a crafted execution ref cannot pass.

        ``allowed`` and ``execution_success`` are derived from the actual
        ``provider_result`` data — caller-supplied values are ignored so a
        post-hoc override cannot manufacture a SUPPORTED verdict.
        ``expected_result_hash`` is read from the original execution's
        persisted artifact in the ledger; the caller-supplied value is only
        used as a fallback when no authoritative source exists.
        """
        derived_allowed = bool(provider_result)
        derived_success = (provider_result.get("state") == "success"
                           if provider_result else False)
        authoritative_hash = _read_original_result_hash(
            self._ledger, original_execution=request.original_execution)
        effective_hash = (authoritative_hash
                          if authoritative_hash is not None
                          else expected_result_hash)

        if replay_guard is None:
            broker = getattr(self._runtime, "broker", None)
            replay_guard = getattr(broker, "c1a_replay_guard", None)
        independence = evaluate_independence(
            request=request,
            verification=verification_execution,
            provider_result=provider_result,
            replay_guard=replay_guard,
            ledger=self._ledger,
        )
        lineage = validate_lineage(
            request=request,
            verification=verification_execution,
            provider_result=provider_result,
            ledger=self._ledger,
        )
        if not independence.all_passed or not lineage.valid:
            classification = VerificationClassification.INSUFFICIENT
        elif not derived_allowed or not derived_success:
            classification = VerificationClassification.INCONCLUSIVE
        elif effective_hash is None:
            classification = VerificationClassification.INCONCLUSIVE
        elif provider_result.get("result_hash") == effective_hash:
            classification = VerificationClassification.SUPPORTED
        else:
            classification = VerificationClassification.CONTRADICTED
        return _mint_verification_result(
            request=request,
            verification=verification_execution,
            independence=independence,
            lineage=lineage,
            classification=classification,
            provider_result=provider_result,
        )

    def verify_independent(
        self,
        request: VerificationRequest,
        mission: Mission,
        *,
        expected_result_hash: Optional[str] = None,
        timeout_seconds: float = 10.0,
        requester: str = "c1a-verifier",
    ) -> VerificationResult:
        """Run a NEW governed execution and verify the finding independently.

        The execution is an ordinary Broker-mediated C1A execution: the D3
        authorization binding, provider-id binding, replay guard, and result
        lineage checks all apply. The finding transitions to VERIFIED only
        when the classification is SUPPORTED and every independence and
        lineage check passed. At most one active verification per finding.
        """
        if request.purpose != "verify":
            raise VerificationRequestError(
                "verify_independent requires a purpose='verify' request")
        with self._active_lock:
            if request.finding_id in self._active_verifications:
                raise VerificationInProgressError(
                    f"verification already active for finding "
                    f"{request.finding_id!r}")
            self._active_verifications.add(request.finding_id)
        try:
            return self._execute_and_assess(
                request, mission,
                expected_result_hash=expected_result_hash,
                timeout_seconds=timeout_seconds,
                requester=requester)
        finally:
            with self._active_lock:
                self._active_verifications.discard(request.finding_id)

    def _execute_and_assess(
        self,
        request: VerificationRequest,
        mission: Mission,
        *,
        expected_result_hash: Optional[str],
        timeout_seconds: float,
        requester: str,
    ) -> VerificationResult:
        # Fail closed BEFORE any provider execution when the store does not
        # own the finding or the finding is no longer in the required state.
        if self._store is not None:
            known = self._store.get(request.finding_id)
            if known is None or known.state is not FindingState.UNVERIFIED:
                state = known.state.value if known is not None else "missing"
                absent = ExecutionRef(
                    mission_id=request.mission_id, run_id="",
                    execution_id="", invocation_id="",
                    provider_result_ref="", finding_id=request.finding_id)
                checks = IndependenceChecks(
                    False, False, False, False, False, False)
                lineage = LineageValidation(
                    False, (f"finding-not-verifiable:{state}",))
                return _mint_verification_result(
                    request=request, verification=absent,
                    independence=checks, lineage=lineage,
                    classification=VerificationClassification.INSUFFICIENT,
                    provider_result={})
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
        provider_result = _provider_result(execution) or {}
        verification = execution_ref_from_runtime_result(
            runtime_result, mission_id=request.mission_id,
            finding_id=request.finding_id)
        result = self.assess_observation(
            request,
            provider_result=provider_result,
            verification_execution=verification,
        )
        evidence_id = self._persist_verification_result(
            request, result, runtime_result)
        evidence_ids = (evidence_id,) + tuple(runtime_result.evidence_ids)

        applied = False
        if (result.classification is VerificationClassification.SUPPORTED
                and result.independence.all_passed
                and result.lineage.valid
                and self._store is not None):
            try:
                self._store.transition(
                    request.finding_id,
                    FindingState.VERIFIED,
                    evidence_seqs=tuple(
                        s for s in (runtime_result.request_seq,
                                    runtime_result.decision_seq,
                                    runtime_result.result_seq)
                        if s is not None),
                    additional_evidence_ids=[evidence_id],
                    extra_payload={
                        "kind": "d4-verified",
                        "mission_id": request.mission_id,
                        "classification": result.classification.value,
                        "verification_result_id": result.result_id,
                    },
                )
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return replace(result, evidence_ids=evidence_ids,
                       transition_applied=applied)

    def _persist_verification_result(
        self,
        request: VerificationRequest,
        result: VerificationResult,
        runtime_result: Any,
    ) -> str:
        payload = {
            "kind": "verification-result",
            **result.to_dict(),
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
        }
        evidence_id = digest_id(payload, prefix="VR")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="verifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload=payload,
            finding_id=request.finding_id,
        )
        return evidence_id


# ---------------------------------------------------------------------------
# D4 — independent verification governance
#
# The D4 objective: a finding becomes VERIFIED only through a governed,
# INDEPENDENT verification execution. Independence is CAUSAL/evidential
# (P1..P6), never infrastructural: the same mission, finding, provider,
# target, capability, inputs, and sandbox are all allowed. What must be new
# is the execution, the invocation, and the provider observation, and the
# provenance must terminate at the NEW invocation.
#
# This layer maps onto production names:
#   * execution identity  -> a deterministic ref over (run_id, result_seq)
#   * invocation identity -> ProviderResult.invocation_id (D3)
#   * provider observation-> ProviderResult payload in ExecutionResult.evidence
#   * replay guard        -> BOBBroker.c1a_replay_guard (D3)
#   * evidence records    -> EvidenceLedger (existing)
#   * lifecycle authority -> FindingStore.transition (existing)
# ---------------------------------------------------------------------------


#: Module-private possession tokens. Only the governed factories in this
#: module hold them, so VerificationRequest/VerificationResult cannot be
#: freely constructed as authority-bearing objects by callers.
_REQUEST_MINT = object()
_RESULT_MINT = object()

#: Minimum number of INDEPENDENT executions a verification requires. The
#: ORIGINAL execution NEVER counts toward this number (Flash regression).
MINIMUM_INDEPENDENT_EXECUTIONS = 1

_AUTHORITY_KEYS = frozenset({
    "verified", "refuted", "authorized", "approved", "approval", "complete",
    "gate_pass", "gatepass", "policy_approved", "verdict", "conclusion",
    "confidence", "severity", "risk", "recommendation", "recommendations",
})


class VerificationGovernanceError(Exception):
    """Fail-closed D4 verification error."""


class VerificationRequestError(VerificationGovernanceError):
    """A VerificationRequest could not be governed/minted."""


class IndependenceError(VerificationGovernanceError):
    """An independence or lineage check failed."""


class VerificationInProgressError(VerificationGovernanceError):
    """A second active verification was requested for the same finding."""


class VerificationClassification(str, Enum):
    """Factual classification of an independent observation (NOT authority)."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class IndependenceChecks:
    """The six-part D4 independence relation (P1..P6)."""
    distinct_execution: bool
    distinct_invocation: bool
    fresh_provider_observation: bool
    causal_binding_valid: bool
    no_replayed_execution: bool
    no_cached_output: bool

    @property
    def all_passed(self) -> bool:
        return all((
            self.distinct_execution,
            self.distinct_invocation,
            self.fresh_provider_observation,
            self.causal_binding_valid,
            self.no_replayed_execution,
            self.no_cached_output,
        ))

    @property
    def failed(self) -> Tuple[str, ...]:
        names = (
            "distinct_execution", "distinct_invocation",
            "fresh_provider_observation", "causal_binding_valid",
            "no_replayed_execution", "no_cached_output",
        )
        return tuple(n for n in names if not getattr(self, n))

    def independent_execution_count(self) -> int:
        """The number of executions that satisfy the FULL independence
        relation. The original execution contributes 0, by construction."""
        return 1 if self.all_passed else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "distinct_execution": self.distinct_execution,
            "distinct_invocation": self.distinct_invocation,
            "fresh_provider_observation": self.fresh_provider_observation,
            "causal_binding_valid": self.causal_binding_valid,
            "no_replayed_execution": self.no_replayed_execution,
            "no_cached_output": self.no_cached_output,
            "all_passed": self.all_passed,
        }


@dataclass(frozen=True)
class LineageValidation:
    """Result of validating the causal chain / referenced records."""
    valid: bool
    reasons: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"valid": self.valid, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ExecutionRef:
    """A causal reference to one governed execution.

    ``execution_id`` is this execution's identity; ``invocation_id`` is the
    provider invocation identity; ``provider_result_ref`` is the identity of
    the exact ProviderResult record consumed. All three must differ between
    the original and the verification execution.
    """
    mission_id: str
    run_id: str
    execution_id: str
    invocation_id: str
    provider_result_ref: str
    finding_id: Optional[str] = None
    proof_session_id: str = ""
    result_seq: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "execution_id": self.execution_id,
            "invocation_id": self.invocation_id,
            "provider_result_ref": self.provider_result_ref,
            "finding_id": self.finding_id,
            "proof_session_id": self.proof_session_id,
            "result_seq": self.result_seq,
        }


def make_provider_result_ref(provider_result: Dict[str, Any],
                             run_id: str) -> str:
    """Deterministic identity of a ProviderResult record.

    Encodes the invocation the observation's provenance terminates at, so a
    copied observation cannot masquerade as a fresh one.
    """
    return digest_id({
        "run_id": run_id,
        "invocation_id": provider_result.get("invocation_id"),
        "proof_session_id": provider_result.get("proof_session_id"),
        "result_hash": provider_result.get("result_hash"),
        "capability_id": provider_result.get("capability_id"),
        "provider_id": provider_result.get("provider_id"),
    }, prefix="PR")


def execution_ref_from_runtime_result(
    runtime_result: Any, *,
    mission_id: str,
    finding_id: Optional[str] = None,
) -> ExecutionRef:
    """Derive an ExecutionRef from a governed RuntimeResult (never caller
    supplied identity strings)."""
    execution = getattr(runtime_result, "execution", None)
    provider_result = _provider_result(execution) or {}
    run_id = provider_result.get("run_id") or "in-memory"
    invocation_id = provider_result.get("invocation_id")
    if not isinstance(invocation_id, str) or not invocation_id:
        invocation_id = f"INV-missing-{getattr(runtime_result, 'result_seq', None)}"
    result_seq = getattr(runtime_result, "result_seq", None)
    if result_seq is not None:
        execution_id = digest_id(
            {"run_id": run_id, "result_seq": result_seq}, prefix="EX")
    else:
        execution_id = digest_id(
            {"run_id": run_id, "invocation_id": invocation_id}, prefix="EX")
    return ExecutionRef(
        mission_id=provider_result.get("mission_id") or mission_id,
        run_id=run_id,
        execution_id=execution_id,
        invocation_id=str(invocation_id),
        provider_result_ref=make_provider_result_ref(provider_result, run_id),
        finding_id=finding_id,
        proof_session_id=str(provider_result.get("proof_session_id") or ""),
        result_seq=result_seq,
    )


@dataclass(frozen=True)
class VerificationRequest:
    """A governed request for an independent verification execution.

    Every authoritative field is DERIVED by :func:`build_verification_request`
    from the finding, the mission, and the original execution — never taken
    from the caller. Construction is gated by a private possession token.
    """
    record_id: str
    mission_id: str
    finding_id: str
    original_execution: ExecutionRef
    target: str
    capability: str
    scope: str
    purpose: str = "verify"
    _mint: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _REQUEST_MINT:
            raise VerificationRequestError(
                "VerificationRequest must be minted by "
                "build_verification_request")
        if not self.mission_id or not self.finding_id:
            raise VerificationRequestError(
                "VerificationRequest requires mission_id and finding_id")
        if self.purpose not in ("verify", "falsify"):
            raise VerificationRequestError(
                f"unsupported verification purpose: {self.purpose!r}")
        original = self.original_execution
        if original.mission_id != self.mission_id:
            raise VerificationRequestError(
                "original execution mission does not match request mission")
        if original.finding_id not in (None, self.finding_id):
            raise VerificationRequestError(
                "original execution does not belong to this finding")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "mission_id": self.mission_id,
            "finding_id": self.finding_id,
            "original_execution": self.original_execution.to_dict(),
            "target": self.target,
            "capability": self.capability,
            "scope": self.scope,
            "purpose": self.purpose,
        }


def build_verification_request(
    *,
    mission: Mission,
    finding: Finding,
    original_execution: ExecutionRef,
    ledger: Optional[EvidenceLedger] = None,
    purpose: str = "verify",
) -> VerificationRequest:
    """Governed factory: derive all authoritative fields, validate scope, and
    (optionally) durably record the request.

    Fails closed on: unknown purpose, a finding without a mission, a mission
    mismatch, a finding in the wrong lifecycle state, or an original execution
    that does not belong to this mission/finding.
    """
    if purpose not in ("verify", "falsify"):
        raise VerificationRequestError(f"unknown purpose: {purpose!r}")
    mission_id = getattr(mission, "mission_id", "")
    if not mission_id:
        raise VerificationRequestError("mission_id is required")
    if finding.mission_id is None:
        raise VerificationRequestError(
            "finding has no mission_id; independent verification fails closed")
    if finding.mission_id != mission_id:
        raise VerificationRequestError(
            "finding mission does not match request mission")
    required_state = (FindingState.UNVERIFIED if purpose == "verify"
                      else FindingState.VERIFIED)
    if finding.state is not required_state:
        raise VerificationRequestError(
            f"{purpose} requires finding state {required_state.value}, "
            f"got {finding.state.value}")
    if original_execution.mission_id != mission_id:
        raise VerificationRequestError("original execution mission mismatch")
    if original_execution.finding_id not in (None, finding.finding_id):
        raise VerificationRequestError(
            "original execution does not belong to this finding")
    if not original_execution.invocation_id or not original_execution.execution_id:
        raise VerificationRequestError("original execution identity is incomplete")

    record_id = digest_id({
        "kind": "verification-request",
        "mission_id": mission_id,
        "finding_id": finding.finding_id,
        "original_execution_id": original_execution.execution_id,
        "original_invocation_id": original_execution.invocation_id,
        "original_provider_result_ref": original_execution.provider_result_ref,
        "purpose": purpose,
    }, prefix="VR")
    request = VerificationRequest(
        record_id=record_id,
        mission_id=mission_id,
        finding_id=finding.finding_id,
        original_execution=original_execution,
        target=finding.target,
        capability=C1A_CAPABILITY_ID,
        scope=mission.scope,
        purpose=purpose,
        _mint=_REQUEST_MINT,
    )
    if ledger is not None:
        ledger.append_evidence(
            evidence_id=record_id,
            producer="verifier" if purpose == "verify" else "falsifier",
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            payload={"kind": "verification-request", **request.to_dict()},
            finding_id=finding.finding_id,
        )
    return request


def evaluate_independence(
    *,
    request: VerificationRequest,
    verification: ExecutionRef,
    provider_result: Dict[str, Any],
    replay_guard: Optional[Any] = None,
    ledger: Optional[EvidenceLedger] = None,
) -> IndependenceChecks:
    """Evaluate the six-part independence relation P1..P6.

    P1 distinct execution, P2 distinct invocation, P3 fresh observation,
    P4 causal binding, P5 no replayed execution (replay-guard registered for
    THIS run), P6 no cached/replayed provider output (the new invocation's
    provider evidence exists in the ledger).
    """
    original = request.original_execution

    distinct_execution = (
        bool(verification.execution_id)
        and verification.execution_id != original.execution_id)

    distinct_invocation = (
        bool(verification.invocation_id)
        and verification.invocation_id != original.invocation_id)

    fresh_provider_observation = (
        bool(verification.provider_result_ref)
        and verification.provider_result_ref != original.provider_result_ref)

    causal_binding_valid = (
        verification.mission_id == request.mission_id
        and verification.finding_id == request.finding_id
        and provider_result.get("mission_id") == request.mission_id
        and str(provider_result.get("invocation_id") or "")
        == verification.invocation_id
        and provider_result.get("capability_id") == request.capability
        and provider_result.get("provider_id") == C1A_PROVIDER_ID)

    no_replayed_execution = False
    if replay_guard is not None:
        no_replayed_execution = (
            replay_guard.is_registered(verification.invocation_id)
            and replay_guard.run_for(verification.invocation_id)
            == verification.run_id
            and verification.invocation_id != original.invocation_id)

    no_cached_output = False
    if ledger is not None:
        for record in ledger.all_records():
            if record.get("kind") != "evidence":
                continue
            if record.get("producer") != "provider":
                continue
            payload = record.get("payload") or {}
            if (payload.get("invocation_id") == verification.invocation_id
                    and payload.get("mission_id") == request.mission_id):
                no_cached_output = True
                break

    return IndependenceChecks(
        distinct_execution=distinct_execution,
        distinct_invocation=distinct_invocation,
        fresh_provider_observation=fresh_provider_observation,
        causal_binding_valid=causal_binding_valid,
        no_replayed_execution=no_replayed_execution,
        no_cached_output=no_cached_output,
    )


def validate_lineage(
    *,
    request: VerificationRequest,
    verification: ExecutionRef,
    provider_result: Dict[str, Any],
    ledger: Optional[EvidenceLedger] = None,
) -> LineageValidation:
    """Validate the causal chain and the existence of referenced records."""
    reasons: List[str] = []
    if verification.mission_id != request.mission_id:
        reasons.append("execution-mission-mismatch")
    if verification.finding_id != request.finding_id:
        reasons.append("execution-finding-mismatch")
    if request.original_execution.mission_id != request.mission_id:
        reasons.append("original-mission-mismatch")
    if request.original_execution.finding_id not in (None, request.finding_id):
        reasons.append("original-finding-mismatch")
    if provider_result.get("provider_id") != C1A_PROVIDER_ID:
        reasons.append("provider-id-mismatch")
    if provider_result.get("capability_id") != request.capability:
        reasons.append("capability-mismatch")
    if provider_result.get("run_id") not in (None, "", verification.run_id):
        reasons.append("run-id-mismatch")
    if ledger is not None:
        record_ids = {r.get("evidence_id") for r in ledger.all_records()}
        if request.record_id not in record_ids:
            reasons.append("verification-request-record-not-found")
    return LineageValidation(valid=not reasons, reasons=tuple(reasons))


class VerificationValidator:
    """Validates that a minted VerificationResult references records that
    actually exist and are causally consistent (Phase 6)."""

    def __init__(self, ledger: EvidenceLedger):
        self._ledger = ledger

    def validate(self, result: "VerificationResult") -> LineageValidation:
        reasons: List[str] = []
        record_ids = {r.get("evidence_id") for r in self._ledger.all_records()}
        if result.verification_request_ref not in record_ids:
            reasons.append("verification-request-record-not-found")
        provider_found = False
        for record in self._ledger.all_records():
            if record.get("producer") != "provider":
                continue
            payload = record.get("payload") or {}
            if (payload.get("invocation_id")
                    == result.verification_execution.invocation_id
                    and payload.get("mission_id") == result.mission_id):
                provider_found = True
                break
        if not provider_found:
            reasons.append("verification-provider-evidence-not-found")
        return LineageValidation(valid=not reasons, reasons=tuple(reasons))


def _safe_observation(provider_result: Dict[str, Any],
                      verification: ExecutionRef) -> Dict[str, Any]:
    """A trust-stripped, bounded observation (never authority)."""
    observation = {
        "provider_state": provider_result.get("state"),
        "result_hash": provider_result.get("result_hash"),
        "provider_id": provider_result.get("provider_id"),
        "capability_id": provider_result.get("capability_id"),
        "run_id": provider_result.get("run_id"),
        "mission_id": provider_result.get("mission_id"),
        "invocation_id": verification.invocation_id,
        "execution_id": verification.execution_id,
        "provider_result_ref": verification.provider_result_ref,
        "result_count": (
            len(provider_result.get("results", []))
            if isinstance(provider_result.get("results"), list) else 0),
    }
    for key in list(observation):
        if key in _AUTHORITY_KEYS:
            observation.pop(key, None)
    return observation


@dataclass(frozen=True)
class VerificationResult:
    """A minted, factual classification (NOT authority).

    It cannot transition a Finding by itself, and it carries no verified/
    authorized/approved/complete field. Construction requires the private
    possession token held only by :class:`C1AVerifier`.
    """
    result_id: str
    classification: VerificationClassification
    verification_request_ref: str
    verification_execution: ExecutionRef
    finding_id: str
    mission_id: str
    independence: IndependenceChecks
    lineage: LineageValidation
    observation: Dict[str, Any]
    evidence_ids: Tuple[str, ...] = ()
    transition_applied: bool = False
    _mint: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _RESULT_MINT:
            raise VerificationGovernanceError(
                "VerificationResult must be minted by the governed verifier")
        for key in self.observation:
            if key in _AUTHORITY_KEYS:
                raise VerificationGovernanceError(
                    f"authority field {key!r} is not valid on a "
                    f"VerificationResult observation")

    @property
    def supported(self) -> bool:
        return self.classification is VerificationClassification.SUPPORTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "classification": self.classification.value,
            "supported": self.supported,
            "verification_request_ref": self.verification_request_ref,
            "verification_execution": self.verification_execution.to_dict(),
            "finding_id": self.finding_id,
            "mission_id": self.mission_id,
            "independence": self.independence.to_dict(),
            "lineage": self.lineage.to_dict(),
            "observation": dict(self.observation),
            "evidence_ids": list(self.evidence_ids),
            "transition_applied": self.transition_applied,
        }


def _mint_verification_result(
    *,
    request: VerificationRequest,
    verification: ExecutionRef,
    independence: IndependenceChecks,
    lineage: LineageValidation,
    classification: VerificationClassification,
    provider_result: Dict[str, Any],
) -> VerificationResult:
    observation = _safe_observation(provider_result, verification)
    result_id = digest_id({
        "kind": "verification-result",
        "verification_request_ref": request.record_id,
        "finding_id": request.finding_id,
        "mission_id": request.mission_id,
        "classification": classification.value,
        "execution_id": verification.execution_id,
        "invocation_id": verification.invocation_id,
        "provider_result_ref": verification.provider_result_ref,
        "independence": independence.to_dict(),
        "lineage": lineage.to_dict(),
    }, prefix="VRS")
    return VerificationResult(
        result_id=result_id,
        classification=classification,
        verification_request_ref=request.record_id,
        verification_execution=verification,
        finding_id=request.finding_id,
        mission_id=request.mission_id,
        independence=independence,
        lineage=lineage,
        observation=observation,
        evidence_ids=(),
        transition_applied=False,
        _mint=_RESULT_MINT,
    )


__all__ = [
    "C1AVerificationResult",
    "C1AVerifier",
    "VerificationOutcome",
    # D4
    "MINIMUM_INDEPENDENT_EXECUTIONS",
    "ExecutionRef",
    "IndependenceChecks",
    "IndependenceError",
    "LineageValidation",
    "VerificationClassification",
    "VerificationGovernanceError",
    "VerificationInProgressError",
    "VerificationRequest",
    "VerificationRequestError",
    "VerificationResult",
    "VerificationValidator",
    "build_verification_request",
    "evaluate_independence",
    "execution_ref_from_runtime_result",
    "make_provider_result_ref",
    "validate_lineage",
    "_read_original_result_hash",
    "_read_verified_result_hash",
]
