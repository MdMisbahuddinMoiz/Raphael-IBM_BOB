"""raphael_ibm_bob.broker — BOB MVP Broker implementation.

The Broker is the MANDATORY mediation layer between any caller (Runtime,
Verifier, Falsifier, Replanner) and any capability. It:

    1. Assigns a dense sequence number to each request.
    2. Consults the Policy BEFORE invoking any capability.
    3. Persists a canonical RequestRecord to the EvidenceLedger (M3).
    4. Persists a canonical DecisionRecord (ALLOW or DENY) (M3).
    5. On DENY: persists a PolicyEvidenceReceipt and returns
       PolicyDecision without invoking any handler. (M3)
    6. On ALLOW: invokes the capability via `execute_capability`, persists
       a ResultRecord and an ExecutionEvidenceReceipt. (M3)
    7. Returns the PolicyDecision (and, on ALLOW, the ExecutionResult).

The Broker is the ONLY component that calls into `execute_capability`.
Runtime, Verifier, Falsifier, Replanner, QualityGate, Planner, Runner
must all go through the Broker.

Legacy reference (ADAPT, not reused as-is):
    src/orchestrator/brain/capability_broker.py:266 CapabilityBroker
        - 5-dim authorization, deny-by-default, ActionReceipt shape.
        - Rebound at M2 to: capability allow-list, workspace scope,
          mission-scope substring, capability-specific invariants.
    src/orchestrator/brain/evidence.py
        - frozen-dataclass + SHA-256 digest pattern; the BOB MVP uses the
          same digest discipline at the record level.

Remaining limitations at M3:
    - Audit log field is retained for back-compat with M2 tests; the
      authoritative provenance is now the EvidenceLedger.
    - No rate limiting (MVP does not require it).
    - No replay protection.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Decision,
    EvidenceReceipt,
    ExecutionResult,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.capabilities import execute_capability
from raphael_ibm_bob.workspace import Workspace
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id


@dataclass(frozen=True)
class BrokerResult:
    """Bundled result of a Broker.submit call."""
    decision: PolicyDecision
    execution: Optional[ExecutionResult]  # set only when ALLOW
    capability_invoked: bool              # True iff execute_capability ran
    request_seq: int                      # durable ledger sequence
    decision_seq: int                     # durable ledger sequence
    result_seq: Optional[int]            # durable ledger sequence (None on DENY)
    evidence_ids: Tuple[str, ...]         # durable evidence identifiers


class BOBBroker:
    """Mandatory mediation layer. Always consults Policy before invoking a capability.

    If `ledger` is provided, every action persists a canonical record chain
    to the ledger. If `ledger` is None, the broker behaves as it did at M2
    (in-memory audit only).
    """

    def __init__(
        self,
        policy: BOBPolicy,
        workspace: Workspace,
        ledger: Optional[EvidenceLedger] = None,
    ):
        self._policy = policy
        self._workspace = workspace
        self._ledger = ledger
        self._lock = threading.Lock()
        self._sequence = 0
        # Diagnostic counters for tests/audit. Retained from M2.
        self.submissions: int = 0
        self.allows: int = 0
        self.denies: int = 0
        self.capability_invocations: int = 0
        # In-memory audit log retained for back-compat with M2 tests.
        # The authoritative provenance is the ledger.
        self.audit: List[Dict[str, Any]] = []

    @property
    def ledger(self) -> Optional[EvidenceLedger]:
        return self._ledger

    def attach_ledger(self, ledger: EvidenceLedger) -> None:
        """Attach (or replace) the EvidenceLedger after construction."""
        with self._lock:
            self._ledger = ledger

    # Broker.seam interface ----------------------------------------------------

    def submit(self, request: ActionRequest, mission: Mission) -> BrokerResult:
        with self._lock:
            self.submissions += 1
            self._sequence += 1
            # Stamp the request sequence in case the caller did not.
            stamped = ActionRequest(
                sequence=self._sequence,
                requester=request.requester,
                capability=request.capability,
                target=request.target,
                purpose=request.purpose,
                plan_id=request.plan_id,
                finding_id=request.finding_id,
            )
        # Persist the RequestRecord first so subsequent records can link.
        # The ledger's sequence number is the canonical request_seq; the
        # in-broker counter is retained for back-compat with the M2 audit
        # counters but the ledger is the source of truth for ordering.
        if self._ledger is not None:
            request_seq = self._ledger.append_request(stamped)
        else:
            request_seq = self._sequence

        # Consult Policy. ALLOW/DENY both must be honoured.
        decision = self._policy.consult(stamped, mission)
        with self._lock:
            if decision.decision == Decision.ALLOW:
                self.allows += 1
            else:
                self.denies += 1
            self.audit.append({"stage": "decision", **decision.to_dict()})

        # Persist the DecisionRecord.
        decision_seq = self._sequence + 1 if False else None  # placeholder
        if self._ledger is not None:
            decision_seq = self._ledger.append_decision(request_seq, decision)
        else:
            decision_seq = 0

        # Persist a PolicyEvidenceReceipt for the decision itself (always).
        evidence_ids: List[str] = []
        if self._ledger is not None:
            ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "decision": decision.decision.value,
                "reason": decision.reason,
            }, prefix="P")
            payload = {
                "decision": decision.decision.value,
                "reason": decision.reason,
                "capability": decision.capability.value,
                "target": decision.target,
                "request_seq": request_seq,
                "decision_seq": decision_seq,
            }
            self._ledger.append_evidence(
                evidence_id=ev_id,
                producer="policy",
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=None,
                payload=payload,
            )
            evidence_ids.append(ev_id)

        # On DENY: NO capability invocation, no side effect.
        if decision.decision == Decision.DENY:
            return BrokerResult(
                decision=decision,
                execution=None,
                capability_invoked=False,
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=None,
                evidence_ids=tuple(evidence_ids),
            )

        # On ALLOW: invoke the capability. We stamp the ExecutionResult
        # with the same sequence number so the linkage is unambiguous.
        result_seq: Optional[int] = None
        try:
            payload = execute_capability(self._workspace, stamped)
            execution = ExecutionResult(
                sequence=stamped.sequence,
                success=True,
                output="ok",
                error=None,
                evidence=payload,
            )
        except Exception as exc:
            execution = ExecutionResult(
                sequence=stamped.sequence,
                success=False,
                output="",
                error=f"{type(exc).__name__}:{exc}",
                evidence={},
            )

        with self._lock:
            self.capability_invocations += 1
            self.audit.append(
                {"stage": "execution", **execution.to_dict()}
            )

        if self._ledger is not None:
            result_seq = self._ledger.append_result(
                request_seq=request_seq,
                decision_seq=decision_seq,
                result=execution,
            )
            exec_ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
                "success": execution.success,
            }, prefix="X")
            exec_payload = {
                "success": execution.success,
                "output": execution.output,
                "error": execution.error,
                "evidence_keys": sorted(execution.evidence.keys()),
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
            }
            self._ledger.append_evidence(
                evidence_id=exec_ev_id,
                producer="execution",
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=result_seq,
                payload=exec_payload,
            )
            evidence_ids.append(exec_ev_id)

        return BrokerResult(
            decision=decision,
            execution=execution,
            capability_invoked=True,
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            evidence_ids=tuple(evidence_ids),
        )

    def next_sequence(self) -> int:
        with self._lock:
            return self._sequence + 1


__all__ = ["BOBBroker", "BrokerResult"]