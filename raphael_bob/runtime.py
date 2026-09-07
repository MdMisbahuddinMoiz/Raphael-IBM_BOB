"""raphael_bob.runtime — BOB MVP Runtime implementation.

The Runtime is the AGENT-FACING boundary. It accepts an `ActionRequest`
from a caller (Planner, Verifier, agent) and submits it through the
Broker. The Runtime itself NEVER performs filesystem, process, or
network actions directly — that is the Broker + capabilities' job.

The Runtime's job at M3 is:

    request -> Broker.submit -> BrokerResult
            -> RuntimeResult (with M3 provenance fields)

It deliberately exposes no path that lets a caller skip the Broker.

Legacy reference (REPLACE; not invoked):
    src/raphael/main.py:30 — Wave 1 cognitive loop entry point.
    src/raphael/executor/executor.py:31 Executor — bypasses Broker;
        MUST NOT be called from the BOB Runtime.
    src/orchestrator/capabilities/interactive_shell/capability.py:58 —
        abstract base for shell capabilities; out of MVP scope.

Remaining limitations at M3:
    - No retry policy.
    - No streaming output.
    - No scheduling; this is a single-request synchronous boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from raphael_bob.broker import BOBBroker, BrokerResult
from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    ExecutionResult,
    Mission,
)


@dataclass(frozen=True)
class RuntimeResult:
    """Public Runtime response."""
    broker_result: BrokerResult
    # On ALLOW, `execution` is set. On DENY, `execution` is None.
    execution: Optional[ExecutionResult]
    # The sequence number stamped by the Broker (provenance).
    sequence: int
    # M3 provenance fields.
    request_seq: int
    decision_seq: int
    result_seq: Optional[int]
    evidence_ids: Tuple[str, ...]


class BOBRuntime:
    """Agent-facing execution boundary. Goes through the Broker only."""

    def __init__(self, broker: BOBBroker):
        if not isinstance(broker, BOBBroker):
            # Structural guard: Runtime may only wrap a BOBBroker.
            raise TypeError(
                f"BOBRuntime requires a BOBBroker instance, got {type(broker).__name__}"
            )
        self._broker = broker

    @property
    def broker(self) -> BOBBroker:
        return self._broker

    def submit(
        self,
        request: ActionRequest,
        mission: Mission,
    ) -> RuntimeResult:
        # Structural guard: reject calls that have not been constructed
        # through the proper factory, ensuring provenance fields exist.
        if not isinstance(request, ActionRequest):
            raise TypeError(
                f"Runtime requires an ActionRequest, got {type(request).__name__}"
            )
        if not isinstance(mission, Mission):
            raise TypeError(
                f"Runtime requires a Mission, got {type(mission).__name__}"
            )
        if not request.requester:
            raise ValueError("ActionRequest.requester is required for provenance")
        if not request.target:
            raise ValueError("ActionRequest.target is required")
        if not request.purpose:
            raise ValueError("ActionRequest.purpose is required")
        if not isinstance(request.capability, Capability):
            raise TypeError(
                f"ActionRequest.capability must be a Capability enum, got "
                f"{type(request.capability).__name__}"
            )

        broker_result = self._broker.submit(request, mission)
        return RuntimeResult(
            broker_result=broker_result,
            execution=broker_result.execution,
            sequence=broker_result.decision.sequence,
            request_seq=broker_result.request_seq,
            decision_seq=broker_result.decision_seq,
            result_seq=broker_result.result_seq,
            evidence_ids=broker_result.evidence_ids,
        )


__all__ = ["BOBRuntime", "RuntimeResult"]