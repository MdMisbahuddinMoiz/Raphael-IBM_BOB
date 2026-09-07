"""raphael_bob — IBM BOB Hackathon MVP seam package (M1..M5).

This package establishes the migration boundary between the existing
Raphael v2.1.1 implementation and the IBM BOB MVP target.

Modules:
    contracts         - dataclasses / enums that cross every seam boundary.
    seams             - Protocol interfaces for Runtime, Broker, Policy,
                        EvidenceLedger, Verifier, Falsifier, Replanner,
                        QualityGate, Planner, Runner.
    workspace         - isolated workspace root, realpath containment.
    policy            - BOB Policy implementation (M2): fail-closed.
    capabilities      - READ/LIST/SEARCH/WRITE/RUN_TEST implementations (M2).
    broker            - BOB Broker implementation (M2..M3).
    runtime           - BOB Runtime implementation (M2..M3).
    evidence_ledger   - M3 append-only JSONL evidence ledger.
    finding           - M4 lifecycle-aware Finding store.
    verifier          - M4 broker-mediated retest engine.
    falsifier         - M4 broker-mediated active-challenge engine.
    replanner         - M5 evidence-driven Plan B generator.
    runner            - M5 control-loop orchestrator (REFUSE only).
    adapters          - explicit adapters to legacy Raphael machinery.

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
from raphael_bob.evidence_ledger import (
    ArtifactSink,
    DecisionRecord,
    EvidenceLedger as _JSONL_EvidenceLedger,
    EvidenceRecord,
    FindingRecord,
    LedgerReader,
    LedgerWriter,
    RecordKind,
    RequestRecord,
    ResultRecord,
    digest_id,
)
from raphael_bob.finding import (
    FindingStore,
    InvalidTransitionError,
    TransitionResult,
)
from raphael_bob.verifier import RetestSpec, VerifyOutcome, Verifier
from raphael_bob.falsifier import (
    ChallengeOutcome,
    ChallengeSpec,
    Falsifier,
)
from raphael_bob.replanner import ReplanStrategy, Replanner, derive_plan_b_id
from raphael_bob.runner import PlannerStub, Runner, RunnerOutcome
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
    # M3 implementations
    "ArtifactSink",
    "DecisionRecord",
    "EvidenceRecord",
    "FindingRecord",
    "LedgerReader",
    "LedgerWriter",
    "RecordKind",
    "RequestRecord",
    "ResultRecord",
    "digest_id",
    # M4 implementations
    "FindingStore",
    "InvalidTransitionError",
    "TransitionResult",
    "Verifier",
    "RetestSpec",
    "VerifyOutcome",
    "Falsifier",
    "ChallengeSpec",
    "ChallengeOutcome",
    # M5 implementations
    "ReplanStrategy",
    "Replanner",
    "derive_plan_b_id",
    "Runner",
    "PlannerStub",
    "RunnerOutcome",
]