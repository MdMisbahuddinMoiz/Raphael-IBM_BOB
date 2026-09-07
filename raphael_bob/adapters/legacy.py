"""raphael_bob.adapters.legacy — *index* of legacy Raphael modules selected
for migration behind the IBM BOB MVP seams.

This module contains no runtime logic. It is the seam's authoritative
documentation of:

    * which legacy modules will sit behind which seams
    * what action applies to each (REUSE / ADAPT / ISOLATE / REPLACE)
    * why the action was chosen
    * what behavior remains legacy (and therefore must NOT be claimed as
      migrated)
    * what behavior is still missing (i.e., must be built in M2..M6)

This file is the bridge from docs/migration/reuse-matrix.md to code. M2+
implementations add real adapters in sub-modules such as
`policy_legacy.py`, `broker_legacy.py`, etc.

M2 update:
    * Broker seam: raphael_bob/broker.py BOBBroker is now IMPLEMENTED.
    * Policy seam: raphael_bob/policy.py BOBPolicy is now IMPLEMENTED.
    * Runtime seam: raphael_bob/runtime.py BOBRuntime is now IMPLEMENTED.
    * Capabilities: raphael_bob/capabilities.py execute_capability is
      now IMPLEMENTED for READ/LIST/SEARCH/WRITE/RUN_TEST.
    * Legacy CapabilityBroker, ScopeParser, RateLimiter: ADAPT path
      documented but the actual rebound to BOB semantics is now done
      by writing fresh code rather than importing the legacy modules.

Status language:
    IMPLEMENTED         - selection documented here.
    PHYSICALLY VERIFIED - exercised by tests in tests/test_seam_*.py and
                          tests/test_m2_*.py.
    NOT IMPLEMENTED     - real adapter bodies, deferred to M2+.
    UNKNOWN             - insufficient evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Action verbs used in this index, mirroring docs/migration/reuse-matrix.md.
REUSE = "REUSE"
ADAPT = "ADAPT"
ISOLATE = "ISOLATE"
REPLACE = "REPLACE"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AdapterSpec:
    """Documentation of one legacy-module-to-seam mapping."""

    seam: str                # target seam name (e.g. "Broker", "Policy")
    legacy_module: str       # import path within this repo
    action: str              # REUSE | ADAPT | ISOLATE | REPLACE | UNKNOWN
    why: str                 # evidence-backed justification
    legacy_behavior_remaining: str
    missing_for_target: str
    m2_status: Optional[str] = None  # populated by M2 implementation notes

    def to_dict(self) -> dict:
        return {
            "seam": self.seam,
            "legacy_module": self.legacy_module,
            "action": self.action,
            "why": self.why,
            "legacy_behavior_remaining": self.legacy_behavior_remaining,
            "missing_for_target": self.missing_for_target,
            "m2_status": self.m2_status,
        }


# -----------------------------------------------------------------------------
# Broker
# -----------------------------------------------------------------------------

BROKER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Broker",
        legacy_module="src/orchestrator/brain/capability_broker.py",
        action=ADAPT,
        why=(
            "CapabilityBroker (line 266) is a single deny-by-default gate with "
            "5-dim auth (target/RoE/capability/rate/impact) and emits "
            "ActionReceipt. Semantic match for the BOB Broker seam. Lexical "
            "mismatch: policy grammar is offensive-RoE, must be rebound."
        ),
        legacy_behavior_remaining=(
            "Existing offensive-policy grammar (ActionType enum with EXPLOIT, "
            "LATERAL_MOVEMENT, etc.) MUST NOT be reachable from the BOB seam."
        ),
        missing_for_target=(
            "Pure broker mediation of the new BOB Capability enum "
            "(READ/LIST/SEARCH/WRITE/RUN_TEST); sequence-number assignment; "
            "EvidenceReceipt emission on every decision."
        ),
        m2_status=(
            "M2: IMPLEMENTED as raphael_bob.broker.BOBBroker. Rebuilt from "
            "the contract rather than wrapping the legacy module; the legacy "
            "offensive-RoE code path is ISOLATE."
        ),
    ),
    AdapterSpec(
        seam="Broker",
        legacy_module="src/orchestrator/hardening/action_receipt.py",
        action=ADAPT,
        why=(
            "ActionReceipt already carries provenance and a chain of "
            "create_proposal/authorize/deny/start_execution/complete_execution. "
            "Reuse as the receipt shape that the BOB Broker emits."
        ),
        legacy_behavior_remaining=(
            "Receipt state machine tied to offensive execution timeline; "
            "the BOB seam needs only the receipt dataclass."
        ),
        missing_for_target=(
            "Drop-in mapping from ActionReceipt -> EvidenceReceipt at the seam."
        ),
        m2_status=(
            "M2: NOT IMPLEMENTED. BOB seam emits its own EvidenceReceipt "
            "(raphael_bob.contracts.EvidenceReceipt) rather than wrapping "
            "the legacy ActionReceipt shape."
        ),
    ),
)


# -----------------------------------------------------------------------------
# Policy
# -----------------------------------------------------------------------------

POLICY_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Policy",
        legacy_module="src/orchestrator/brain/scope_parser.py",
        action=ADAPT,
        why=(
            "ScopeParser is fail-closed and compiles HackerOne JSON into "
            "ScopeRule entries. The fail-closed semantics map directly onto "
            "the BOB Policy seam. The grammar must be replaced with BOB "
            "mission-scope grammar."
        ),
        legacy_behavior_remaining=(
            "HackerOne JSON parser. ISOLATE from MVP at the parser boundary."
        ),
        missing_for_target=(
            "Parser for the BOB mission-scope description language."
        ),
        m2_status=(
            "M2: IMPLEMENTED as raphael_bob.policy.BOBPolicy. The fail-closed "
            "semantics are preserved; the grammar is BOB-native "
            "(mission-scope substring + capability-specific invariants)."
        ),
    ),
    AdapterSpec(
        seam="Policy",
        legacy_module="src/orchestrator/brain/rate_limiter.py",
        action=ADAPT,
        why=(
            "RateLimiterConfig provides per-target multiplier, minute/hour "
            "windows, and jitter. The mechanism is reusable; the target-type "
            "dictionary must be re-keyed."
        ),
        legacy_behavior_remaining=(
            "Default target multipliers are tuned for offensive recon."
        ),
        missing_for_target=(
            "MVP target-type dict (filesystem vs test-runner)."
        ),
        m2_status=(
            "M2: NOT IMPLEMENTED. The MVP does not require time-window "
            "rate limiting; revisit when mission scope is finalized."
        ),
    ),
)


# -----------------------------------------------------------------------------
# Evidence (no in-memory JSONL yet; only the Evidence dataclass is reusable)
# -----------------------------------------------------------------------------

EVIDENCE_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Evidence",
        legacy_module="src/orchestrator/brain/evidence.py",
        action=ADAPT,
        why=(
            "Evidence (line 55) is a frozen dataclass with TrustLevel and a "
            "derived_from/supports/contradicts DAG. Shape matches BOB "
            "EvidenceReceipt with one difference: BOB requires a single "
            "flat payload + producer tag, not a semantic-relation graph."
        ),
        legacy_behavior_remaining=(
            "Semantic-relation DAG is rich but the BOB MVP only needs the "
            "evidence_id/sequence/producer/payload surface."
        ),
        missing_for_target=(
            "JSONL append-only serialization; causal-sequence ordering."
        ),
        m2_status=(
            "M2: NOT IMPLEMENTED. BOB Broker keeps an in-memory audit list. "
            "M3 owns the JSONL writer."
        ),
    ),
    AdapterSpec(
        seam="Evidence",
        legacy_module="src/orchestrator/brain/trust.py",
        action=ISOLATE,
        why=(
            "TrustLevel enum classifies provenance (SYSTEM_POLICY, "
            "OPERATOR_INSTRUCTION, etc.). Useful but not part of the BOB "
            "MVP evidence surface; defer."
        ),
        legacy_behavior_remaining=(
            "Trust taxonomy remains reachable in legacy code only."
        ),
        missing_for_target=(
            "BOB MVP uses a 'producer' string tag, not the full trust enum."
        ),
        m2_status="M2: ISOLATE remains correct.",
    ),
)


# -----------------------------------------------------------------------------
# Falsifier (ContradictionManager is the closest analogue)
# -----------------------------------------------------------------------------

FALSIFIER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Falsifier",
        legacy_module="src/orchestrator/brain/contradiction.py",
        action=ADAPT,
        why=(
            "ContradictionManager (line 134) implements "
            "DETECTED -> UNDER_INVESTIGATION -> RESOLVED_TRUE/FALSE lifecycle "
            "with discriminating-observation proposals. Matches the brief's "
            "active-challenge pattern for the Falsifier seam."
        ),
        legacy_behavior_remaining=(
            "Built for offensive contradictions. Discriminator execution "
            "currently bypasses the new BOB Runtime; must be rewired at M4."
        ),
        missing_for_target=(
            "Output: a Finding whose state is REFUTED when the challenge "
            "finds a counter-example. Adapter at M4."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M4.",
    ),
)


# -----------------------------------------------------------------------------
# Verifier (VerificationLoop)
# -----------------------------------------------------------------------------

VERIFIER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Verifier",
        legacy_module="src/raphael/verifier/core.py",
        action=ADAPT,
        why=(
            "VerificationLoop (line 33) has a preflight/observe/adapt "
            "lifecycle for *exploit canary* verification (TCP/HTTP/DNS "
            "callbacks). Lifecycle shape is reusable; semantics are wrong "
            "for the BOB MVP (which needs behavioral retest of source-code "
            "fixes, not exploit canary callbacks)."
        ),
        legacy_behavior_remaining=(
            "Canary channels and TCP/HTTP/DNS callback adapters."
        ),
        missing_for_target=(
            "Broker-mediated behavioral retest of a Finding."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M4.",
    ),
)


# -----------------------------------------------------------------------------
# Planner (cognitive-loop Action/Precondition model)
# -----------------------------------------------------------------------------

PLANNER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Planner",
        legacy_module="src/orchestrator/brain/action.py",
        action=ADAPT,
        why=(
            "Action / Precondition / Effect model (line 149) is general-purpose. "
            "Factory functions at lines 280..441 are offensive-specific and "
            "must NOT be reachable from the BOB Planner seam."
        ),
        legacy_behavior_remaining=(
            "Offensive factories (create_nmap_scan_action, "
            "create_exploit_action, create_lateral_movement_action)."
        ),
        missing_for_target=(
            "Planner search that emits ActionRequest lists in "
            "Capability/LIST/READ/SEARCH/WRITE/RUN_TEST space."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M5.",
    ),
    AdapterSpec(
        seam="Planner",
        legacy_module="src/orchestrator/brain/world.py",
        action=ADAPT,
        why=(
            "WorldModel + Entity + Relationship provide a generic typed "
            "graph that is reusable. Entity vocabulary must be reduced."
        ),
        legacy_behavior_remaining=(
            "Offensive entity types (Asset, Service, Credential, CloudResource, "
            "Container, Cluster, etc.)."
        ),
        missing_for_target=(
            "Reduced entity vocabulary: file, function, test, "
            "capability-request."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M5.",
    ),
    AdapterSpec(
        seam="Planner",
        legacy_module="src/raphael/cognitive/planner.py",
        action=REPLACE,
        why=(
            "GreedyPlanner (line 69) selects next step by UCB1 utility. "
            "The BOB Planner seam is plan-generation, not step-selection. "
            "Replace with evidence-aware planning at M5."
        ),
        legacy_behavior_remaining=(
            "UCB1 step selection."
        ),
        missing_for_target=(
            "Plan-A generation from Mission + EvidenceLedger."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M5.",
    ),
)


# -----------------------------------------------------------------------------
# Replanner — no direct analogue; declare explicitly
# -----------------------------------------------------------------------------

REPLANNER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Replanner",
        legacy_module="(none)",
        action=REPLACE,
        why=(
            "No on-target Replanner exists. The closest analogues are "
            "src/orchestrator/brain/strategy.py and "
            "src/orchestrator/brain/strategy_learner.py (heuristic). "
            "Replanner must be evidence-causal (Plan A -> refutation -> "
            "FocusedContext -> Plan B)."
        ),
        legacy_behavior_remaining=(
            "None. Heuristic strategy learner must not be invoked by the "
            "BOB seam."
        ),
        missing_for_target=(
            "Replanner implementation in M5 that consumes FocusedContext "
            "and emits a Plan with parent_plan_id set."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M5.",
    ),
)


# -----------------------------------------------------------------------------
# QualityGate — no analogue
# -----------------------------------------------------------------------------

QUALITYGATE_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="QualityGate",
        legacy_module="(none)",
        action=REPLACE,
        why=(
            "No module bears the COMPLETE-authority responsibility. "
            "src/arena/conclusion.py evaluates RBS arena runs; not a "
            "mission-level gate."
        ),
        legacy_behavior_remaining=(
            "None."
        ),
        missing_for_target=(
            "QualityGate implementation in M6 with the four-input signature: "
            "mission, findings, evidence, behavior_probe_ok, regression_ok."
        ),
        m2_status="M2: NOT IMPLEMENTED. Reserved for M6.",
    ),
)


# -----------------------------------------------------------------------------
# Runtime — no direct analogue
# -----------------------------------------------------------------------------

RUNTIME_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Runtime",
        legacy_module="(none)",
        action=REPLACE,
        why=(
            "InteractiveShellCapability (line 58 of "
            "src/orchestrator/capabilities/interactive_shell/capability.py) "
            "is an abstract base for shell capabilities, not an "
            "agent-facing broker-mediated Runtime. Executor "
            "(src/raphael/executor/executor.py) bypasses the Broker and "
            "calls KaliBridge/subprocess directly."
        ),
        legacy_behavior_remaining=(
            "Shell capability machinery, KaliBridge, Executor."
        ),
        missing_for_target=(
            "Runtime implementation in M2 that dispatches to Capability "
            "adapters and emits ExecutionResult + EvidenceReceipt."
        ),
        m2_status=(
            "M2: IMPLEMENTED as raphael_bob.runtime.BOBRuntime. Submits "
            "ActionRequests through BOBBroker; rejects non-BOBBroker "
            "wrappers structurally."
        ),
    ),
)


# -----------------------------------------------------------------------------
# Runner — no direct analogue
# -----------------------------------------------------------------------------

RUNNER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        seam="Runner",
        legacy_module="src/raphael/main.py",
        action=ISOLATE,
        why=(
            "src/raphael/main.py drives the existing offensive cognitive "
            "loop. It MUST NOT be invoked from the BOB seam."
        ),
        legacy_behavior_remaining=(
            "Wave 1 cognitive loop entry point."
        ),
        missing_for_target=(
            "Runner implementation in M6 that drives the BOB control loop."
        ),
        m2_status="M2: ISOLATE remains correct. Reserved for M6.",
    ),
)


# -----------------------------------------------------------------------------
# Index of all specs, grouped by seam
# -----------------------------------------------------------------------------

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
    """Return a {action: count} dict across all specs."""
    counts: dict[str, int] = {}
    for spec in [s for specs in ALL_SPECS.values() for s in specs]:
        counts[spec.action] = counts.get(spec.action, 0) + 1
    return counts


def specs_for(seam: str) -> tuple[AdapterSpec, ...]:
    """Return the legacy-module specs selected for a given seam."""
    return ALL_SPECS.get(seam, ())


__all__ = [
    "AdapterSpec",
    "REUSE",
    "ADAPT",
    "ISOLATE",
    "REPLACE",
    "UNKNOWN",
    "BROKER_SPECS",
    "POLICY_SPECS",
    "EVIDENCE_SPECS",
    "FALSIFIER_SPECS",
    "VERIFIER_SPECS",
    "PLANNER_SPECS",
    "REPLANNER_SPECS",
    "QUALITYGATE_SPECS",
    "RUNTIME_SPECS",
    "RUNNER_SPECS",
    "ALL_SPECS",
    "action_counts",
    "specs_for",
]