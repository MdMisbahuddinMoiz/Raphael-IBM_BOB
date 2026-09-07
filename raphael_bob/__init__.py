"""raphael_bob — IBM BOB Hackathon MVP seam package (M1..M2).

This package establishes the migration boundary between the existing
Raphael v2.1.1 implementation and the IBM BOB MVP target.

Modules:
    contracts         - dataclasses / enums that cross every seam boundary.
    seams             - Protocol interfaces for Runtime, Broker, Policy,
                        EvidenceLedger, Verifier, Falsifier, Replanner,
                        QualityGate, Planner, Runner.
    workspace         - isolated workspace root, realpath containment.
    policy            - BOB Policy implementation (M2): fail-closed,
                        mission-scope, capability-specific invariants.
    capabilities      - READ/LIST/SEARCH/WRITE/RUN_TEST implementations (M2).
    broker            - BOB Broker implementation (M2): mandatory mediation,
                        sequence numbering, audit log.
    runtime           - BOB Runtime implementation (M2): agent-facing
                        boundary that submits through the Broker only.
    adapters          - explicit adapters to legacy Raphael machinery (M2+).

Legacy status language used throughout this package:

    IMPLEMENTED         - dataclass / enum / Protocol / class defined.
    PHYSICALLY VERIFIED - exercised by tests in tests/test_seam_*.py and
                          tests/test_m2_*.py.
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
from raphael_bob.workspace import Workspace
from raphael_bob.policy import BOBPolicy
from raphael_bob.broker import BOBBroker, BrokerResult
from raphael_bob.runtime import BOBRuntime, RuntimeResult
from raphael_bob.capabilities import execute_capability

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
    # M2 implementations
    "Workspace",
    "BOBPolicy",
    "BOBBroker",
    "BrokerResult",
    "BOBRuntime",
    "RuntimeResult",
    "execute_capability",
]