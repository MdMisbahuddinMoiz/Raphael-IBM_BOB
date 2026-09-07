"""raphael_bob.runner — M5 minimal Runner.

The Runner drives the BOB control loop:

    Mission
       ↓
    Planner (M5 stub: produces Plan A)
       ↓
    Plan A
       ↓
    Runner.execute_plan(plan_a)  # actions go through Runtime -> Broker -> Policy
       ↓
    candidate Finding registered with FindingStore
       ↓
    Verifier.verify(finding, retest, mission) -> VERIFIED
       ↓
    Falsifier.challenge(finding, spec, mission) -> REFUTED
       ↓
    FocusedContext built from FindingStore.evidence_for(finding_id)
       ↓
    Replanner.replan(focused_context, plan_a) -> Plan B
       ↓
    Verifier.verify again (Plan B's action goes through the broker)
       ↓
    return REFUSE    #   NEVER COMPLETE

The Runner MUST NOT declare COMPLETE. That remains M6's QualityGate.

The Planner is a stub at M5: it emits a single ActionRequest that points
at a candidate target (default: the finding's target). M7 will harden
this with a proper authkit-style planner.

Legacy references:
    src/raphael/main.py — Wave 1 cognitive loop. ISOLATE; not invoked.
    src/orchestrator/brain/action.py Action/Precondition/Effect —
        ADAPT conceptually; the M5 Planner stub uses the same shape
        but emits BOB-native READ/LIST/SEARCH/WRITE/RUN_TEST actions.

Limitations at M5:
    - Planner is a stub; M7 will replace it.
    - Single-step replan only.
    - No scheduler; synchronous.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from raphael_bob.broker import BOBBroker
from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
)
from raphael_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_bob.falsifier import ChallengeSpec, Falsifier
from raphael_bob.finding import FindingStore
from raphael_bob.policy import BOBPolicy
from raphael_bob.replanner import Replanner, ReplanStrategy, derive_plan_b_id
from raphael_bob.runtime import BOBRuntime
from raphael_bob.verifier import RetestSpec, Verifier


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class PlannerStub:
    """M5 stub planner. Produces a single-step Plan A targeting
    `initial_target`. M7 replaces this with a real Planner.

    Uses Capability.LIST against a directory because the BOB Policy
    requires READ targets to be regular files and WRITE/RUN_TEST targets
    to be files of a specific kind. A directory target is the safest
    default for a placeholder plan.
    """

    initial_target: str = "src/"

    def plan_a(self, mission: Mission) -> Plan:
        h = hashlib.sha256(_canonical({
            "mission_id": mission.mission_id,
            "stage": "plan-a",
        }).encode("utf-8")).hexdigest()
        plan_a_id = f"P-{h[:12]}"
        step = ActionRequest(
            sequence=0,
            requester="planner",
            capability=Capability.LIST,
            target=self.initial_target,
            purpose="plan-a:candidate-discovery",
            plan_id=plan_a_id,
            finding_id=None,
        )
        return Plan(
            plan_id=plan_a_id,
            mission_id=mission.mission_id,
            steps=[step],
            parent_plan_id=None,
        )


@dataclass(frozen=True)
class RunnerOutcome:
    """Public result of a Runner.run() call. The Runner NEVER returns
    COMPLETE; that is the Quality Gate's authority at M6."""
    gate_verdict: GateVerdict
    plan_a: Plan
    plan_b: Optional[Plan]
    finding: Finding
    mission: Mission
    # Replan evidence ids produced by the runner.
    plan_a_step_runtime_seq: int
    plan_b_step_runtime_seq: Optional[int]


class Runner:
    """Drives the BOB control loop without deciding final COMPLETE."""

    def __init__(
        self,
        runtime: BOBRuntime,
        ledger: EvidenceLedger,
        store: FindingStore,
        verifier: Verifier,
        falsifier: Falsifier,
        replanner: Replanner,
        planner: Optional[PlannerStub] = None,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._verifier = verifier
        self._falsifier = falsifier
        self._replanner = replanner
        self._planner = planner or PlannerStub()
        self._lock = threading.Lock()

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    @property
    def store(self) -> FindingStore:
        return self._store

    @property
    def verifier(self) -> Verifier:
        return self._verifier

    @property
    def falsifier(self) -> Falsifier:
        return self._falsifier

    @property
    def replanner(self) -> Replanner:
        return self._replanner

    @property
    def runtime(self) -> BOBRuntime:
        return self._runtime

    def run(
        self,
        mission: Mission,
        *,
        candidate_target: str = "src/fixed.py",
        candidate_summary: str = "session.py mishandles tokens",
        challenger_target: str = "src/still_buggy.py",
        challenger_forbidden_substring: str = "BUG: still contains the original defect",
        challenger_capability: Capability = Capability.READ,
    ) -> RunnerOutcome:
        """Execute the full M5 control loop and return a REFUSE verdict.

        M6 will evaluate the verdict against mission criteria.
        """
        # 1. Generate Plan A.
        plan_a = self._planner.plan_a(mission)
        # 2. Execute Plan A's first action through the Runtime.
        plan_a_step = plan_a.steps[0]
        rt_a = self._runtime.submit(
            ActionRequest(
                sequence=plan_a_step.sequence,
                requester=plan_a_step.requester,
                capability=plan_a_step.capability,
                target=plan_a_step.target,
                purpose=plan_a_step.purpose,
                plan_id=plan_a_step.plan_id,
                finding_id=plan_a_step.finding_id,
            ),
            mission,
        )
        if rt_a.broker_result.decision.decision.value != "allow":
            # Plan A was denied. Stop; return REFUSE.
            return RunnerOutcome(
                gate_verdict=GateVerdict.REFUSE,
                plan_a=plan_a,
                plan_b=None,
                finding=Finding(
                    finding_id="F-NA",
                    state=FindingState.UNVERIFIED,
                    summary="plan-a-denied",
                    target=plan_a_step.target,
                ),
                mission=mission,
                plan_a_step_runtime_seq=rt_a.request_seq,
                plan_b_step_runtime_seq=None,
            )

        # 3. Register a candidate Finding.
        finding = Finding(
            finding_id=f"F-{plan_a.plan_id[2:8]}",
            state=FindingState.UNVERIFIED,
            summary=candidate_summary,
            target=candidate_target,
        )
        self._store.register(finding)

        # 4. Verifier.verify: UNVERIFIED -> VERIFIED.
        verify_outcome = self._verifier.verify(
            finding,
            RetestSpec(
                capability=Capability.READ,
                target=candidate_target,
                expected_substring="OK",
            ),
            mission,
            requester="runner",
        )
        # 5. Falsifier.challenge: VERIFIED -> REFUTED.
        challenge_outcome = self._falsifier.challenge(
            self._store.get(finding.finding_id) or finding,
            ChallengeSpec(
                capability=challenger_capability,
                target=challenger_target,
                forbidden_substring=challenger_forbidden_substring,
            ),
            mission,
            requester="runner",
        )

        plan_b: Optional[Plan] = None
        plan_b_seq: Optional[int] = None
        refuted = self._store.get(finding.finding_id)
        if refuted is not None and refuted.state is FindingState.REFUTED:
            # 6. Build FocusedContext from the evidence chain.
            ctx = self._build_focused_context(refuted, plan_a, mission)
            # 7. Replan.
            plan_b = self._replanner.replan(ctx, plan_a)
            # 8. Submit Plan B's step through the Runtime (broker-mediated).
            if plan_b.steps:
                b_step = plan_b.steps[0]
                rt_b = self._runtime.submit(
                    ActionRequest(
                        sequence=b_step.sequence,
                        requester=b_step.requester,
                        capability=b_step.capability,
                        target=b_step.target,
                        purpose=b_step.purpose,
                        plan_id=b_step.plan_id,
                        finding_id=b_step.finding_id,
                    ),
                    mission,
                )
                plan_b_seq = rt_b.request_seq
        else:
            # Refutation did NOT happen; the runner must NOT replan.
            plan_b = None

        # 9. NEVER COMPLETE. Return REFUSE.
        return RunnerOutcome(
            gate_verdict=GateVerdict.REFUSE,
            plan_a=plan_a,
            plan_b=plan_b,
            finding=self._store.get(finding.finding_id) or finding,
            mission=mission,
            plan_a_step_runtime_seq=rt_a.request_seq,
            plan_b_step_runtime_seq=plan_b_seq,
        )

    def _build_focused_context(
        self,
        refuted: Finding,
        plan_a: Plan,
        mission: Mission,
    ) -> FocusedContext:
        """Compose a FocusedContext from the FindingStore evidence chain.

        The diagnostic_evidence list contains real EvidenceReceipt records
        whose sequence numbers point into the durable JSONL ledger.
        """
        records = self._ledger.records_for_finding(refuted.finding_id)
        receipts: list = []
        for rec in records:
            if rec.get("kind") != "evidence":
                continue
            receipts.append(
                _record_to_receipt(rec)
            )
        if not receipts:
            # Synthesize a minimum receipt so the Replanner can run.
            receipts = [
                _synth_receipt(self._ledger, refuted),
            ]
        return FocusedContext(
            refuted_claim=refuted,
            diagnostic_evidence=receipts,
            mission_scope=mission.scope,
        )


def _record_to_receipt(rec: dict):
    from raphael_bob.contracts import EvidenceReceipt
    return EvidenceReceipt(
        evidence_id=rec.get("evidence_id", ""),
        sequence=rec.get("seq", 0),
        producer=rec.get("producer", ""),
        payload=dict(rec),
    )


def _synth_receipt(ledger: EvidenceLedger, refuted: Finding):
    """Synthesize a minimum-viable receipt for the Replanner when no
    evidence records are linked yet (defensive; in practice the Falsifier
    always persists at least one counter-example record)."""
    from raphael_bob.contracts import EvidenceReceipt
    payload = {"refuted_finding_id": refuted.finding_id}
    return EvidenceReceipt(
        evidence_id=digest_id(payload, prefix="S"),
        sequence=ledger.all_records()[-1].get("seq", 0) if ledger.all_records() else 0,
        producer="runner",
        payload=payload,
    )


__all__ = [
    "Runner",
    "PlannerStub",
    "RunnerOutcome",
]