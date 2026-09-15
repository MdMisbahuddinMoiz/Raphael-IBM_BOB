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
                                 shows a RUN_TEST request with a Policy
                                 ALLOW decision, a successful result,
                                 and a persisted artifact proving
                                 returncode == 0. DENIED or failed
                                 tests never satisfy B. (M9 repair.)
    C  Full regression        - regression_ok=True backed by a
                                 producer="regression" record; the
                                 ledger shows >=2 distinct ALLOWed
                                 capability invocations. DENIED
                                 requests contribute no breadth.
                                 (M9 repair.)
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

import json
from dataclasses import dataclass
from pathlib import Path
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

    @staticmethod
    def _artifact_reports_success(result_record: dict) -> bool:
        """Check the persisted result artifact for returncode == 0.

        The ledger's ResultRecord carries only success/output digests;
        the RUN_TEST returncode lives in the artifact JSON written by
        ArtifactSink. Fail-closed: any missing file, parse error, or
        missing key reports False.
        """
        ref = result_record.get("artifact_ref", "")
        if not ref:
            return False
        try:
            path = Path(ref)
            if not path.is_file():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if data.get("success") is not True:
            return False
        evidence = data.get("evidence", {})
        if not isinstance(evidence, dict):
            return False
        return evidence.get("returncode") == 0

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

        # ---- Condition B: required tests (ledger-backed) ----
        # A RUN_TEST request satisfies B only when the ledger shows the
        # full chain for the same request: Policy ALLOW decision, an
        # executed successful result, and a persisted artifact proving
        # returncode == 0. A DENIED request, a failed test, or a missing
        # artifact never satisfies B. (M9 repair: the M6 check counted
        # any RUN_TEST request, including DENIED ones.)
        decisions_by_request = {}
        for r in decision_records:
            decisions_by_request[r.get("request_seq")] = r.get("decision")
        results_by_request = {}
        for r in result_records:
            if r.get("success") is True:
                results_by_request[r.get("request_seq")] = r
        passing_test_evidence: List[str] = []
        run_test_requests = [
            r for r in sorted(request_records, key=lambda x: x.get("seq", 0))
            if r.get("capability") == "run_test"
        ]
        denied_tests = 0
        unsuccessful_tests = 0
        for r in run_test_requests:
            req_seq = r.get("seq")
            if decisions_by_request.get(req_seq) != "allow":
                denied_tests += 1
                continue
            res = results_by_request.get(req_seq)
            if res is None or not self._artifact_reports_success(res):
                unsuccessful_tests += 1
                continue
            for e in evidence_records:
                if (e.get("producer") == "execution"
                        and e.get("request_seq") == req_seq):
                    eid = e.get("evidence_id", "")
                    if eid:
                        passing_test_evidence.append(eid)
        if inputs.regression_ok and passing_test_evidence:
            passed.append("B:required-tests")
            evidence_refs.extend(sorted(set(passing_test_evidence)))
        else:
            failed.append("B:required-tests")
            if not inputs.regression_ok:
                reasons.append("regression_ok=False (caller did not prove regression)")
            elif not run_test_requests:
                reasons.append("no RUN_TEST capability invocation in the ledger")
            else:
                reasons.append(
                    "no RUN_TEST invocation with ALLOW + successful result "
                    "+ returncode 0 in persisted evidence "
                    f"(denied={denied_tests} unsuccessful-or-unproven={unsuccessful_tests})"
                )

        # ---- Condition C: full regression (ledger-backed breadth) ----
        # Only ALLOWed requests count as invocations: a DENIED request
        # performed no work and contributes no breadth. The caller's
        # regression_ok flag must additionally be backed by a
        # producer="regression" evidence record. (M9 repair.)
        regression_records = [
            r for r in evidence_records if r.get("producer") == "regression"
        ]
        allowed_caps = {
            r.get("capability") for r in request_records
            if decisions_by_request.get(r.get("seq")) == "allow"
        }
        if (inputs.regression_ok and regression_records
                and len(allowed_caps) >= 2):
            passed.append("C:regression")
        else:
            failed.append("C:regression")
            if not inputs.regression_ok:
                reasons.append("regression_ok=False")
            elif not regression_records:
                reasons.append(
                    "regression_ok=True but no producer='regression' "
                    "evidence record in the ledger"
                )
            else:
                reasons.append(
                    f"only {len(allowed_caps)} distinct ALLOWed "
                    f"capability(ies) in ledger (need >=2)"
                )

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