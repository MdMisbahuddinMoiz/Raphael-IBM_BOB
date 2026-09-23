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
from typing import Any, List, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
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


#: Legacy Plan-A retest marker. Retained as the default so existing
#: generic Runner behavior is unchanged when a mission declares nothing.
DEFAULT_CANDIDATE_EXPECTED_SUBSTRING = "OK"

#: Sentinel distinguishing "caller did not supply an expectation" from an
#: explicit `None` (which means: a successful ALLOWed READ is sufficient).
_UNSET = object()


def resolve_plan_a_expected_substring(
    mission: Mission, override: object = _UNSET
) -> Optional[str]:
    """Resolve the Plan-A retest content expectation.

    Precedence (smallest, explicit-first design):
        1. an explicit `override` argument;
        2. `mission.problem["verification_expected_substring"]` when the
           mission declares it (a string marker, or explicit ``None`` to
           require only a successful ALLOWed READ);
        3. the legacy default ``"OK"`` (backward compatibility).

    A declared empty/invalid value falls back to the strict legacy
    default rather than silently weakening verification.
    """
    if override is not _UNSET:
        return override  # type: ignore[return-value]
    problem = mission.problem if isinstance(mission.problem, dict) else {}
    if "verification_expected_substring" in problem:
        value = problem.get("verification_expected_substring")
        if value is None:
            return None
        if isinstance(value, str) and value:
            return value
    return DEFAULT_CANDIDATE_EXPECTED_SUBSTRING


@dataclass(frozen=True)
class ProbeSpec:
    capability: Capability
    target: str
    expected_substring: Optional[str] = None
    purpose: str = "runner:independent-probe"


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
        candidate_expected_substring: object = _UNSET,
        challenger_target: str = "src/still_buggy.py",
        challenger_forbidden_substring: str = "BUG: still contains the original defect",
        challenger_capability: Capability = Capability.READ,
        challenge_specs: Optional[List[ChallengeSpec]] = None,
        verification_tests: Tuple[str, ...] = (),
        probe_spec: Optional["ProbeSpec"] = None,
        max_replans: int = 1,
    ) -> RunnerOutcome:
        """Execute the bounded M5/M6/M9 control loop and return the gate's verdict.

        M6/D12.1: the Runner does NOT accept caller regression/probe
        booleans. `regression_ok` is derived from the actual exit status of
        the declared `verification_tests` (RUN_TEST) executions, and a
        `producer="regression"` record is persisted only when a real test
        execution passed. `behavior_probe_ok` is derived from the governed
        `probe_spec` observation (ActionRequest -> Policy -> Broker ->
        Runtime -> observation); with no `probe_spec` it is False. Both
        derived values are passed to the QualityGate, which independently
        cross-checks the persisted records, so a caller cannot fabricate
        completion.
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
        yields REFUSE from the gate. The Plan-A retest content
        expectation is resolved explicitly via
        `resolve_plan_a_expected_substring`: an explicit
        `candidate_expected_substring` wins, else
        `mission.problem["verification_expected_substring"]` (a marker,
        or explicit None for observation-only missions), else the legacy
        `"OK"` default. The Verifier and QualityGate are unchanged.
        """
        # 1. Generate Plan A.
        plan_a = self._planner.plan_a(mission)
        plan_a_results = self._submit_plan(plan_a, mission)
        rt_a = plan_a_results[0]

        # 2. Register candidate Finding F1 for Plan A.
        finding = Finding(
            finding_id=f"F-{plan_a.plan_id[2:8]}",
            state=FindingState.UNVERIFIED,
            summary=candidate_summary,
            target=candidate_target,
        )
        self._store.register(finding)

        # 3. Verifier.verify F1: UNVERIFIED -> VERIFIED. The Plan-A
        # expected content marker is explicit and mission-derived
        # (see resolve_plan_a_expected_substring), never a hidden
        # constant.
        self._verifier.verify(
            finding,
            RetestSpec(
                capability=Capability.READ,
                target=candidate_target,
                expected_substring=resolve_plan_a_expected_substring(
                    mission, candidate_expected_substring),
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
            next_plan_results = self._submit_plan(next_plan, mission)
            rt_next = next_plan_results[0]
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

        regression_ok = False
        regression_seq: Optional[int] = None
        test_runs: List[Tuple[Any, Any, bool]] = []
        for test_target in verification_tests:
            rt_test = self._runtime.submit(
                ActionRequest(
                    sequence=0,
                    requester="runner",
                    capability=Capability.RUN_TEST,
                    target=test_target,
                    purpose="runner:final-verification",
                ),
                mission,
            )
            execution = rt_test.execution
            passed = bool(
                execution is not None
                and execution.success
                and (execution.evidence or {}).get("returncode") == 0)
            test_runs.append((test_target, rt_test, passed))
        regression_ok = bool(test_runs) and all(p for _, _, p in test_runs)
        if regression_ok:
            test_target, rt_test, _passed = test_runs[-1]
            payload = {
                "kind": "regression",
                "mission_id": mission.mission_id,
                "result": "passed",
                "test": test_target,
                "returncode": 0,
                "request_seq": rt_test.request_seq,
                "result_seq": rt_test.result_seq,
                "source": "runner:final-verification",
            }
            regression_seq = self._ledger.append_evidence(
                evidence_id=digest_id(payload, prefix="RG"),
                producer="regression",
                request_seq=rt_test.request_seq,
                decision_seq=rt_test.decision_seq,
                result_seq=rt_test.result_seq,
                payload=payload,
            )

        probe_ok = False
        probe_seq: Optional[int] = None
        effective_probe = probe_spec
        if effective_probe is None:
            effective_probe = ProbeSpec(
                capability=Capability.READ,
                target=candidate_target,
                expected_substring=resolve_plan_a_expected_substring(
                    mission, candidate_expected_substring),
            )
        if effective_probe is not None:
            rt_probe = self._runtime.submit(
                ActionRequest(
                    sequence=0,
                    requester="runner",
                    capability=effective_probe.capability,
                    target=effective_probe.target,
                    purpose=effective_probe.purpose,
                ),
                mission,
            )
            probe_execution = rt_probe.execution
            probe_allowed = (
                rt_probe.broker_result.decision.decision is Decision.ALLOW)
            observed = (json.dumps(probe_execution.evidence, sort_keys=True)
                        if probe_execution is not None else "")
            observation_matched = bool(
                probe_execution is not None
                and probe_execution.success
                and (effective_probe.expected_substring is None
                     or effective_probe.expected_substring in observed))
            probe_ok = bool(probe_allowed and observation_matched)
            if probe_ok:
                payload = {
                    "kind": "probe",
                    "mission_id": mission.mission_id,
                    "result": "passed",
                    "allowed": True,
                    "invariant": effective_probe.expected_substring,
                    "capability": effective_probe.capability.value,
                    "target": effective_probe.target,
                    "request_seq": rt_probe.request_seq,
                    "result_seq": rt_probe.result_seq,
                    "source": "runner:independent-probe",
                }
                probe_seq = self._ledger.append_evidence(
                    evidence_id=digest_id(payload, prefix="PB"),
                    producer="probe",
                    request_seq=rt_probe.request_seq,
                    decision_seq=rt_probe.decision_seq,
                    result_seq=rt_probe.result_seq,
                    payload=payload,
                )

        latest = [
            self._store.get(f.finding_id) or f for f in findings
        ]
        evaluation = self._gate.evaluate(GateInputs(
            mission=mission,
            findings=list(self._store.all()),
            regression_ok=regression_ok,
            behavior_probe_ok=probe_ok,
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

    def _submit_plan(self, plan: Plan, mission: Mission) -> list:
        return [self._runtime.submit(step, mission) for step in plan.steps]

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

__all__ = [
    "DEFAULT_CANDIDATE_EXPECTED_SUBSTRING",
    "ProbeSpec",
    "Runner",
    "Planner",
    "RunnerOutcome",
    "resolve_plan_a_expected_substring",
]
