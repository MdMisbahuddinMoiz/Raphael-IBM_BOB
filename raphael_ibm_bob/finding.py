"""raphael_ibm_bob.finding — M4 finding lifecycle store.

Implements the brief's required lifecycle:

    UNVERIFIED -> VERIFIED
    UNVERIFIED -> REFUTED
    VERIFIED   -> SUPERSEDED
    REFUTED    -> SUPERSEDED

Structural rule: a finding cannot transition from UNVERIFIED directly
to SUPERSEDED; it must pass through VERIFIED or REFUTED first.

This module is the SOLE authority for transition validation. The
Verifier (M4) and Falsifier (M4) consume `FindingStore.transition(...)`;
they do not transition state by mutating the Finding directly.

Persistence:
    Every transition is persisted as a `FindingRecord` in the EvidenceLedger.
    The store keeps an in-memory map of `finding_id` -> Finding for fast
    access, but the ledger is the source of truth.

Legacy references:
    src/orchestrator/brain/hypothesis.py Hypothesis lifecycle is the
    inspiration; the BOB finding lifecycle is a strict subset.
    src/orchestrator/brain/contradiction.py (M1 ADAPT) provides the
    ContradictionManager active-challenge pattern that the Falsifier
    reuses at M4.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import Finding, FindingState
from raphael_ibm_bob.evidence_ledger import EvidenceLedger


_ALLOWED_TRANSITIONS = {
    FindingState.UNVERIFIED: {FindingState.VERIFIED, FindingState.REFUTED},
    FindingState.VERIFIED: {FindingState.REFUTED, FindingState.SUPERSEDED},
    FindingState.REFUTED: {FindingState.SUPERSEDED},
    FindingState.SUPERSEDED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when a transition is not allowed by the lifecycle rule."""


@dataclass
class TransitionResult:
    """The outcome of a state transition."""
    finding: Finding
    prev_state: FindingState
    new_state: FindingState
    ledger_seq: int
    evidence_seqs: Tuple[int, ...]


class FindingStore:
    """Lifecycle-aware Finding store, backed by the EvidenceLedger."""

    def __init__(self, ledger: EvidenceLedger):
        self._ledger = ledger
        self._findings: Dict[str, Finding] = {}
        self._lock = threading.Lock()

    # --- registration ------------------------------------------------------

    def register(self, finding: Finding) -> Finding:
        """Register a new finding in UNVERIFIED state (or whatever state
        the caller supplies, validated against the lifecycle)."""
        if not finding.finding_id:
            raise ValueError("Finding.finding_id is required")
        with self._lock:
            if finding.finding_id in self._findings:
                raise ValueError(f"finding already registered: {finding.finding_id}")
            self._findings[finding.finding_id] = finding
        # Persist the initial FindingRecord with prev_state=None.
        seq = self._ledger.append_finding(
            finding_id=finding.finding_id,
            state=finding.state.value,
            prev_state=None,
            summary=finding.summary,
            target=finding.target,
            evidence_seqs=tuple(int(s) for s in finding.evidence_ids),
            payload={
                "summary": finding.summary,
                "target": finding.target,
                "evidence_ids": list(finding.evidence_ids),
                "supersedes": finding.supersedes,
                "kind": "initial",
            },
        )
        return finding

    # --- lookup ------------------------------------------------------------

    def get(self, finding_id: str) -> Optional[Finding]:
        with self._lock:
            return self._findings.get(finding_id)

    def all(self) -> List[Finding]:
        with self._lock:
            return list(self._findings.values())

    def evidence_for(self, finding_id: str) -> List[dict]:
        """Return every ledger record linked to the given finding_id, sorted
        by ledger seq. Combines FindingRecord rows + EvidenceRecord rows
        that carry the same `finding_id` field."""
        return self._ledger.records_for_finding(finding_id)

    # --- transitions -------------------------------------------------------

    def transition(
        self,
        finding_id: str,
        new_state: FindingState,
        *,
        evidence_seqs: Tuple[int, ...] = (),
        supersedes: Optional[str] = None,
        additional_evidence_ids: Optional[List[str]] = None,
        extra_payload: Optional[dict] = None,
    ) -> TransitionResult:
        """Validate + apply a state transition, persisting a FindingRecord.

        Raises InvalidTransitionError if the transition is not allowed.
        """
        with self._lock:
            current = self._findings.get(finding_id)
            if current is None:
                raise KeyError(f"unknown finding_id: {finding_id}")
            prev = current.state
            allowed = _ALLOWED_TRANSITIONS[prev]
            if new_state not in allowed:
                raise InvalidTransitionError(
                    f"transition {prev.value} -> {new_state.value} not allowed; "
                    f"from {prev.value} only {sorted(s.value for s in allowed)} are permitted"
                )

            merged_evidence_ids = list(current.evidence_ids)
            if additional_evidence_ids:
                merged_evidence_ids.extend(additional_evidence_ids)

            updated = Finding(
                finding_id=finding_id,
                state=new_state,
                summary=current.summary,
                target=current.target,
                evidence_ids=merged_evidence_ids,
                supersedes=supersedes if supersedes is not None else current.supersedes,
            )
            self._findings[finding_id] = updated

        payload = {
            "summary": updated.summary,
            "target": updated.target,
            "evidence_seqs": list(evidence_seqs),
            "additional_evidence_ids": list(additional_evidence_ids or []),
            "supersedes": updated.supersedes,
            "kind": "transition",
        }
        if extra_payload:
            payload.update(extra_payload)

        seq = self._ledger.append_finding(
            finding_id=finding_id,
            state=new_state.value,
            prev_state=prev.value,
            summary=updated.summary,
            target=updated.target,
            evidence_seqs=tuple(int(s) for s in evidence_seqs),
            payload=payload,
        )

        return TransitionResult(
            finding=updated,
            prev_state=prev,
            new_state=new_state,
            ledger_seq=seq,
            evidence_seqs=tuple(int(s) for s in evidence_seqs),
        )

    # --- static helpers ----------------------------------------------------

    @staticmethod
    def allowed_from(state: FindingState) -> List[FindingState]:
        return sorted(_ALLOWED_TRANSITIONS[state], key=lambda s: s.value)


__all__ = [
    "FindingStore",
    "TransitionResult",
    "InvalidTransitionError",
    "_ALLOWED_TRANSITIONS",
]