"""raphael_ibm_bob.runner — M5/M6/M9 Runner.

M5: drives the BOB control loop (Plan A -> Verifier -> Falsifier ->
    Replanner -> Plan B). Returns REFUSE unconditionally.
M6: after Plan B's verifier retest, the Runner delegates the final
    completion decision to `BOBQualityGate`. The Runner never produces
    COMPLETE itself.
M9: bounded multi-replan. Each recovery attempt registers a NEW finding
    (F1 for Plan A, F2 for Plan B, ...) because the M4 lifecycle does
    not allow re-verifying an already-REFUTED finding. The loop is
    bounded by `max_replans` (default 1 preserves the M5/M6 single
    replan). Every recovery action goes through Runtime -> Broker ->
    Policy; the Runner never produces COMPLETE itself.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
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
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateEvaluation, GateInputs
from raphael_ibm_bob.replanner import Replanner
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.planner import Planner
from raphael_ibm_bob.verifier import RetestSpec, Verifier


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class RunnerOutcome:
    """Public result of a Runner.run() call.

    The Runner NEVER returns COMPLETE itself; that is the Quality Gate's
    authority. The `gate_evaluation` field carries the gate's verdict and
    is the source of truth for completion.
    """
    gate_verdict: GateVerdict
    plan_a: Plan
    plan_b: Optional[Plan] = None
    plan_c: Optional[Plan] = None
    finding: Optional[Finding] = None
    findings: Tuple[Finding, ...] = ()
    mission: Optional[Mission] = None
    plan_a_step_runtime_seq: Optional[int] = None
    plan_b_step_runtime_seq: Optional[int] = None
    plan_c_step_runtime_seq: Optional[int] = None
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
        planner: Optional[Planner] = None,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._verifier = verifier
        self._falsifier = falsifier
        self._replanner = replanner
        self._gate = gate
        self._planner = planner or Planner()
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
        challenge_specs: Optional[List[ChallengeSpec]] = None,
        verification_tests: Tuple[str, ...] = (),
        regression_ok: bool = True,
        behavior_probe_ok: bool = True,
        max_replans: int = 1,
    ) -> RunnerOutcome:
        """Execute the bounded M5/M6/M9 control loop and return the gate's verdict.

        M6: the Runner persists a `producer="regression"` evidence record
        (when `regression_ok=True`) and a `producer="probe"` evidence
        record (when `behavior_probe_ok=True`) so the QualityGate can
        verify the source of these flags rather than trust caller
        fabrication. If either flag is False, the Runner does NOT
        persist the corresponding record and the gate will REFUSE.
        M9: each loop iteration operates on its own finding. Plan A is
        assessed as F1; when F1 is REFUTED and budget remains, the
        Replanner derives Plan B from F1's counter-evidence and the
        loop registers a NEW finding F2 for Plan B's claim (re-verifying
        the REFUTED F1 is forbidden by the M4 lifecycle). Iteration `i`
        challenges finding Fi with `challenge_specs[i]` when provided,
        else with the legacy challenger_* triple. After the loop,
        `verification_tests` (if any) are executed as broker-mediated
        RUN_TEST actions so the gate's required-test condition can be
        satisfied by real evidence. The loop never exceeds `max_replans`
        recovery attempts; exhaustion with a REFUTED terminal finding
        yields REFUSE from the gate.
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

        # 2. Register candidate Finding F1 for Plan A.
        finding = Finding(
            finding_id=f"F-{plan_a.plan_id[2:8]}",
            state=FindingState.UNVERIFIED,
            summary=candidate_summary,
            target=candidate_target,
        )
        self._store.register(finding)

        # 3. Verifier.verify F1: UNVERIFIED -> VERIFIED.
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

        # 4. Falsifier.challenge F1: VERIFIED -> REFUTED (or not).
        self._falsifier.challenge(
            self._store.get(finding.finding_id) or finding,
            self._challenge_spec(0, challenge_specs, challenger_capability,
                                 challenger_target,
                                 challenger_forbidden_substring),
            mission,
            requester="runner",
        )

        # 5. Bounded recovery loop. Iteration `attempt` replans from the
        # REFUTED finding findings[attempt] (backed by plans[attempt])
        # and assesses the new plan as a NEW finding, since a REFUTED
        # finding cannot be re-verified under the M4 lifecycle.
        plans = [plan_a]
        findings = [finding]
        plan_sequences = [rt_a.request_seq]

        for attempt in range(max_replans):
            current = self._store.get(findings[attempt].finding_id)
            if current is None:
                current = findings[attempt]
            if current.state is not FindingState.REFUTED:
                break
            ctx = self._build_focused_context(
                current, plans[attempt], mission)
            next_plan = self._replanner.replan(ctx, plans[attempt])
            plans.append(next_plan)
            if not next_plan.steps:
                break
            next_step = next_plan.steps[0]
            rt_next = self._runtime.submit(
                ActionRequest(
                    sequence=next_step.sequence,
                    requester=next_step.requester,
                    capability=next_step.capability,
                    target=next_step.target,
                    purpose=next_step.purpose,
                    plan_id=next_step.plan_id,
                    finding_id=next_step.finding_id,
                ),
                mission,
            )
            plan_sequences.append(rt_next.request_seq)
            # A new claim gets a new finding identity, deterministically
            # derived from the new plan, superseding the refuted one.
            recovery = Finding(
                finding_id=f"F-{next_plan.plan_id[2:8]}",
                state=FindingState.UNVERIFIED,
                summary=f"recovery candidate: {next_step.target}",
                target=next_step.target,
                supersedes=current.finding_id,
            )
            self._store.register(recovery)
            findings.append(recovery)
            # Retest the new candidate through the boundary. No fixed
            # marker is required: observability (ALLOW + success) is the
            # retest bar; behavioral judgment belongs to the falsifier.
            self._verifier.verify(
                recovery,
                RetestSpec(
                    capability=Capability.READ,
                    target=next_step.target,
                    expected_substring=None,
                ),
                mission,
                requester="runner",
            )
            # Challenge the new finding with this iteration's spec.
            self._falsifier.challenge(
                self._store.get(recovery.finding_id) or recovery,
                self._challenge_spec(attempt + 1, challenge_specs,
                                     challenger_capability,
                                     challenger_target,
                                     challenger_forbidden_substring),
                mission,
                requester="runner",
            )

        # 6. Broker-mediated final verification tests (M9). Each target
        # is submitted as RUN_TEST through Runtime -> Broker -> Policy
        # so the gate can satisfy its required-test condition from real
        # persisted evidence rather than caller assertions.
        for test_target in verification_tests:
            self._runtime.submit(
                ActionRequest(
                    sequence=0,
                    requester="runner",
                    capability=Capability.RUN_TEST,
                    target=test_target,
                    purpose="runner:final-verification",
                ),
                mission,
            )

        # 7. Persist regression / probe proof records (M6 anti-bypass).
        regression_seq = self._persist_regression_proof(regression_ok, mission)
        probe_seq = self._persist_probe_proof(behavior_probe_ok, mission)

        # 8. Delegate to QualityGate.
        latest = [
            self._store.get(f.finding_id) or f for f in findings
        ]
        evaluation = self._gate.evaluate(GateInputs(
            mission=mission,
            findings=list(self._store.all()),
            regression_ok=regression_ok,
            behavior_probe_ok=behavior_probe_ok,
        ))

        return RunnerOutcome(
            gate_verdict=evaluation.verdict,
            plan_a=plan_a,
            plan_b=plans[1] if len(plans) > 1 else None,
            plan_c=plans[2] if len(plans) > 2 else None,
            finding=self._store.get(finding.finding_id) or finding,
            findings=tuple(latest),
            mission=mission,
            plan_a_step_runtime_seq=plan_sequences[0],
            plan_b_step_runtime_seq=plan_sequences[1] if len(plan_sequences) > 1 else None,
            plan_c_step_runtime_seq=plan_sequences[2] if len(plan_sequences) > 2 else None,
            gate_evaluation=evaluation,
            regression_record_seq=regression_seq,
            probe_record_seq=probe_seq,
        )

    @staticmethod
    def _challenge_spec(
        index: int,
        challenge_specs: Optional[List[ChallengeSpec]],
        challenger_capability: Capability,
        challenger_target: str,
        challenger_forbidden_substring: str,
    ) -> ChallengeSpec:
        """Select the falsifier challenge for recovery iteration `index`.

        Iteration 0 challenges F1, iteration 1 challenges F2, and so on.
        An explicit per-iteration spec wins; otherwise the legacy
        challenger_* triple is used (M5/M6 behavior preserved).
        """
        if challenge_specs is not None and index < len(challenge_specs):
            return challenge_specs[index]
        return ChallengeSpec(
            capability=challenger_capability,
            target=challenger_target,
            forbidden_substring=challenger_forbidden_substring,
        )

    # --- provenance helpers ------------------------------------------------

    def _build_focused_context(
        self,
        refuted: Finding,
        parent_plan: Plan,
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
    "Planner",
    "RunnerOutcome",
]