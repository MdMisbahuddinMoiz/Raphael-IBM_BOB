"""raphael_ibm_bob.harness.telnet_run — deterministic governed Telnet mission (D12).

Wires the additive ``NETWORK_TELNET_SESSION`` capability into the NORMAL run
lifecycle and produces the SAME real, ledger-backed evidence the existing
QualityGate conditions require (no gate semantics changed):

    A  mission criterion      mission.criteria
    B  required-tests         a governed RUN_TEST (returncode 0 artifact)
    C  regression             producer="regression" tied to that RUN_TEST
                              + >=2 distinct ALLOWed capabilities
    D  independent probe      a SEPARATE governed Telnet observation
                              (producer="probe", allowed=True)
    E  scope                  TargetProfile scope (Policy + gate share it)
    F  evidence               request/decision/result/evidence chain
    G  finding state          Telnet flag Finding independently VERIFIED

Nothing is fabricated: the candidate comes from an actual ``cat flag.txt``
observation through the governed Telnet capability, verification is a second
independent session, and the falsifier makes a third, distinct observation.
The flag value is never written to source, tests, or documentation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, create_run_dir, digest_id
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.network_run import NetworkRunResult
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.harness.session import RaphaelSession, save_session
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import get_target_store
from raphael_ibm_bob.telnet_runtime import (
    DEFAULT_TELNET_TIMEOUT,
    build_telnet_spec,
    flag_sha256,
    get_telnet_mediator,
)
from raphael_ibm_bob.workspace import Workspace

TELNET_PURPOSE_FLAG = "telnet-session"
TELNET_PURPOSE_PROBE = "telnet-session mode=probe"
TELNET_PURPOSE_NEGATIVE = "telnet-session mode=negative-control"
DEFAULT_RUN_TEST_TIMEOUT = 30.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _telnet_result(execution) -> dict:
    if execution is None:
        return {}
    return (execution.evidence or {}).get("telnet_result") or {}


def _append(ledger: EvidenceLedger, *, producer: str, prefix: str,
            payload: dict, request_seq: int, decision_seq: int,
            result_seq: Optional[int]) -> str:
    evidence_id = digest_id(payload, prefix=prefix)
    ledger.append_evidence(
        evidence_id=evidence_id, producer=producer, request_seq=request_seq,
        decision_seq=decision_seq, result_seq=result_seq, payload=payload)
    return evidence_id


def run_telnet_mission(session: RaphaelSession, mission: Mission,
                       workspace_root: Path, *, runs_root: Path,
                       sessions_root: Optional[Path] = None,
                       target_store: Any = None,
                       mediator: Any = None,
                       timeout_seconds: float = DEFAULT_TELNET_TIMEOUT,
                       requester: str = "operator") -> NetworkRunResult:
    """Drive one governed Telnet mission to a terminal state."""
    run_id, run_dir = create_run_dir(runs_root)
    run = RaphaelRun(
        run_id=run_id, session_id=session.session_id, mission=mission,
        workspace_root=str(workspace_root), state="running",
        ledger_dir=str(run_dir))
    session.add_run(run_id)
    save_run(run)

    store = target_store if target_store is not None else get_target_store()
    mediator = mediator if mediator is not None else get_telnet_mediator()
    workspace = Workspace(workspace_root)
    ledger = EvidenceLedger(run_dir)
    findings = FindingStore(ledger)
    gate = BOBQualityGate(ledger, target_store=store)

    verified = False
    flag: Optional[str] = None
    regression_ok = False
    probe_ok = False
    reason = ""

    try:
        profile = store.get_target(mission.mission_id)
        spec = build_telnet_spec(mission, profile) if profile is not None else None

        if profile is None:
            reason = "no-authorized-target-for-mission"
        elif spec is None:
            reason = "no-telnet-session-spec"
        else:
            policy = BOBPolicy(workspace, target_store=store)
            broker = BOBBroker(policy, workspace, ledger=ledger,
                               network_mediator=None, target_store=store,
                               telnet_mediator=mediator)
            runtime = BOBRuntime(broker)
            target_url = f"telnet://{profile.locator}:{spec.port}"

            # --- 1. governed flag observation -> Finding -> verify -> falsify ---
            runtime_result = runtime.submit(ActionRequest(
                sequence=0, requester=requester,
                capability=Capability.NETWORK_TELNET_SESSION, target=target_url,
                purpose=TELNET_PURPOSE_FLAG, timeout_seconds=timeout_seconds),
                mission)
            execution = runtime_result.execution
            telnet = _telnet_result(execution)
            invocation = telnet.get("invocation_id")
            observed = telnet.get("flag")

            if execution is not None and execution.success and observed:
                flag = observed
                finding = Finding(
                    finding_id=f"F-{run_id[-6:]}-telnet",
                    state=FindingState.UNVERIFIED,
                    summary=f"telnet-flag:{flag_sha256(observed)[:12]}",
                    target=target_url, mission_id=mission.mission_id)
                findings.register(finding)
                from raphael_ibm_bob.telnet_runtime import TelnetVerifier
                verifier = TelnetVerifier(
                    runtime, ledger, findings,
                    replay_guard=getattr(mediator, "replay_guard", None))
                outcome = verifier.verify_independent(
                    findings.get(finding.finding_id), mission,
                    original_invocation_id=invocation,
                    expected_flag_hash=flag_sha256(observed),
                    timeout_seconds=timeout_seconds)
                verified = (outcome.classification == "supported"
                            and outcome.transition_applied)
                if verified:
                    candidate = observed

                    def _negative_control_shows_flag(
                            payload: dict, _candidate: str = candidate) -> bool:
                        tr = payload.get("telnet_result") or {}
                        for c in (tr.get("commands") or []):
                            if _candidate and _candidate in (
                                    c.get("output_preview") or ""):
                                return True
                        return False

                    Falsifier(runtime, ledger, findings).challenge(
                        findings.get(finding.finding_id),
                        ChallengeSpec(
                            capability=Capability.NETWORK_TELNET_SESSION,
                            target=target_url,
                            purpose=TELNET_PURPOSE_NEGATIVE,
                            predicate=_negative_control_shows_flag),
                        mission)

            # --- 2. condition D: independent governed behavior probe ---
            # A SEPARATE Telnet session (own invocation) runs the declared
            # probe command and asserts the authorized endpoint is reachable
            # and authenticable THROUGH the governed path. Never the flag fetch.
            probe_rt = runtime.submit(ActionRequest(
                sequence=0, requester="telnet-probe",
                capability=Capability.NETWORK_TELNET_SESSION, target=target_url,
                purpose=TELNET_PURPOSE_PROBE, timeout_seconds=timeout_seconds),
                mission)
            p_exec = probe_rt.execution
            p_telnet = _telnet_result(p_exec)
            p_commands = p_telnet.get("commands") or []
            probe_ok = bool(
                p_exec is not None and p_exec.success
                and p_telnet.get("authenticated") is True
                and any(c.get("output_sha256") and (c.get("bytes") or 0) > 0
                        for c in p_commands))
            if probe_ok:
                first = p_commands[0]
                _append(ledger, producer="probe", prefix="PB", payload={
                    "kind": "probe",
                    "probe_id": f"TELPROBE-{run_id[-6:]}",
                    "mission_id": mission.mission_id,
                    "result": "passed", "allowed": True,
                    "invariant":
                        "authorized-telnet-endpoint-reachable-and-authenticated",
                    "endpoint": target_url, "username": spec.username,
                    "auth_decision": p_telnet.get("auth_decision"),
                    "command": first.get("command"),
                    "output_sha256": first.get("output_sha256"),
                    "session_bytes": p_telnet.get("session_bytes"),
                    "invocation_id": p_telnet.get("invocation_id"),
                    "source": "telnet-independent-behavior-probe",
                    "request_seq": probe_rt.request_seq,
                    "decision_seq": probe_rt.decision_seq,
                    "result_seq": probe_rt.result_seq,
                }, request_seq=probe_rt.request_seq,
                    decision_seq=probe_rt.decision_seq,
                    result_seq=probe_rt.result_seq)

            # --- 3. conditions B/C: real governed required-tests + regression ---
            tests = (mission.problem or {}).get("verification_tests") or []
            ran_any = False
            tests_ok = True
            last: Optional[Tuple[str, Any, Any]] = None
            for test_target in tests:
                ran_any = True
                t_rt = runtime.submit(ActionRequest(
                    sequence=0, requester="telnet-run",
                    capability=Capability.RUN_TEST, target=test_target,
                    purpose="telnet-run:required-test",
                    timeout_seconds=DEFAULT_RUN_TEST_TIMEOUT), mission)
                execution_ok = (t_rt.execution is not None
                                and t_rt.execution.success)
                rc = ((t_rt.execution.evidence or {}).get("returncode")
                      if execution_ok else None)
                if execution_ok and rc == 0:
                    last = (test_target, t_rt, rc)
                else:
                    tests_ok = False
            regression_ok = ran_any and tests_ok
            if regression_ok and last is not None:
                test_target, t_rt, rc = last
                _append(ledger, producer="regression", prefix="RG", payload={
                    "kind": "regression", "mission_id": mission.mission_id,
                    "result": "passed", "test": test_target, "returncode": rc,
                    "request_seq": t_rt.request_seq,
                    "result_seq": t_rt.result_seq,
                    "source": "telnet-run:required-test"},
                    request_seq=t_rt.request_seq,
                    decision_seq=t_rt.decision_seq,
                    result_seq=t_rt.result_seq)

        evaluation = gate.evaluate(GateInputs(
            mission=mission, findings=list(findings.all()),
            regression_ok=regression_ok, behavior_probe_ok=probe_ok))
        run.gate_verdict = evaluation.verdict.value
        run.finding_ids = [f.finding_id for f in findings.all()]
        if evaluation.verdict.value == "complete":
            run.state = "completed"
        else:
            run.state = "refused"
            reason = reason or "; ".join(evaluation.reasons)[:400]
    except Exception as exc:
        run.state = "failed"
        run.failure_reason = f"{type(exc).__name__}:{exc}"[:500]
        run.finished_at = _utcnow()
        save_run(run)
        ledger.close()
        if sessions_root is not None:
            save_session(session, sessions_root)
        raise

    run.finished_at = _utcnow()
    if run.state == "refused" and reason:
        run.failure_reason = reason
    save_run(run)
    ledger.close()
    if sessions_root is not None:
        save_session(session, sessions_root)

    return NetworkRunResult(
        run=run, terminal=run.state, gate_verdict=run.gate_verdict,
        verified=verified, flag=flag, terminal_reason=(run.failure_reason or ""))


__all__ = [
    "DEFAULT_RUN_TEST_TIMEOUT",
    "TELNET_PURPOSE_FLAG",
    "TELNET_PURPOSE_NEGATIVE",
    "TELNET_PURPOSE_PROBE",
    "run_telnet_mission",
]
