"""raphael_bob.contracts — typed data contracts for the IBM BOB MVP seam.

Stdlib-only. These types define the *shape* of every request, decision, and
result that crosses a seam boundary. No behavioral logic lives here.

The contracts establish provenance-carrying records so M2+ can wire them
through Broker/Policy/Runtime/EvidenceLedger without ambiguity.

Status language:
    IMPLEMENTED         - dataclass/enum defined and importable.
    PHYSICALLY VERIFIED - exercised by tests in tests/test_seam_*.py.
    NOT IMPLEMENTED     - reserved for downstream milestones.
    UNKNOWN             - no evidence yet.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# -----------------------------------------------------------------------------
# Capabilities and decisions
# -----------------------------------------------------------------------------

class Capability(str, Enum):
    """The MVP capability allow-list.

    The brief restricts the MVP to these five capabilities. Anything outside
    this set is OUT OF SCOPE for the BOB MVP and must be requested through
    legacy adapters explicitly marked ISOLATE.
    """
    READ = "read"
    LIST = "list"
    SEARCH = "search"
    WRITE = "write"
    RUN_TEST = "run_test"


class Decision(str, Enum):
    """Policy / Broker outcomes for an ActionRequest."""
    ALLOW = "allow"
    DENY = "deny"


class FindingState(str, Enum):
    """Lifecycle states for a Finding.

    Target transitions:
        UNVERIFIED -> VERIFIED       (after broker-mediated retest passes)
        UNVERIFIED -> REFUTED        (after falsifier or independent probe)
        VERIFIED   -> SUPERSEDED     (when a later finding replaces it)
        REFUTED    -> SUPERSEDED     (when a later finding replaces it)

    Structural rule enforced at M4/M5: UNVERIFIED cannot transition directly
    to SUPERSEDED without passing through VERIFIED or REFUTED first.
    """
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"


class GateVerdict(str, Enum):
    """Output Quality Gate verdicts.

    COMPLETE is only ever produced by QualityGate. The Planner, Runner, or
    CLI must not produce it independently.
    """
    COMPLETE = "complete"
    REFUSE = "refuse"


# -----------------------------------------------------------------------------
# Identifiers and provenance
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Seq:
    """Logical sequence number for an event in a run.

    Sequence numbers are dense integers assigned by the EventBus / Runtime
    layer in causal order. They are the primary ordering key for append-only
    evidence. Frozen so they cannot be silently rewritten.
    """
    n: int


def fresh_id(prefix: str) -> str:
    """Deterministic-shape UUID v4 with a stable prefix.

    Deterministic-shape: 36-char canonical UUID with prefix. Not a substitute
    for cryptographic identity; only used for in-run uniqueness. UUID is
    generated lazily so importing this module is side-effect free.
    """
    return f"{prefix}-{uuid.uuid4()}"


# -----------------------------------------------------------------------------
# Request / decision / result
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionRequest:
    """A request to perform one capability action against one target.

    Provenance fields:
        sequence     - dense sequence number in the current run
        requester    - identifier of the originator (mission, plan, replanner)
        capability   - Capability enum value
        target       - canonical target identifier (file path, test id, etc.)
        purpose      - free-text or causal reference (e.g. "verify finding F-12")
        plan_id      - optional plan this action belongs to
        finding_id   - optional finding this action causally references
    """
    sequence: int
    requester: str
    capability: Capability
    target: str
    purpose: str
    plan_id: Optional[str] = None
    finding_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "requester": self.requester,
            "capability": self.capability.value,
            "target": self.target,
            "purpose": self.purpose,
            "plan_id": self.plan_id,
            "finding_id": self.finding_id,
        }


@dataclass(frozen=True)
class PolicyDecision:
    """Result of a Broker + Policy consultation."""
    sequence: int
    decision: Decision
    reason: str
    capability: Capability
    target: str
    # The evidence ledger slot this decision was recorded against. M3 will
    # enforce that PolicyDecision.evidence_id is non-null on every record.
    evidence_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "decision": self.decision.value,
            "reason": self.reason,
            "capability": self.capability.value,
            "target": self.target,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """Result of running an allowed action through Runtime.

    `evidence` is a payload the Runtime may attach for the EvidenceLedger
    writer. It must be JSON-serializable; the Runtime adapter is responsible
    for that contract.
    """
    sequence: int
    success: bool
    output: str
    error: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EvidenceReceipt:
    """A single append-only record in the EvidenceLedger.

    Frozen. M3 will write these to a JSONL ledger. Each receipt links back
    to the originating ActionRequest via `sequence`, and to the producing
    component via `producer`. The `payload` is opaque to the seam; only the
    Runtime / Broker / Verifier adapters know how to interpret it.
    """
    evidence_id: str
    sequence: int
    producer: str          # "broker" | "policy" | "runtime" | "verifier" | "falsifier" | "replanner" | "quality_gate"
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "sequence": self.sequence,
            "producer": self.producer,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class Finding:
    """A candidate or verified statement about the codebase.

    Lifecycle states are governed by `state`. Transitions are not enforced
    here; they are enforced at M4/M5 by the Verifier + Falsifier adapters.
    """
    finding_id: str
    state: FindingState
    summary: str
    target: str
    evidence_ids: List[str] = field(default_factory=list)
    supersedes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "state": self.state.value,
            "summary": self.summary,
            "target": self.target,
            "evidence_ids": list(self.evidence_ids),
            "supersedes": self.supersedes,
        }


@dataclass(frozen=True)
class FocusedContext:
    """Deliberately small context passed to the Replanner.

    Contains only:
        refuted_claim      - the Finding the replanner should address
        diagnostic_evidence - evidence receipts explaining why it was refuted
        mission_scope       - the mission description / scope boundary
    """
    refuted_claim: Finding
    diagnostic_evidence: List[EvidenceReceipt]
    mission_scope: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "refuted_claim": self.refuted_claim.to_dict(),
            "diagnostic_evidence": [e.to_dict() for e in self.diagnostic_evidence],
            "mission_scope": self.mission_scope,
        }


@dataclass(frozen=True)
class Plan:
    """A plan is a sequence of ActionRequests tied to a mission."""
    plan_id: str
    mission_id: str
    steps: List[ActionRequest]
    parent_plan_id: Optional[str] = None  # set when this plan was produced by a replanner

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "mission_id": self.mission_id,
            "steps": [s.to_dict() for s in self.steps],
            "parent_plan_id": self.parent_plan_id,
        }


@dataclass(frozen=True)
class Mission:
    """The top-level input to a run.

    `scope` is the BOB mission-scope description. M2 will hand it to the
    Policy. `criteria` are the success criteria that the Quality Gate will
    evaluate at M6.

    `problem` (M8) is a small structured payload the Planner inspects
    to derive the initial Plan A target/action. It is intentionally
    minimal: at most a handful of named keys (e.g. `symptom_target`,
    `actual_defect_target`). The Planner never inspects `description`
    for the target — `description` is human-readable only.
    """
    mission_id: str
    description: str
    scope: str
    criteria: List[str] = field(default_factory=list)
    problem: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "description": self.description,
            "scope": self.scope,
            "criteria": list(self.criteria),
            "problem": dict(self.problem),
        }


__all__ = [
    "Capability",
    "Decision",
    "FindingState",
    "GateVerdict",
    "Seq",
    "fresh_id",
    "ActionRequest",
    "PolicyDecision",
    "ExecutionResult",
    "EvidenceReceipt",
    "Finding",
    "FocusedContext",
    "Plan",
    "Mission",
]