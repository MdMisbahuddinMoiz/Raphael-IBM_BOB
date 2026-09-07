"""raphael_bob — IBM BOB Hackathon MVP seam package (M1).

This package establishes the migration boundary between the existing
Raphael v2.1.1 implementation and the IBM BOB MVP target. It is *not* an
implementation of the target control loop; that begins at M2.

Modules:
    contracts  - dataclasses / enums that cross every seam boundary.
    seams      - Protocol interfaces for Runtime, Broker, Policy,
                 EvidenceLedger, Verifier, Falsifier, Replanner,
                 QualityGate, Planner, Runner.
    adapters   - explicit adapters to legacy Raphael machinery (M2+).

Legacy status language used throughout this package:

    IMPLEMENTED         - dataclass/enum/protocol defined and importable.
    PHYSICALLY VERIFIED - exercised by tests in tests/test_seam_*.py.
    NOT IMPLEMENTED     - the substantive implementation; deferred.
    UNKNOWN             - no evidence yet.
"""
from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    EvidenceReceipt,
    ExecutionResult,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    PolicyDecision,
    Seq,
    fresh_id,
)
from raphael_bob.seams import (
    Broker,
    EvidenceLedger,
    Falsifier,
    Planner,
    Policy,
    QualityGate,
    Replanner,
    Runner,
    Runtime,
    Verifier,
)

__all__ = [
    # contracts
    "ActionRequest",
    "Capability",
    "Decision",
    "EvidenceReceipt",
    "ExecutionResult",
    "Finding",
    "FindingState",
    "FocusedContext",
    "GateVerdict",
    "Mission",
    "Plan",
    "PolicyDecision",
    "Seq",
    "fresh_id",
    # seams
    "Broker",
    "EvidenceLedger",
    "Falsifier",
    "Planner",
    "Policy",
    "QualityGate",
    "Replanner",
    "Runner",
    "Runtime",
    "Verifier",
]