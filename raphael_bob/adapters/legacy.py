"""raphael_bob.adapters.legacy — index of legacy Raphael modules selected
for migration behind the IBM BOB MVP seams.

This module contains no runtime logic. It is the seam's authoritative
documentation of legacy-module dispositions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


REUSE = "REUSE"
ADAPT = "ADAPT"
ISOLATE = "ISOLATE"
REPLACE = "REPLACE"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AdapterSpec:
    seam: str
    legacy_module: str
    action: str
    why: str
    legacy_behavior_remaining: str
    missing_for_target: str
    m2_status: Optional[str] = None
    m3_status: Optional[str] = None
    m4_status: Optional[str] = None
    m5_status: Optional[str] = None
    m6_status: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "seam": self.seam,
            "legacy_module": self.legacy_module,
            "action": self.action,
            "why": self.why,
            "legacy_behavior_remaining": self.legacy_behavior_remaining,
            "missing_for_target": self.missing_for_target,
            "m2_status": self.m2_status,
            "m3_status": self.m3_status,
            "m4_status": self.m4_status,
            "m5_status": self.m5_status,
            "m6_status": self.m6_status,
        }


# --- specs --------------------------------------------------------------------

BROKER_SPECS = (
    AdapterSpec(
        seam="Broker", legacy_module="src/orchestrator/brain/capability_broker.py",
        action=ADAPT,
        why="5-dim deny-by-default authorization; semantic match for BOB Broker.",
        legacy_behavior_remaining="Offensive ActionType grammar (EXPLOIT, ...).",
        missing_for_target="Reuse shape; rebuild with BOB Capability enum.",
        m6_status="M6: BOBBroker unchanged from M3; QualityGate reads its ledger writes.",
    ),
    AdapterSpec(
        seam="Broker", legacy_module="src/orchestrator/hardening/action_receipt.py",
        action=ADAPT,
        why="ActionReceipt shape with provenance chain.",
        legacy_behavior_remaining="Receipt state machine tied to offensive execution.",
        missing_for_target="Drop-in mapping ActionReceipt -> EvidenceReceipt.",
        m6_status="M6: NOT IMPLEMENTED. JSONL EvidenceRecord is authoritative.",
    ),
)

POLICY_SPECS = (
    AdapterSpec(
        seam="Policy", legacy_module="src/orchestrator/brain/scope_parser.py",
        action=ADAPT,
        why="Fail-closed scope compilation; semantic match for BOB Policy.",
        legacy_behavior_remaining="HackerOne JSON parser.",
        missing_for_target="Replace parser grammar with BOB mission-scope language.",
        m6_status="M6: BOBPolicy unchanged from M2.",
    ),
    AdapterSpec(
        seam="Policy", legacy_module="src/orchestrator/brain/rate_limiter.py",
        action=ADAPT,
        why="Per-target multiplier + windowed rate limit.",
        legacy_behavior_remaining="Offensive-tuned target multipliers.",
        missing_for_target="Re-key target-type dict.",
        m6_status="M6: NOT IMPLEMENTED.",
    ),
)

EVIDENCE_SPECS = (
    AdapterSpec(
        seam="Evidence", legacy_module="src/orchestrator/brain/evidence.py",
        action=ADAPT,
        why="Frozen dataclass + SHA-256 digest pattern is reusable.",
        legacy_behavior_remaining="In-memory EvidenceGraph with semantic-relation DAG.",
        missing_for_target="JSONL append-only + flat causal links (now M3 + M4 + M6).",
        m6_status=(
            "M6: EvidenceLedger now also persists GateRecord (kind='gate') for "
            "QualityGate decisions. Records the final COMPLETE/REFUSE, checks, "
            "evidence_refs, finding_refs, reasons."
        ),
    ),
    AdapterSpec(
        seam="Evidence", legacy_module="src/orchestrator/brain/trust.py",
        action=ISOLATE,
        why="TrustLevel enum not part of BOB MVP evidence surface.",
        legacy_behavior_remaining="Trust taxonomy reachable in legacy only.",
        missing_for_target="BOB uses 'producer' string tag (policy/execution/verifier/falsifier/replanner/probe/regression).",
        m6_status="M6: ISOLATE remains correct. New producers: 'probe', 'regression'.",
    ),
)

FALSIFIER_SPECS = (
    AdapterSpec(
        seam="Falsifier", legacy_module="src/orchestrator/brain/contradiction.py",
        action=ADAPT,
        why="Active-challenge lifecycle pattern (DETECTED -> RESOLVED).",
        legacy_behavior_remaining="Offensive contradictions; discriminator bypasses Broker.",
        missing_for_target="Counter-example observed through Broker, persisted as EvidenceRecord.",
        m6_status="M6: Falsifier unchanged from M5; counter-example payload now feeds Replanner.",
    ),
)

VERIFIER_SPECS = (
    AdapterSpec(
        seam="Verifier", legacy_module="src/raphael/verifier/core.py",
        action=ADAPT,
        why="preflight/observe/adapt lifecycle pattern (exploit canary).",
        legacy_behavior_remaining="Canary channels and TCP/HTTP/DNS callback adapters.",
        missing_for_target="Broker-mediated behavioral retest, not exploit canary.",
        m6_status="M6: Verifier unchanged from M5.",
    ),
)

PLANNER_SPECS = (
    AdapterSpec(
        seam="Planner", legacy_module="src/orchestrator/brain/action.py",
        action=ADAPT,
        why="General-purpose Action / Precondition / Effect model.",
        legacy_behavior_remaining="Offensive factory functions.",
        missing_for_target="M7: real Planner in BOB Capability space.",
        m6_status="M6: PlannerStub still a stub. Reserved for M7.",
    ),
    AdapterSpec(
        seam="Planner", legacy_module="src/orchestrator/brain/world.py",
        action=ADAPT,
        why="Typed entity graph; general-purpose shape.",
        legacy_behavior_remaining="Offensive entity vocabulary.",
        missing_for_target="Reduced vocabulary (file, finding, plan, scope).",
        m6_status="M6: NOT IMPLEMENTED.",
    ),
    AdapterSpec(
        seam="Planner", legacy_module="src/raphael/cognitive/planner.py",
        action=REPLACE,
        why="UCB step selector is utility-driven, not evidence-driven.",
        legacy_behavior_remaining="UCB step selection.",
        missing_for_target="Plan-A generation from Mission + EvidenceLedger.",
        m6_status="M6: NOT IMPLEMENTED. Reserved for M7.",
    ),
)

REPLANNER_SPECS = (
    AdapterSpec(
        seam="Replanner", legacy_module="(none)",
        action=REPLACE,
        why="No on-target Replanner exists. Closest analogues are heuristic.",
        legacy_behavior_remaining="None.",
        missing_for_target="Evidence-causal Plan B generator.",
        m6_status=(
            "M6: Replanner unchanged from M5. Plan B is submitted through the "
            "Broker by the Runner; the Gate's condition G requires a replan "
            "evidence record for every REFUTED finding."
        ),
    ),
)

QUALITYGATE_SPECS = (
    AdapterSpec(
        seam="QualityGate", legacy_module="(none)",
        action=REPLACE,
        why="No on-target QualityGate exists.",
        legacy_behavior_remaining="None.",
        missing_for_target="Sole COMPLETE authority with 7 conditions.",
        m6_status=(
            "M6: IMPLEMENTED as raphael_bob.quality_gate.BOBQualityGate. "
            "7 conditions (A-G) checked against the durable ledger. "
            "Persists a GateRecord (kind='gate') with the final decision, "
            "checks, evidence_refs, finding_refs, and reasons. "
            "Only the QualityGate may return GateVerdict.COMPLETE."
        ),
    ),
)

RUNTIME_SPECS = (
    AdapterSpec(
        seam="Runtime", legacy_module="(none)",
        action=REPLACE,
        why="No on-target broker-mediated Runtime exists.",
        legacy_behavior_remaining="Shell capability machinery (ISOLATE).",
        missing_for_target="Agent-facing boundary; submits via Broker.",
        m6_status="M6: BOBRuntime unchanged from M5.",
    ),
)

RUNNER_SPECS = (
    AdapterSpec(
        seam="Runner", legacy_module="src/raphael/main.py",
        action=ISOLATE,
        why="Wave1 cognitive loop is the legacy entry point.",
        legacy_behavior_remaining="Wave1 cognitive loop entry point.",
        missing_for_target="M5/M6 control-loop orchestrator.",
        m6_status=(
            "M6: Runner is raphael_bob.runner.Runner (M5 + M6). It drives "
            "Plan A -> Verifier -> Falsifier -> Replanner -> Plan B and "
            "delegates COMPLETE to BOBQualityGate. Never returns COMPLETE."
        ),
    ),
)

ALL_SPECS: dict[str, tuple[AdapterSpec, ...]] = {
    "Broker": BROKER_SPECS,
    "Policy": POLICY_SPECS,
    "Evidence": EVIDENCE_SPECS,
    "Falsifier": FALSIFIER_SPECS,
    "Verifier": VERIFIER_SPECS,
    "Planner": PLANNER_SPECS,
    "Replanner": REPLANNER_SPECS,
    "QualityGate": QUALITYGATE_SPECS,
    "Runtime": RUNTIME_SPECS,
    "Runner": RUNNER_SPECS,
}


def action_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in [s for specs in ALL_SPECS.values() for s in specs]:
        counts[spec.action] = counts.get(spec.action, 0) + 1
    return counts


def specs_for(seam: str) -> tuple[AdapterSpec, ...]:
    return ALL_SPECS.get(seam, ())


__all__ = [
    "AdapterSpec", "REUSE", "ADAPT", "ISOLATE", "REPLACE", "UNKNOWN",
    "BROKER_SPECS", "POLICY_SPECS", "EVIDENCE_SPECS", "FALSIFIER_SPECS",
    "VERIFIER_SPECS", "PLANNER_SPECS", "REPLANNER_SPECS",
    "QUALITYGATE_SPECS", "RUNTIME_SPECS", "RUNNER_SPECS", "ALL_SPECS",
    "action_counts", "specs_for",
]