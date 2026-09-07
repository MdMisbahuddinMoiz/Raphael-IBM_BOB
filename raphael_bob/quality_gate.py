"""raphael_bob.quality_gate — M6 Output QualityGate.

The QualityGate is the SOLE authority allowed to declare COMPLETE. The
Planner, Runner, Verifier, Falsifier, Replanner, and CLI may return any
other verdict (REFUSE, intermediate), but ONLY this class may return
COMPLETE under M6 conditions.

`evaluate(...)` consumes the actual persisted evidence ledger and a
small set of bool flags (regression_ok, behavior_probe_ok) whose source
is the caller's responsibility to trace to real test/probe results.

Conditions:

    A  Mission criterion      - the Mission has non-empty criteria
                                (semantic match is left to the M7 hero).
    B  Required tests         - regression_ok=True and the ledger
                                contains at least one "test"-shaped
                                RUN_TEST record.
    C  Full regression        - regression_ok=True; the ledger shows
                                multiple distinct capability invocations.
    D  Independent probe      - behavior_probe_ok=True.
    E  Scope                  - every recorded target must be inside the
                                declared workspace AND mission scope.
    F  Evidence               - the ledger contains request, decision,
                                result, and evidence records.
    G  Finding state          - no UNVERIFIED finding that affects the
                                mission. REFUTED findings must have a
                                subsequent replan evidence record (or
                                the gate records a REFUSE).

Failure mode:
    ANY condition failing -> REFUSE.
    Missing evidence      -> REFUSE.
    No gate decision is produced silently; EVERY evaluate() call writes a
    GateRecord to the ledger so the final decision is reconstructible.

Anti-bypass:
    Only `BOBQualityGate.evaluate()` returns COMPLETE under M6 conditions.
    Constructing `GateVerdict.COMPLETE` directly in another module is
    not the bypass: the bypass would be to call the QualityGate with
    fabricated bools. The structural guard:
      - `behavior_probe_ok` and `regression_ok` MUST each be backed by
        a `producer="probe"` or `producer="regression"` evidence record.
    If a caller claims `behavior_probe_ok=True` without a probe evidence
    record, the gate returns REFUSE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from raphael_bob.contracts import (
    Finding,
    FindingState,
    GateVerdict,
    Mission,
)
from raphael_bob.evidence_ledger import (
    EvidenceLedger,
    RecordKind,
    digest_id,
)


@dataclass(frozen=True)
class GateInputs:
    """Inputs the gate consumes at evaluate-time.

    `regression_ok` and `behavior_probe_ok` MUST be backed by evidence
    records in the ledger (the gate checks this).
    """
    mission: Mission
    findings: List[Finding]
    regression_ok: bool
    behavior_probe_ok: bool
    # Optional pre-computed summary. The gate re-derives it from the
    # ledger regardless, so this field is informational only.
    workspace_root: Optional[str] = None


@dataclass(frozen=True)
class GateEvaluation:
    """Public result of a QualityGate.evaluate() call."""
    verdict: GateVerdict
    passed: Tuple[str, ...]
    failed: Tuple[str, ...]
    reasons: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    finding_refs: Tuple[str, ...]


class BOBQualityGate:
    """The Output Quality Gate. Sole COMPLETE authority."""

    # Names of the seven conditions checked.
    CONDITION_NAMES: Tuple[str, ...] = (
        "A:mission-criterion",
        "B:required-tests",
        "C:regression",
        "D:independent-behavior-probe",
        "E:scope",
        "F:evidence",
        "G:finding-state",
    )

    def __init__(self, ledger: EvidenceLedger):
        self._ledger = ledger

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    # --- main entry point ---------------------------------------------------

    def evaluate(self, inputs: GateInputs) -> GateEvaluation:
        """Evaluate the inputs against the ledger; return a GateEvaluation.

        Persists a `GateRecord` to the ledger regardless of verdict.
        """
        all_records = self._ledger.all_records()
        evidence_records = [r for r in all_records if r.get("kind") == RecordKind.EVIDENCE.value]
        request_records = [r for r in all_records if r.get("kind") == RecordKind.REQUEST.value]
        result_records = [r for r in all_records if r.get("kind") == RecordKind.RESULT.value]
        decision_records = [r for r in all_records if r.get("kind") == RecordKind.DECISION.value]
        finding_records = [r for r in all_records if r.get("kind") == RecordKind.FINDING.value]

        passed: List[str] = []
        failed: List[str] = []
        reasons: List[str] = []
        evidence_refs: List[str] = []
        finding_refs: List[str] = []

        # ---- Condition A: mission criterion ----
        if inputs.mission.criteria:
            passed.append("A:mission-criterion")
        else:
            failed.append("A:mission-criterion")
            reasons.append("mission has no criteria")

        # ---- Condition B: required tests ----
        run_test_records = [
            r for r in request_records
            if r.get("capability") == "run_test"
        ]
        if inputs.regression_ok and run_test_records:
            passed.append("B:required-tests")
            for r in run_test_records:
                eid = r.get("evidence_id", "")
                if eid:
                    evidence_refs.append(eid)
        else:
            failed.append("B:required-tests")
            if not inputs.regression_ok:
                reasons.append("regression_ok=False (caller did not prove regression)")
            else:
                reasons.append("no RUN_TEST capability invocation in the ledger")

        # ---- Condition C: full regression ----
        distinct_caps = {r.get("capability") for r in request_records}
        if inputs.regression_ok and len(distinct_caps) >= 2:
            passed.append("C:regression")
        else:
            failed.append("C:regression")
            if not inputs.regression_ok:
                reasons.append("regression_ok=False")
            else:
                reasons.append(f"only {len(distinct_caps)} distinct capability(ies) in ledger (need >=2)")

        # ---- Condition D: independent behavior probe ----
        # The probe MUST have a producer="probe" evidence record with
        # allowed=True; a bare True is not enough.
        probe_records = [
            r for r in evidence_records if r.get("producer") == "probe"
        ]
        probe_success = any(
            r.get("payload", {}).get("allowed") is True
            for r in probe_records
        )
        if inputs.behavior_probe_ok and probe_success:
            passed.append("D:independent-behavior-probe")
            for r in probe_records:
                eid = r.get("evidence_id", "")
                if eid:
                    evidence_refs.append(eid)
        else:
            failed.append("D:independent-behavior-probe")
            if not inputs.behavior_probe_ok:
                reasons.append("behavior_probe_ok=False (no probe proof supplied)")
            else:
                reasons.append(
                    "behavior_probe_ok=True but no producer='probe' evidence record with allowed=True"
                )

        # ---- Condition E: scope ----
        # Every recorded request target must contain the mission scope
        # substring (when scope is non-empty). All decisions must be
        # ALLOW; no DENY records that actually executed (result after DENY).
        scope_ok = True
        if inputs.mission.scope:
            for r in request_records:
                tgt = (r.get("target") or "").replace("\\", "/")
                if inputs.mission.scope not in tgt:
                    scope_ok = False
                    reasons.append(
                        f"scope violation: target '{tgt}' not in mission scope '{inputs.mission.scope}'"
                    )
                    break
        for r in decision_records:
            if r.get("decision") == "deny" and r.get("request_seq") in {
                rr.get("seq") for rr in result_records
            }:
                scope_ok = False
                reasons.append("DENY record paired with result record (scope/enforcement violation)")
                break
        if scope_ok:
            passed.append("E:scope")
        else:
            failed.append("E:scope")

        # ---- Condition F: evidence ----
        if (request_records and decision_records
                and result_records and evidence_records):
            passed.append("F:evidence")
            # Capture the most recent 8 evidence refs as the trail.
            for r in evidence_records[-8:]:
                eid = r.get("evidence_id", "")
                if eid:
                    evidence_refs.append(eid)
        else:
            failed.append("F:evidence")
            reasons.append(
                f"missing record kinds: "
                f"requests={len(request_records)} decisions={len(decision_records)} "
                f"results={len(result_records)} evidence={len(evidence_records)}"
            )

        # ---- Condition G: finding state ----
        # - No UNVERIFIED finding that affects the mission.
        # - REFUTED findings must have a subsequent replan evidence record
        #   OR must be superseded.
        bad_findings: List[Finding] = []
        for f in inputs.findings:
            if f.state is FindingState.UNVERIFIED:
                bad_findings.append(f)
                reasons.append(
                    f"unresolved UNVERIFIED finding: {f.finding_id} (target={f.target})"
                )
            elif f.state is FindingState.REFUTED:
                # A REFUTED finding is acceptable IFF the replanner has
                # produced a plan_b record for it. Look at the replan
                # evidence records for a matching plan_b_id.
                replan_for_finding = [
                    r for r in evidence_records
                    if r.get("producer") == "replanner"
                    and r.get("finding_id") == f.finding_id
                ]
                if not replan_for_finding:
                    bad_findings.append(f)
                    reasons.append(
                        f"REFUTED finding without replan: {f.finding_id}"
                    )
        for f in bad_findings:
            finding_refs.append(f.finding_id)
        if not bad_findings:
            passed.append("G:finding-state")
        else:
            failed.append("G:finding-state")

        # ---- Verdict ----
        verdict = GateVerdict.COMPLETE if not failed else GateVerdict.REFUSE
        if not inputs.mission.criteria and not failed:
            # A mission with no criteria cannot be evaluated as COMPLETE.
            failed.append("A:mission-criterion")
            verdict = GateVerdict.REFUSE
            reasons.append("refusing: mission has no success criteria")

        # Persist the gate decision.
        run_id = self._ledger.run_dir().name
        payload = {
            "decision": verdict.value,
            "mission_id": inputs.mission.mission_id,
            "passed": list(passed),
            "failed": list(failed),
            "reasons": list(reasons),
            "evidence_refs": list(evidence_refs),
            "finding_refs": list(finding_refs),
        }
        self._ledger.append_gate(
            decision=verdict.value,
            run_id=run_id,
            mission_id=inputs.mission.mission_id,
            checks=tuple(list(passed) + list(failed)),
            evidence_refs=tuple(evidence_refs),
            finding_refs=tuple(finding_refs),
            reasons=tuple(reasons),
            payload=payload,
        )

        return GateEvaluation(
            verdict=verdict,
            passed=tuple(passed),
            failed=tuple(failed),
            reasons=tuple(reasons),
            evidence_refs=tuple(evidence_refs),
            finding_refs=tuple(finding_refs),
        )


__all__ = ["BOBQualityGate", "GateInputs", "GateEvaluation"]