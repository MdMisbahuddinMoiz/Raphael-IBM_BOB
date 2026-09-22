"""raphael_ibm_bob.harness.network_run — deterministic HTB network mission.

Wires the existing D9 governed network capability into the NORMAL run
lifecycle (persisted `runs/<run_id>/harness.json`) and produces the REAL,
ledger-backed evidence the existing QualityGate conditions require:

    A  mission criterion      mission.criteria
    B  required-tests         a governed RUN_TEST (returncode 0 artifact)
    C  regression             a producer="regression" record causally tied to
                              that RUN_TEST + >=2 distinct ALLOWed caps
    D  independent probe      a SEPARATE governed behavior observation
                              (producer="probe", allowed=True)
    E  scope                  TargetProfile scope (Policy + gate share it)
    F  evidence               request/decision/result/evidence chain
    G  finding state          flag Finding verified (NetworkVerifier), not
                              refuted without replan

Nothing here fabricates evidence: B comes from an executed RUN_TEST, C is
derived from that execution's ledger sequences, and D comes from its own
independent governed request. The request is built from the mission-bound
`TargetProfile` only; `candidate_target` is never consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    create_run_dir,
    digest_id,
)
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.harness.session import RaphaelSession, save_session
from raphael_ibm_bob.network_runtime import (
    DEFAULT_TIMEOUT_SECONDS,
    NetworkVerifier,
    flag_sha256,
    get_network_mediator,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import TargetProfile, get_target_store
from raphael_ibm_bob.workspace import Workspace

NETWORK_METHOD = "GET"
NETWORK_PURPOSE = "network-http-request method=GET"
DEFAULT_REQUEST_PATH = "/"
#: Deterministic negative-control path for falsification (a different path on
#: the SAME authorized host must not return the flag).
DEFAULT_DECOY_PATH = "/raphael-decoy"
#: Independent behavior-probe path. Must differ from the request path: the
#: probe is a SEPARATE governed observation of the target's behavior (it
#: serves content), not the flag fetch repeated.
DEFAULT_PROBE_PATH = "/"
DEFAULT_RUN_TEST_TIMEOUT = 30.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_path(value: Any, default: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        return default
    path = value.strip()
    return path if path.startswith("/") else "/" + path


def _build_url(profile: TargetProfile, path: str) -> str:
    scheme = profile.allowed_protocols[0]
    port = profile.allowed_ports[0]
    return f"{scheme}://{profile.locator}:{port}{path}"


def _append(ledger: EvidenceLedger, *, producer: str, prefix: str,
            payload: dict, request_seq: int, decision_seq: int,
            result_seq: Optional[int]) -> str:
    evidence_id = digest_id(payload, prefix=prefix)
    ledger.append_evidence(
        evidence_id=evidence_id, producer=producer, request_seq=request_seq,
        decision_seq=decision_seq, result_seq=result_seq, payload=payload)
    return evidence_id


@dataclass
class NetworkRunResult:
    """Authoritative run record plus terminal-mission details."""
    run: RaphaelRun
    terminal: str
    gate_verdict: Optional[str]
    verified: bool
    flag: Optional[str] = None
    terminal_reason: str = ""


def run_network_mission(session: RaphaelSession, mission: Mission,
                        workspace_root: Path, *, runs_root: Path,
                        sessions_root: Optional[Path] = None,
                        target_store: Any = None,
                        mediator: Any = None,
                        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                        requester: str = "operator") -> NetworkRunResult:
    """Drive one governed network mission to a terminal state.

    A missing/mismatched mission-bound TargetProfile is a REFUSE, persisted
    as a normal run (never a silently-constructed target).
    """
    run_id, run_dir = create_run_dir(runs_root)
    run = RaphaelRun(
        run_id=run_id, session_id=session.session_id, mission=mission,
        workspace_root=str(workspace_root), state="running",
        ledger_dir=str(run_dir))
    session.add_run(run_id)
    save_run(run)

    store = target_store if target_store is not None else get_target_store()
    mediator = mediator if mediator is not None else get_network_mediator()
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

        if profile is None:
            reason = "no-authorized-target-for-mission"
        else:
            policy = BOBPolicy(workspace, target_store=store)
            broker = BOBBroker(policy, workspace, ledger=ledger,
                               network_mediator=mediator, target_store=store)
            runtime = BOBRuntime(broker)

            request_path = _normalize_path(
                (mission.problem or {}).get("request_path"),
                DEFAULT_REQUEST_PATH)
            url = _build_url(profile, request_path)

            # --- 1. governed flag observation -> Finding -> verify -> falsify ---
            runtime_result = runtime.submit(ActionRequest(
                sequence=0, requester=requester,
                capability=Capability.NETWORK_HTTP_REQUEST, target=url,
                purpose=NETWORK_PURPOSE, timeout_seconds=timeout_seconds),
                mission)
            execution = runtime_result.execution
            network = ((execution.evidence.get("network_result")
                        if execution else None) or {})
            invocation = network.get("invocation_id")
            observed = network.get("flag")

            if execution is not None and execution.success and observed:
                flag = observed
                finding = Finding(
                    finding_id=f"F-{run_id[-6:]}-net",
                    state=FindingState.UNVERIFIED,
                    summary=f"htb-flag:{flag_sha256(observed)[:12]}",
                    target=url, mission_id=mission.mission_id)
                findings.register(finding)
                verifier = NetworkVerifier(
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
                    decoy_path = _normalize_path(
                        (mission.problem or {}).get("decoy_path"),
                        DEFAULT_DECOY_PATH)
                    decoy_url = _build_url(profile, decoy_path)
                    Falsifier(runtime, ledger, findings).challenge(
                        findings.get(finding.finding_id),
                        ChallengeSpec(
                            capability=Capability.NETWORK_HTTP_REQUEST,
                            target=decoy_url, purpose=NETWORK_PURPOSE,
                            predicate=lambda p: bool(
                                (p.get("network_result") or {}).get("flag"))),
                        mission)

            # --- 2. condition D: independent governed behavior probe ---
            # A SEPARATE governed observation (its own invocation) at a
            # distinct documented path: the target must actually serve
            # content. Never claim a probe from the flag fetch itself.
            probe_path = _normalize_path(
                (mission.problem or {}).get("probe_path"), DEFAULT_PROBE_PATH)
            if probe_path != request_path:
                probe_url = _build_url(profile, probe_path)
                probe_rt = runtime.submit(ActionRequest(
                    sequence=0, requester="network-probe",
                    capability=Capability.NETWORK_HTTP_REQUEST,
                    target=probe_url, purpose=NETWORK_PURPOSE,
                    timeout_seconds=timeout_seconds), mission)
                p_exec = probe_rt.execution
                p_net = ((p_exec.evidence.get("network_result")
                          if p_exec else None) or {})
                status = p_net.get("status_code")
                nbytes = p_net.get("response_bytes") or 0
                # Invariant (independent of flag extraction): the declared
                # authorized endpoint is reachable THROUGH the governed
                # path and serves a well-formed, non-empty response.
                probe_ok = bool(
                    p_exec is not None and p_exec.success
                    and isinstance(status, int) and 200 <= status < 400
                    and nbytes > 0)
                if probe_ok:
                    payload = {
                        "kind": "probe",
                        "probe_id": f"NETPROBE-{run_id[-6:]}",
                        "mission_id": mission.mission_id,
                        "result": "passed", "allowed": True,
                        "invariant":
                            "authorized-http-endpoint-reachable-and-serving",
                        "endpoint": probe_url, "path": probe_path,
                        "status_code": status, "response_bytes": nbytes,
                        "response_sha256": p_net.get("response_sha256"),
                        "invocation_id": p_net.get("invocation_id"),
                        "source": "network-independent-behavior-probe",
                        "request_seq": probe_rt.request_seq,
                        "decision_seq": probe_rt.decision_seq,
                        "result_seq": probe_rt.result_seq,
                    }
                    _append(ledger, producer="probe", prefix="PB",
                            payload=payload,
                            request_seq=probe_rt.request_seq,
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
                    sequence=0, requester="network-run",
                    capability=Capability.RUN_TEST, target=test_target,
                    purpose="network-run:required-test",
                    timeout_seconds=DEFAULT_RUN_TEST_TIMEOUT), mission)
                # Mirror harness.model_run.passing_run_tests: a RUN_TEST
                # only counts when the artifact reports success AND
                # returncode 0 — a failing test is not a regression pass.
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
                    "source": "network-run:required-test"},
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
        verified=verified, flag=flag,
        terminal_reason=(run.failure_reason or ""))


__all__ = [
    "DEFAULT_DECOY_PATH",
    "DEFAULT_PROBE_PATH",
    "DEFAULT_REQUEST_PATH",
    "NETWORK_METHOD",
    "NetworkRunResult",
    "run_network_mission",
]
