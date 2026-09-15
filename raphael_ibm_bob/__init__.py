"""raphael_ibm_bob — IBM BOB Hackathon MVP seam package (M1..M5).

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

from raphael_ibm_bob.contracts import (
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
from raphael_ibm_bob.seams import (
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
from raphael_ibm_bob.workspace import Workspace
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.broker import BOBBroker, BrokerResult
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult
from raphael_ibm_bob.capabilities import execute_capability
from raphael_ibm_bob.evidence_ledger import (
    ArtifactSink,
    DecisionRecord,
    EvidenceLedger as _JSONL_EvidenceLedger,
    EvidenceRecord,
    FindingRecord,
    GateRecord,
    LedgerReader,
    LedgerWriter,
    RecordKind,
    RequestRecord,
    ResultRecord,
    create_run_dir,
    generate_run_id,
    append_run_provenance,
)
from raphael_ibm_bob.finding import (
    FindingStore,
    InvalidTransitionError,
    TransitionResult,
)
from raphael_ibm_bob.verifier import RetestSpec, VerifyOutcome, Verifier
from raphael_ibm_bob.falsifier import (
    ChallengeOutcome,
    ChallengeSpec,
    Falsifier,
)
from raphael_ibm_bob.replanner import ReplanStrategy, Replanner, derive_plan_b_id
from raphael_ibm_bob.runner import Runner, RunnerOutcome
from raphael_ibm_bob.planner import Planner, derive_plan_a_id
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateEvaluation, GateInputs

__all__ = [
    "Runner",
    "RunnerOutcome",
    "Planner",
    "derive_plan_a_id",
]