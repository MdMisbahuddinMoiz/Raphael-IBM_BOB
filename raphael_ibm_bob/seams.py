"""raphael_ibm_bob.seams — interface contracts for the IBM BOB MVP control loop.

Each Protocol below defines the target shape of one component in the brief's
control flow:

    Mission -> Planner -> Plan A
              -> Runtime -> Broker -> Policy -> Capability
              -> EvidenceLedger (append)
              -> Verifier -> Finding
              -> Falsifier
              -> FocusedContext -> Replanner -> Plan B
              -> QualityGate -> COMPLETE / REFUSE

The M1 milestone establishes these as Protocols only. Implementations and
adapters are introduced in M2..M6. The seams are deliberately small so that
legacy Raphael machinery can later sit behind them via explicit adapters.

Status language:
    IMPLEMENTED         - protocol defined and importable.
    PHYSICALLY VERIFIED - exercised by tests in tests/test_seam_*.py.
    NOT IMPLEMENTED     - implementations deferred.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Decision,
    EvidenceReceipt,
    ExecutionResult,
    Finding,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    PolicyDecision,
)


# -----------------------------------------------------------------------------
# Policy — declarative authority
# -----------------------------------------------------------------------------

@runtime_checkable
class Policy(Protocol):
    """Decides whether a request is permitted under the mission scope.

    Implementations MUST be pure with respect to inputs (no side effects) and
    MUST consult the active mission scope. M2 will provide a real
    implementation that delegates to raphael_ibm_bob.adapters.legacy_policy.
    """

    def consult(
        self,
        request: ActionRequest,
        mission: Mission,
    ) -> PolicyDecision:
        ...


# -----------------------------------------------------------------------------
# Broker — mediation point
# -----------------------------------------------------------------------------

@runtime_checkable
class Broker(Protocol):
    """The single mediation point between any caller and the Runtime.

    The Broker consults the Policy and emits a PolicyDecision. It MUST be
    called for every ActionRequest. The Verifier, Falsifier, and Replanner
    MUST go through the Broker too (M4/M5).

    The Broker is also responsible for sequencing requests: it assigns and
    enforces dense sequence numbers within a run.
    """

    def submit(
        self,
        request: ActionRequest,
        mission: Mission,
    ) -> PolicyDecision:
        ...

    def next_sequence(self) -> int:
        ...


# -----------------------------------------------------------------------------
# Runtime — agent-facing execution boundary
# -----------------------------------------------------------------------------

@runtime_checkable
class Runtime(Protocol):
    """The agent-facing execution boundary.

    The Runtime accepts only requests that have already been permitted by
    the Broker. It dispatches to a capability-specific adapter and returns
    an ExecutionResult. The Runtime MUST NOT perform work that bypasses the
    Broker or Policy.
    """

    def execute(
        self,
        request: ActionRequest,
        decision: PolicyDecision,
    ) -> ExecutionResult:
        ...


# -----------------------------------------------------------------------------
# EvidenceLedger — append-only evidence
# -----------------------------------------------------------------------------

@runtime_checkable
class EvidenceLedger(Protocol):
    """Append-only ledger of EvidenceReceipt records.

    The ledger MUST be append-only. Updates and deletes MUST be rejected.
    M3 will provide a JSONL-backed implementation that also writes to disk.
    """

    def append(self, receipt: EvidenceReceipt) -> str:
        ...

    def get(self, evidence_id: str) -> Optional[EvidenceReceipt]:
        ...

    def by_sequence(self, sequence: int) -> List[EvidenceReceipt]:
        ...

    def all(self) -> List[EvidenceReceipt]:
        ...


# -----------------------------------------------------------------------------
# Verifier — independent reproduction
# -----------------------------------------------------------------------------

@runtime_checkable
class Verifier(Protocol):
    """Independent reproduction / retest of a candidate Finding.

    The Verifier MUST itself go through the Broker (so it cannot bypass
    Policy). It returns the updated Finding state. M4 will provide a real
    implementation that delegates behavioral retest to a verifier adapter.
    """

    def verify(self, finding: Finding) -> Finding:
        ...


# -----------------------------------------------------------------------------
# Falsifier — actively challenges apparent success
# -----------------------------------------------------------------------------

@runtime_checkable
class Falsifier(Protocol):
    """Actively challenges apparent success by searching for behavioral
    invariants that the candidate Finding does not satisfy.

    M4 will provide a real implementation. The contract is intentionally
    minimal: it returns a Finding whose state may be REFUTED if the
    falsifier's challenge finds a counter-example.
    """

    def challenge(self, finding: Finding) -> Finding:
        ...


# -----------------------------------------------------------------------------
# Replanner — produces Plan B from evidence
# -----------------------------------------------------------------------------

@runtime_checkable
class Replanner(Protocol):
    """Produces Plan B from a refuted claim and its diagnostic evidence.

    The Replanner MUST be invoked only by the control loop in response to a
    REFUTED finding. It MAY also be invoked when the Falsifier reports a
    regression. The Replanner MUST NOT be called arbitrarily by an agent.
    """

    def replan(
        self,
        context: FocusedContext,
        parent_plan: Plan,
    ) -> Plan:
        ...


# -----------------------------------------------------------------------------
# QualityGate — sole authority for COMPLETE
# -----------------------------------------------------------------------------

@runtime_checkable
class QualityGate(Protocol):
    """Sole authority that may issue COMPLETE.

    The Planner, Runner, and CLI MUST NOT independently declare COMPLETE.
    The gate evaluates mission criteria, evidence completeness, behavior
    probe results, and regression status. Failure of any required condition
    returns REFUSE rather than false completion.
    """

    def evaluate(
        self,
        mission: Mission,
        findings: List[Finding],
        evidence: List[EvidenceReceipt],
        behavior_probe_ok: bool,
        regression_ok: bool,
    ) -> GateVerdict:
        ...


# -----------------------------------------------------------------------------
# Planner — generates Plan A
# -----------------------------------------------------------------------------

@runtime_checkable
class Planner(Protocol):
    """Generates Plan A from a Mission and the current evidence state.

    M5 will provide a real implementation that delegates to raphael_ibm_bob
    adapters wrapping the cognitive-loop Action/Precondition model.
    """

    def plan(
        self,
        mission: Mission,
        evidence: List[EvidenceReceipt],
    ) -> Plan:
        ...


# -----------------------------------------------------------------------------
# Runner — drives the control loop
# -----------------------------------------------------------------------------

@runtime_checkable
class Runner(Protocol):
    """Drives the control loop and persists state.

    The Runner is the only entity that may advance sequence numbers and
    append to the EvidenceLedger. M6 will provide the concrete runner.
    """

    def run(self, mission: Mission) -> GateVerdict:
        ...


__all__ = [
    "Policy",
    "Broker",
    "Runtime",
    "EvidenceLedger",
    "Verifier",
    "Falsifier",
    "Replanner",
    "QualityGate",
    "Planner",
    "Runner",
]