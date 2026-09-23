"""Read-only D14 view over the production evidence ledger."""
from __future__ import annotations

from raphael_ibm_bob.d14_state_codec import EvidenceBinding
from raphael_ibm_bob.evidence_ledger import EvidenceLedger


class EvidenceLedgerView:
    """Expose only authenticated ledger reads required by D14 ingestion."""

    def __init__(self, ledger: EvidenceLedger) -> None:
        self._ledger = ledger

    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        """Resolve an evidence receipt to its ALLOW/result binding."""
        receipt = self._ledger.get(evidence_id)
        if receipt is None:
            return None
        payload = receipt.payload
        request_seq = payload.get("request_seq")
        decision_seq = payload.get("decision_seq")
        if not isinstance(request_seq, int) or not isinstance(decision_seq, int):
            return None
        records = self._ledger.reader().by_request_seq(request_seq)
        decision = next(
            (record for record in records
             if record.get("kind") == "decision"
             and record.get("seq") == decision_seq),
            None,
        )
        result = next(
            (record for record in records if record.get("kind") == "result"),
            None,
        )
        if decision is None or result is None:
            return None
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            session_id = _session_id_from_records(records)
        return EvidenceBinding(
            evidence_id=evidence_id,
            request_seq=request_seq,
            policy_decision=str(decision.get("decision", "")),
            result_success=result.get("success") is True,
            session_id=session_id,
            decision_seq=decision_seq,
            result_seq=payload.get("result_seq"),
        )


def _session_id_from_records(records: list[dict]) -> str | None:
    """Read a session binding when a producer did not repeat it in payload."""
    for record in records:
        value = record.get("session_id")
        if isinstance(value, str) and value:
            return value
    return None


__all__ = ["EvidenceLedgerView"]
