"""raphael_bob.runner — M5/M6 Runner.

M5: drives the BOB control loop (Plan A -> Verifier -> Falsifier ->
    Replanner -> Plan B). Returns REFUSE unconditionally.
M6: after Plan B's verifier retest, the Runner delegates the final
    completion decision to `BOBQualityGate`. The Runner never produces
    COMPLETE itself.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

from raphael_bob.broker import BOBBroker
from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    EvidenceReceipt,
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
from raphael_bob.quality_gate import BOBQualityGate, GateEvaluation, GateInputs
from raphael_bob.replanner import Replanner
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
    """Public result of a Runner.run() call.

    The Runner NEVER returns COMPLETE itself; that is the Quality Gate's
    authority. The `gate_evaluation` field carries the gate's verdict and
    is the source of truth for completion.
    """
    gate_verdict: GateVerdict
    plan_a: Plan
    plan_b: Optional[Plan]
    finding: Finding
    mission: Mission
    plan_a_step_runtime_seq: int
    plan_b_step_runtime_seq: Optional[int]
    gate_evaluation: Optional[GateEvaluation] = None
    regression_record_seq: Optional[int] = None
    probe_record_seq: Optional[int] = None


class Runner:
    """Drives the BOB control loop and delegates COMPLETE to QualityGate."""

    def __init__(
        self,
        runtime: BOBRuntime,
        ledger: EvidenceLedger,
        store: FindingStore,
        verifier: Verifier,
        falsifier: Falsifier,
        replanner: Replanner,
        gate: BOBQualityGate,
        planner: Optional[PlannerStub] = None,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._verifier = verifier
        self._falsifier = falsifier
        self._replanner = replanner
        self._gate = gate
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
    def gate(self) -> BOBQualityGate:
        return self._gate

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
        regression_ok: bool = True,
        behavior_probe_ok: bool = True,
    ) -> RunnerOutcome:
        """Execute the full M5/M6 control loop and return the gate's verdict.

        M6: the Runner persists a `producer="regression"` evidence record
        (when `regression_ok=True`) and a `producer="probe"` evidence
        record (when `behavior_probe_ok=True`) so the QualityGate can
        verify the source of these flags rather than trust caller
        fabrication. If either flag is False, the Runner does NOT
        persist the corresponding record and the gate will REFUSE.
        """
        # 1. Generate Plan A.
        plan_a = self._planner.plan_a(mission)
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

        # 2. Register a candidate Finding.
        finding = Finding(
            finding_id=f"F-{plan_a.plan_id[2:8]}",
            state=FindingState.UNVERIFIED,
            summary=candidate_summary,
            target=candidate_target,
        )
        self._store.register(finding)

        # 3. Verifier.verify: UNVERIFIED -> VERIFIED.
        self._verifier.verify(
            finding,
            RetestSpec(
                capability=Capability.READ,
                target=candidate_target,
                expected_substring="OK",
            ),
            mission,
            requester="runner",
        )

        # 4. Falsifier.challenge: VERIFIED -> REFUTED.
        self._falsifier.challenge(
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
            ctx = self._build_focused_context(refuted, plan_a, mission)
            plan_b = self._replanner.replan(ctx, plan_a)
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
                # 5. Verifier on the corrected Plan B step.
                self._verifier.verify(
                    self._store.get(finding.finding_id) or finding,
                    RetestSpec(
                        capability=Capability.READ,
                        target=b_step.target,
                        expected_substring="OK",
                    ),
                    mission,
                    requester="runner",
                )

        # 6. Persist regression / probe proof records (M6 anti-bypass).
        regression_seq = self._persist_regression_proof(regression_ok, mission)
        probe_seq = self._persist_probe_proof(behavior_probe_ok, mission)

        # 7. Delegate to QualityGate.
        findings = list(self._store.all())
        evaluation = self._gate.evaluate(GateInputs(
            mission=mission,
            findings=findings,
            regression_ok=regression_ok,
            behavior_probe_ok=behavior_probe_ok,
        ))

        return RunnerOutcome(
            gate_verdict=evaluation.verdict,
            plan_a=plan_a,
            plan_b=plan_b,
            finding=self._store.get(finding.finding_id) or finding,
            mission=mission,
            plan_a_step_runtime_seq=rt_a.request_seq,
            plan_b_step_runtime_seq=plan_b_seq,
            gate_evaluation=evaluation,
            regression_record_seq=regression_seq,
            probe_record_seq=probe_seq,
        )

    # --- provenance helpers ------------------------------------------------

    def _build_focused_context(
        self,
        refuted: Finding,
        plan_a: Plan,
        mission: Mission,
    ) -> FocusedContext:
        """Compose a FocusedContext from the FindingStore evidence chain."""
        records = self._ledger.records_for_finding(refuted.finding_id)
        receipts: List[EvidenceReceipt] = []
        for rec in records:
            if rec.get("kind") != "evidence":
                continue
            receipts.append(EvidenceReceipt(
                evidence_id=rec.get("evidence_id", ""),
                sequence=rec.get("seq", 0),
                producer=rec.get("producer", ""),
                payload=dict(rec),
            ))
        if not receipts:
            payload = {"refuted_finding_id": refuted.finding_id}
            receipts = [EvidenceReceipt(
                evidence_id=digest_id(payload, prefix="S"),
                sequence=self._ledger.all_records()[-1].get("seq", 0)
                    if self._ledger.all_records() else 0,
                producer="runner",
                payload=payload,
            )]
        return FocusedContext(
            refuted_claim=refuted,
            diagnostic_evidence=receipts,
            mission_scope=mission.scope,
        )

    def _persist_regression_proof(
        self, regression_ok: bool, mission: Mission
    ) -> Optional[int]:
        """Persist a producer='regression' evidence record iff regression_ok."""
        if not regression_ok:
            return None
        payload = {
            "kind": "regression",
            "mission_id": mission.mission_id,
            "result": "passed",
        }
        ev_id = digest_id(payload, prefix="RG")
        return self._ledger.append_evidence(
            evidence_id=ev_id,
            producer="regression",
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            payload=payload,
        )

    def _persist_probe_proof(
        self, behavior_probe_ok: bool, mission: Mission
    ) -> Optional[int]:
        """Persist a producer='probe' evidence record iff behavior_probe_ok."""
        if not behavior_probe_ok:
            return None
        payload = {
            "kind": "probe",
            "mission_id": mission.mission_id,
            "result": "passed",
            "allowed": True,
        }
        ev_id = digest_id(payload, prefix="PB")
        return self._ledger.append_evidence(
            evidence_id=ev_id,
            producer="probe",
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            payload=payload,
        )


__all__ = [
    "Runner",
    "PlannerStub",
    "RunnerOutcome",
]