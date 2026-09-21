"""raphael_ibm_bob.c1a_evidence — provider receipt -> governed evidence.

Converts a bounded :class:`~raphael_ibm_bob.provider_runtime.ProviderResult`
into an :class:`~raphael_ibm_bob.contracts.ExecutionResult` and appends the
provider evidence to the ledger with an explicit UNTRUSTED marker.

Hard rules:

    * Provider output is EVIDENCE, never authority. It must never create a
      VERIFIED/REFUTED finding, a COMPLETE gate verdict, or an authorization.
    * Any authority key (however normalized) inside a provider-derived
      payload is rejected fail-closed.
    * The untrusted marker ``provider_untrusted=True`` is always present so a
      downstream reader cannot mistake provider bytes for RAPHAEL judgment.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from raphael_ibm_bob.contracts import ExecutionResult
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.provider_runtime import (
    ProviderResult,
    ProviderState,
    _DENIED_NORMALIZED,
    _normalize_key,
)

#: Explicit marker placed on every provider-derived payload.
PROVIDER_UNTRUSTED = "provider_untrusted"


class C1AEvidenceError(Exception):
    """A provider-derived payload violated the evidence contract."""


def assert_no_authority(payload: Dict[str, Any], where: str = "c1a evidence") -> None:
    """Fail closed if any (normalized) authority key is present anywhere."""
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and _normalize_key(key) in _DENIED_NORMALIZED:
                    raise C1AEvidenceError(
                        f"authority key {key!r} is not valid in {where}")
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
    walk(payload)


def provider_result_to_execution(
    result: ProviderResult,
    *,
    sequence: int,
) -> ExecutionResult:
    """Convert a ProviderResult into an ExecutionResult (untrusted evidence).

    ``success`` reflects only that the provider boundary returned a
    schema-valid SUCCESS state — it is NOT a verified finding and NOT a
    mission completion.
    """
    success = result.state is ProviderState.SUCCESS
    output = result.state.value
    evidence: Dict[str, Any] = {
        "provider_result": result.to_dict(),
        PROVIDER_UNTRUSTED: True,
        "capability": result.capability_id,
        "invocation_id": result.invocation_id,
        "proof_session_id": result.proof_session_id,
        "mission_id": result.mission_id,
        "provider_state": result.state.value,
    }
    assert_no_authority(evidence, "provider execution evidence")
    return ExecutionResult(
        sequence=sequence,
        success=success,
        output=output,
        error=(result.error or None),
        evidence=evidence,
    )


def evidence_implies_verified(payload: Dict[str, Any]) -> bool:
    """Provider-derived evidence NEVER implies a verified finding."""
    return False


def evidence_implies_complete(payload: Dict[str, Any]) -> bool:
    """Provider-derived evidence NEVER implies a mission completion."""
    return False


class C1AEvidenceWriter:
    """Appends provider-derived evidence to the ledger, clearly untrusted."""

    def __init__(self, ledger: EvidenceLedger):
        self._ledger = ledger

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def record(
        self,
        result: ProviderResult,
        *,
        request_seq: int,
        decision_seq: int,
        result_seq: Optional[int],
        finding_id: Optional[str] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "kind": "provider-result",
            "provider_id": result.provider_id,
            "capability_id": result.capability_id,
            "invocation_id": result.invocation_id,
            "proof_session_id": result.proof_session_id,
            "mission_id": result.mission_id,
            "state": result.state.value,
            "success": result.success,
            "truncated": result.truncated,
            "cancellation_acknowledged": result.cancellation_acknowledged,
            "orphan_possible": result.orphan_possible,
            "result_count": len(result.results),
            "artifact_count": len(result.artifacts),
            PROVIDER_UNTRUSTED: True,
            "request_seq": request_seq,
            "decision_seq": decision_seq,
            "result_seq": result_seq,
        }
        assert_no_authority(payload, "provider evidence record")
        evidence_id = digest_id({
            "invocation_id": result.invocation_id,
            "request_seq": request_seq,
            "decision_seq": decision_seq,
            "result_seq": result_seq,
            "state": result.state.value,
        }, prefix="X")
        self._ledger.append_evidence(
            evidence_id=evidence_id,
            producer="provider",
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            payload=payload,
            finding_id=finding_id,
        )
        return evidence_id


__all__ = [
    "C1AEvidenceError",
    "C1AEvidenceWriter",
    "PROVIDER_UNTRUSTED",
    "assert_no_authority",
    "evidence_implies_complete",
    "evidence_implies_verified",
    "provider_result_to_execution",
]
