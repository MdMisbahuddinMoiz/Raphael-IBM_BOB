"""raphael_ibm_bob.replanner — M5 evidence-driven Replanner.

The Replanner's job is to produce a `Plan B` whose causal ancestry is the
REFUTED finding from the prior plan. It MUST NOT be invoked speculatively;
the trigger is a real, evidence-backed REFUTED finding.

`replan(focused_context, parent_plan)` produces a `Plan` such that:

    Plan B.parent_plan_id == parent_plan.plan_id
    Plan B.steps[i].requester == "replanner"
    Plan B.steps[i].finding_id == refuted_finding.finding_id
    Plan B.steps[i].purpose  contains the causal pointer

The Replanner derives the new target from the refuted finding's evidence
chain. It does NOT repeat the prior plan's wrong target unless the
refutation evidence explicitly identifies the same target.

Legacy references (ADAPT, NOT imported):
    src/orchestrator/brain/action.py:149 Action / Precondition / Effect
        - general-purpose model; BOB rebuilder uses it conceptually.
    src/orchestrator/brain/world.py WorldModel
        - entity vocabulary reduced at M5 to (file, finding, plan, scope).
    src/orchestrator/brain/strategy.py / strategy_learner.py
        - heuristic; NOT used. The Replanner is evidence-driven, not
          utility-driven.
    src/raphael/cognitive/planner.py GreedyPlanner
        - UCB step selector; REPLACED by this module.

Determinism:
    Same (mission_scope, refuted_finding, parent_plan) produces the same
    Plan B. The Replanner does NOT use wall-clock time, random seeds, or
    in-memory mutable state across calls.

Limitations at M5:
    - The target-derivation strategy is intentionally simple: it locates
      the counter-example evidence (kind=counter-example) and uses its
      detail to choose a target. M7 will harden this against the authkit
      scenario.
    - The Replanner emits exactly ONE action step per call. M7 may extend
      it for multi-step replans.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

from raphael_ibm_bob.capability_fabric import (
    CapabilityFabric,
    default_fabric,
)
from raphael_ibm_bob.contracts import (
    Capability,
    FocusedContext,
    Mission,
    Plan,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def derive_plan_b_id(parent_plan: Plan, refuted_finding_id: str) -> str:
    """Deterministic Plan B identifier from parent + refuted finding id."""
    h = hashlib.sha256(_canonical({
        "parent_plan_id": parent_plan.plan_id,
        "refuted_finding_id": refuted_finding_id,
    }).encode("utf-8")).hexdigest()
    return f"P-{h[:12]}"


@dataclass(frozen=True)
class ReplanStrategy:
    """How to choose the new action's target from the FocusedContext.

    `preferred_target`: if provided, the Replanner targets this path.
                       Used by tests to assert "Plan B targets the
                       evidence-identified defect, not the wrong target."
    `capability`:        capability to invoke in the Plan B step.
    """
    preferred_target: Optional[str] = None
    capability: Capability = Capability.READ


class Replanner:
    """Evidence-driven Plan B generator."""

    def __init__(
        self,
        store: FindingStore,
        ledger: EvidenceLedger,
        strategy: Optional[ReplanStrategy] = None,
        fabric: Optional[CapabilityFabric] = None,
    ):
        self._store = store
        self._ledger = ledger
        self._strategy = strategy or ReplanStrategy()
        # M16.3: capability resolution for the Plan B step goes through the
        # Capability Fabric. None builds a fresh default_fabric().
        self._fabric = fabric if fabric is not None else default_fabric()

    @property
    def store(self) -> FindingStore:
        return self._store

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def replan(
        self,
        focused_context: FocusedContext,
        parent_plan: Plan,
    ) -> Plan:
        """Produce Plan B from the focused context + parent plan.

        Validates:
          - the refuted claim's state is REFUTED;
          - the diagnostic evidence is non-empty.

        Persists a `producer="replanner"` evidence record whose payload
        carries the parent -> child linkage and the evidence_seqs that
        motivated the replan.
        """
        refuted = focused_context.refuted_claim
        if refuted.state.value != "refuted":
            raise ValueError(
                f"replan requires REFUTED finding, got {refuted.state.value}"
            )
        if not focused_context.diagnostic_evidence:
            raise ValueError("replan requires non-empty diagnostic_evidence")

        target = self._derive_target(focused_context)
        if target is None:
            target = parent_plan.steps[0].target if parent_plan.steps else "src/"

        purpose = (
            f"replan-after-refutation:{refuted.finding_id}:"
            f"counter-target={target}"
        )
        plan_b_id = derive_plan_b_id(parent_plan, refuted.finding_id)
        # M16.3: capability -> Capability Fabric -> Native Provider ->
        # ActionRequest (no direct construction; no execution authority).
        provider = self._fabric.resolve(self._strategy.capability)
        step = provider.build_action_request(
            self._strategy.capability,
            target,
            purpose=purpose,
            requester="replanner",
            plan_id=plan_b_id,
            finding_id=refuted.finding_id,
        )

        plan_b = Plan(
            plan_id=plan_b_id,
            mission_id=parent_plan.mission_id,
            steps=[step],
            parent_plan_id=parent_plan.plan_id,
        )

        evidence_seqs = tuple(
            int(ev.sequence) for ev in focused_context.diagnostic_evidence
            if isinstance(ev.sequence, int)
        )
        payload = {
            "parent_plan_id": parent_plan.plan_id,
            "plan_b_id": plan_b.plan_id,
            "refuted_finding_id": refuted.finding_id,
            "new_target": target,
            "new_step_purpose": step.purpose,
            "mission_scope": focused_context.mission_scope,
            "evidence_seqs": list(evidence_seqs),
        }
        ev_id = digest_id(payload, prefix="R")
        self._ledger.append_evidence(
            evidence_id=ev_id,
            producer="replanner",
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            payload=payload,
            finding_id=refuted.finding_id,
        )

        return plan_b

    def _derive_target(self, focused_context: FocusedContext) -> Optional[str]:
        """Choose the new target.

        Priority:
          1. ReplanStrategy.preferred_target (explicit override).
          2. The first counter-example-kind evidence's nested payload
             "new_target" or "target" field (the actual refuted defect).
          3. The first evidence with a "new_target" or "target" field.
          4. None (caller falls back to parent_plan.steps[0].target).
        """
        if self._strategy.preferred_target:
            return self._strategy.preferred_target
        # Pass 1: prefer counter-example evidence.
        for ev in focused_context.diagnostic_evidence:
            inner = (ev.payload or {}).get("payload") or {}
            if inner.get("kind") == "counter-example":
                if "new_target" in inner:
                    return str(inner["new_target"])
                if "target" in inner:
                    return str(inner["target"])
        # Pass 2: fall back to the first evidence with a target.
        for ev in focused_context.diagnostic_evidence:
            inner = (ev.payload or {}).get("payload") or {}
            if "new_target" in inner:
                return str(inner["new_target"])
            if "target" in inner:
                return str(inner["target"])
        return None

__all__ = ["Replanner", "ReplanStrategy", "derive_plan_b_id"]