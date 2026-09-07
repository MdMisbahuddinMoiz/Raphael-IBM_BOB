"""raphael_bob.broker — BOB MVP Broker implementation.

The Broker is the MANDATORY mediation layer between any caller (Runtime,
Verifier, Falsifier, Replanner) and any capability. It:

    1. Assigns a dense sequence number to each request.
    2. Consults the Policy BEFORE invoking any capability.
    3. On DENY: returns PolicyDecision without invoking any handler.
    4. On ALLOW: invokes the capability via `execute_capability`.
    5. Returns the PolicyDecision (and, on ALLOW, the ExecutionResult).

The Broker is the ONLY component that calls into `execute_capability`.
Runtime, Verifier, Falsifier, Replanner, QualityGate, Planner, Runner
must all go through the Broker.

Legacy reference (ADAPT, not reused as-is):
    src/orchestrator/brain/capability_broker.py:266 CapabilityBroker
        - 5-dim authorization, deny-by-default, ActionReceipt shape.
        - Rebound at M2 to: capability allow-list, workspace scope,
          mission-scope substring, capability-specific invariants.

Remaining limitations at M2:
    - No persistent evidence ledger (M3 owns this).
    - No rate limiting (MVP does not require it).
    - No replay protection.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from raphael_bob.contracts import (
    ActionRequest,
    Decision,
    ExecutionResult,
    Mission,
    PolicyDecision,
)
from raphael_bob.policy import BOBPolicy
from raphael_bob.capabilities import execute_capability
from raphael_bob.workspace import Workspace


@dataclass(frozen=True)
class BrokerResult:
    """Bundled result of a Broker.submit call."""
    decision: PolicyDecision
    execution: Optional[ExecutionResult]  # set only when ALLOW
    capability_invoked: bool              # True iff execute_capability ran


class BOBBroker:
    """Mandatory mediation layer. Always consults Policy before invoking a capability."""

    def __init__(self, policy: BOBPolicy, workspace: Workspace):
        self._policy = policy
        self._workspace = workspace
        self._lock = threading.Lock()
        self._sequence = 0
        # Diagnostic counters for tests/audit.
        self.submissions: int = 0
        self.allows: int = 0
        self.denies: int = 0
        self.capability_invocations: int = 0
        # An audit log of every decision. At M2 we keep this in-memory;
        # M3 will replace it with an append-only JSONL EvidenceLedger.
        self.audit: List[Dict[str, Any]] = []

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

        # Consult Policy. ALLOW/DENY both must be honoured.
        decision = self._policy.consult(stamped, mission)
        with self._lock:
            if decision.decision == Decision.ALLOW:
                self.allows += 1
            else:
                self.denies += 1
            self.audit.append(
                {"stage": "decision", **decision.to_dict()}
            )

        # On DENY: NO capability invocation, no side effect.
        if decision.decision == Decision.DENY:
            return BrokerResult(
                decision=decision,
                execution=None,
                capability_invoked=False,
            )

        # On ALLOW: invoke the capability. We stamp the ExecutionResult
        # with the same sequence number so the linkage is unambiguous.
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
        return BrokerResult(
            decision=decision,
            execution=execution,
            capability_invoked=True,
        )

    def next_sequence(self) -> int:
        with self._lock:
            return self._sequence + 1


__all__ = ["BOBBroker", "BrokerResult"]