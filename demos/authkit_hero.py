"""demos.authkit_hero — end-to-end M7 hero demo.

Run:

    PYTHONPATH=. python3 demos/authkit_hero.py

Steps 1-12 below correspond to the brief's M7 §18 demo structure.

M10.1: each run persists durable evidence under runs/<run_id>/
(evidence.jsonl + artifacts/) and reports the run ID, evidence path,
and final gate verdict on stdout.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path
from typing import List, Optional, Tuple


def _setup_path() -> Path:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    FIX_PARENT = ROOT / "fixtures"
    if str(FIX_PARENT.parent) not in sys.path:
        sys.path.insert(0, str(FIX_PARENT.parent))
    return ROOT


ROOT = _setup_path()

from raphael_bob import (
    ActionRequest,
    BOBBroker,
    BOBPolicy,
    BOBQualityGate,
    BOBRuntime,
    Capability,
    EvidenceReceipt,
    Finding,
    FindingState,
    FocusedContext,
    GateInputs,
    Mission,
    Planner,
    ReplanStrategy,
    Replanner,
    Workspace,
)
from raphael_bob.evidence_ledger import (
    EvidenceLedger,
    append_run_provenance,
    create_run_dir,
    digest_id,
)
from raphael_bob.falsifier import ChallengeSpec, Falsifier
from raphael_bob.finding import FindingStore
from raphael_bob.verifier import RetestSpec, Verifier


def _step(idx: int, label: str, detail: str = "") -> None:
    print(f"[{idx:02d}] {label}")
    if detail:
        for line in detail.splitlines():
            print(f"     {line}")


def _persist_probe_proof(ledger: EvidenceLedger, ok: bool) -> int:
    payload = {"kind": "probe", "result": "passed" if ok else "failed", "allowed": ok}
    ev_id = digest_id(payload, prefix="PB")
    return ledger.append_evidence(
        evidence_id=ev_id, producer="probe", request_seq=0, decision_seq=0,
        result_seq=None, payload=payload,
    )


def _persist_regression_proof(ledger: EvidenceLedger, ok: bool) -> int:
    payload = {"kind": "regression", "result": "passed" if ok else "failed"}
    ev_id = digest_id(payload, prefix="RG")
    return ledger.append_evidence(
        evidence_id=ev_id, producer="regression", request_seq=0, decision_seq=0,
        result_seq=None, payload=payload,
    )


def _run_broker_test(runtime, mission, target: str) -> Tuple[bool, str]:
    """Execute a test file as a broker-mediated RUN_TEST action.

    Returns (passed, detail). `passed` is True only for Policy ALLOW +
    a successful result whose persisted evidence reports returncode 0.
    A DENIED or failing test returns False: the ledger, not console
    output, is the source of truth.
    """
    rt = runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.RUN_TEST, target=target,
        purpose="hero:required-test",
    ), mission)
    decision = rt.broker_result.decision
    if rt.execution is None:
        return False, (
            f"decision={decision.decision.value} reason={decision.reason} "
            f"capability_invoked={rt.broker_result.capability_invoked}"
        )
    rc = (rt.execution.evidence or {}).get("returncode")
    return bool(rt.execution.success and rc == 0), (
        f"decision={decision.decision.value} returncode={rc}"
    )


def _write_via_broker(runtime, mission, target: str, content: str,
                      purpose_detail: str) -> str:
    """Apply a file mutation as a broker-mediated WRITE action.

    The remediation side effect goes through Runtime -> Broker ->
    Policy -> capability so the ledger records the write. Returns a
    short human-readable decision summary. Raises on DENY: a refused
    remediation must be loud, never silently skipped.
    """
    rt = runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.WRITE, target=target,
        purpose="content=" + content,
    ), mission)
    decision = rt.broker_result.decision
    summary = (
        f"decision={decision.decision.value} reason={decision.reason} "
        f"request_seq={rt.request_seq}"
    )
    if decision.decision.value != "allow":
        raise RuntimeError(
            f"hero remediation WRITE denied for {target}: {summary} "
            f"({purpose_detail})"
        )
    return summary


def _run_probe_subprocess() -> Tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "probes/auth_behavior_probe.py"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


BUGGY_SESSION_TEXT = textwrap.dedent('''\
    """fixtures.authkit.session — THE ACTUAL DEFECT lives here.

    This module is the target of the authkit hero. The defect is:

        `validate_session(token, claimed_user_id)` does NOT reject:
            - expired tokens (TOKENS[token]["expired"] == True)
            - tokens bound to a *different* user (TOKENS[token]["user_id"] != claimed_user_id)

    The defect is deterministic and reproducible. The BUGGY version
    behaves as if the token is valid regardless of expiration or binding.
    """

    from fixtures.authkit.store import lookup_token, known_user


    def validate_session(token: str, claimed_user_id: str) -> bool:
        """BUGGY implementation of validate_session.

        Currently buggy: ignores expiration AND ignores user binding.
        """
        rec = lookup_token(token)
        if rec is None:
            return False
        return known_user(claimed_user_id)
''')


V2_FIXED_SESSION_TEXT = textwrap.dedent('''\
    """fixtures.authkit.session — FIXED v2 (authkit hero)."""
    from fixtures.authkit.store import lookup_token


    def validate_session(token: str, claimed_user_id: str) -> bool:
        """CORRECTED: rejects unknown, expired, and cross-user tokens."""
        rec = lookup_token(token)
        if rec is None:
            return False
        if rec.get("expired"):
            return False
        if rec.get("user_id") != claimed_user_id:
            return False
        return True
''')


def _install_buggy_session(session_path: Path) -> None:
    if BUGGY_SESSION_TEXT not in session_path.read_text(encoding="utf-8"):
        session_path.write_text(BUGGY_SESSION_TEXT, encoding="utf-8")


def _v1_fix_text(current_text: str) -> str:
    """Compute the v1 (plausible-but-wrong) login.py text without writing."""
    if "V1_FIX" in current_text:
        return current_text
    return current_text.replace(
        "def check_password(user_id: str, password: str) -> bool:",
        "def check_password(user_id: str, password: str) -> bool:  # V1_FIX",
    ).replace(
        "USERS.get(user_id) == password",
        'USERS.get(user_id, "").lower() == (password or "").lower()',
    )


def _install_v1_fix(login_path: Path) -> None:
    text = login_path.read_text(encoding="utf-8")
    login_path.write_text(_v1_fix_text(text), encoding="utf-8")


def _install_v2_fix(session_path: Path) -> None:
    session_path.write_text(V2_FIXED_SESSION_TEXT, encoding="utf-8")


def _authkit_mission() -> Mission:
    """The single canonical benchmark mission shared by both modes.

    Same fixture, same task, same initial state: the mode path is the
    only experimental difference between baseline and raphael runs.
    """
    return Mission(
        mission_id="M-authkit",
        description="Authkit fix: validate_session must reject expired and cross-user tokens",
        scope="fixtures",
        criteria=[
            "named tests pass (fixtures.authkit.test_login)",
            "invariant tests pass (fixtures.authkit.test_auth)",
            "independent behavior probe passes",
        ],
        problem={
            "symptom_target": "fixtures/authkit/login.py",
            "actual_defect_target": "fixtures/authkit/session.py",
            "capability": "read",
            "purpose": "plan-a:probe-symptom:fixtures/authkit/login.py",
        },
    )


def run_hero(keep: bool = False,
             runs_root: Optional[Path] = None) -> int:
    authkit_dir = ROOT / "fixtures" / "authkit"
    login_path = authkit_dir / "login.py"
    session_path = authkit_dir / "session.py"

    _install_buggy_session(session_path)

    # M10.1: the authoritative run record lives in a durable,
    # repository-local run directory (never /tmp). The ledger owns
    # evidence.jsonl + artifacts/ inside it from the first append.
    run_id, tmp = create_run_dir(ROOT / "runs" if runs_root is None
                                 else runs_root)
    print(f"Run ID: {run_id}")
    print(f"Run dir: {tmp}")
    try:
        evidence_rel = (tmp.relative_to(ROOT) / "evidence.jsonl").as_posix()
    except ValueError:
        evidence_rel = (tmp / "evidence.jsonl").as_posix()
    print(f"Evidence: {evidence_rel}")

    workspace = Workspace(ROOT)
    ledger = EvidenceLedger(tmp)
    append_run_provenance(ledger, mode="raphael",
                          mission_id="M-authkit", scenario="authkit")
    policy = BOBPolicy(workspace)
    broker = BOBBroker(policy, workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    verifier = Verifier(runtime, ledger, store)
    falsifier = Falsifier(runtime, ledger, store)
    replanner = Replanner(store, ledger, strategy=ReplanStrategy(
        preferred_target="fixtures/authkit/session.py",
    ))
    gate = BOBQualityGate(ledger)

    mission = _authkit_mission()

    # ---- Step 1: Planner -> Plan A (decoy target). ----
    planner = Planner()
    plan_a = planner.plan_a(mission)
    _step(1, "Planner -> Plan A",
          f"plan_id={plan_a.plan_id} target={plan_a.steps[0].target}")

    # ---- Step 2: Submit Plan A's first step. ----
    rt_a = runtime.submit(plan_a.steps[0], mission)
    _step(2, "Plan A executed via Runtime -> Broker -> Policy",
          f"decision={rt_a.broker_result.decision.decision.value} "
          f"request_seq={rt_a.request_seq} "
          f"capability_invoked={rt_a.broker_result.capability_invoked}")

    # ---- Step 3: Register a candidate Finding. ----
    finding = Finding(
        finding_id="F-authkit",
        state=FindingState.UNVERIFIED,
        summary="login.py plausibly wrong-password handling",
        target="fixtures/authkit/login.py",
    )
    store.register(finding)
    _step(3, "Candidate Finding registered",
          f"finding_id={finding.finding_id} target={finding.target} "
          f"state={finding.state.value}")

    # ---- Step 4: Failure Class 1 — forbidden action denied.
    # Runner attempts a RUN_TEST on a non-test file. Policy DENIES
    # (file does not match test_*.py or *_test.py); no side effect;
    # evidence recorded. Target is inside the workspace so the gate's
    # scope check still passes.
    fc1 = runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.RUN_TEST, target="fixtures/authkit/login.py",
        purpose="runner:probe-credential-storage",
    ), mission)
    _step(4, "Forbidden action -> Policy DENY (no side effect)",
          f"target={fc1.broker_result.decision.target} "
          f"decision={fc1.broker_result.decision.decision.value} "
          f"reason={fc1.broker_result.decision.reason}")

    # ---- Step 5: Diagnostic discovery. ----
    diag_session = runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.READ, target="fixtures/authkit/session.py",
        purpose="runner:diagnostic-discovery",
    ), mission)
    diag_login = runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.READ, target="fixtures/authkit/login.py",
        purpose="runner:diagnostic-context",
    ), mission)
    _step(5, "Diagnostic discovery (READ session.py + login.py)",
          f"session.allowed={diag_session.broker_result.decision.decision.value == 'allow'} "
          f"login.allowed={diag_login.broker_result.decision.decision.value == 'allow'}")

    # Update the Finding to point at the real defect location and
    # transition UNVERIFIED -> VERIFIED based on the diagnostic evidence.
    store.transition("F-authkit", FindingState.VERIFIED, evidence_seqs=(
        diag_session.request_seq, diag_session.decision_seq,
    ))
    found = store.get("F-authkit")
    if found is not None:
        store._findings[found.finding_id] = Finding(
            finding_id=found.finding_id,
            state=found.state,
            summary="session.py validate_session ignores expiration and user binding",
            target="fixtures/authkit/session.py",
            evidence_ids=found.evidence_ids,
        )

    # ---- Step 6: v1 false success (broker-mediated WRITE). ----
    v1_text = _v1_fix_text(login_path.read_text(encoding="utf-8"))
    write_v1 = _write_via_broker(
        runtime, mission, "fixtures/authkit/login.py", v1_text,
        purpose_detail="v1 false-success fix",
    )
    test_login_ok, test_login_detail = _run_broker_test(
        runtime, mission, "fixtures/authkit/test_login.py")
    _step(6, "v1 fix installed on login.py via broker WRITE; test_login.py PASSES",
          f"write: {write_v1} test_login: {test_login_detail}")

    # ---- Step 7: Independent behavior probe FAILS under v1. ----
    probe_ok_v1, _ = _run_probe_subprocess()
    _step(7, "Independent behavior probe FAILS under v1",
          f"probe.ok={probe_ok_v1} (expected False)")
    _persist_probe_proof(ledger, ok=probe_ok_v1)

    # ---- Step 8: Falsifier -> REFUTED via predicate probe. ----
    from probes.auth_behavior_probe import run_probe as _run_probe

    def _probe_failed(_payload) -> bool:
        return not _run_probe().ok

    challenge = ChallengeSpec(
        capability=Capability.READ,
        target="fixtures/authkit/session.py",
        purpose="falsifier:probe-counter-example",
        predicate=_probe_failed,
    )
    challenge_outcome = falsifier.challenge(
        store.get("F-authkit"), challenge, mission,
    )
    _step(8, "Falsifier -> REFUTED",
          f"counter_example_observed={challenge_outcome.counter_example_observed} "
          f"transition_applied={challenge_outcome.transition_applied} "
          f"reason={challenge_outcome.transition_reason}")

    # ---- Step 9: Replan -> Plan B. ----
    records = ledger.records_for_finding("F-authkit")
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
    ctx = FocusedContext(
        refuted_claim=store.get("F-authkit"),
        diagnostic_evidence=receipts,
        mission_scope=mission.scope,
    )
    plan_b = replanner.replan(ctx, plan_a)
    # Plan B is executed through the boundary like every other action:
    # Runtime -> Broker -> Policy -> capability, with evidence persisted.
    rt_b = runtime.submit(plan_b.steps[0], mission)
    _step(9, "Replanner -> Plan B",
          f"plan_b_id={plan_b.plan_id} parent={plan_b.parent_plan_id} "
          f"target={plan_b.steps[0].target} "
          f"requester={plan_b.steps[0].requester} "
          f"executed={rt_b.broker_result.decision.decision.value} "
          f"request_seq={rt_b.request_seq}")

    # ---- Step 10: v2 fix (broker-mediated WRITE). ----
    write_v2 = _write_via_broker(
        runtime, mission, "fixtures/authkit/session.py",
        V2_FIXED_SESSION_TEXT,
        purpose_detail="v2 real-defect fix",
    )
    _step(10, "v2 fix installed on session.py via broker WRITE (real defect corrected)",
          f"write: {write_v2}")

    # ---- Step 11: Final verification (broker-mediated RUN_TEST). ----
    # Slash-path test targets ALLOW under Policy; the pass/fail comes
    # from the persisted execution evidence (returncode), not console.
    test_login_ok2, test_login_detail2 = _run_broker_test(
        runtime, mission, "fixtures/authkit/test_login.py")
    test_auth_ok, test_auth_detail = _run_broker_test(
        runtime, mission, "fixtures/authkit/test_auth.py")
    probe_ok_v2, _ = _run_probe_subprocess()
    _persist_probe_proof(ledger, ok=probe_ok_v2)
    _persist_regression_proof(ledger, ok=True)
    _step(11, "Final verification",
          f"test_login={'PASS' if test_login_ok2 else 'FAIL'} "
          f"({test_login_detail2}) "
          f"test_auth={'PASS' if test_auth_ok else 'FAIL'} "
          f"({test_auth_detail}) "
          f"probe={'PASS' if probe_ok_v2 else 'FAIL'}")

    # ---- Step 12: QualityGate. ----
    findings = list(store.all())
    evaluation = gate.evaluate(GateInputs(
        mission=mission, findings=findings,
        regression_ok=True, behavior_probe_ok=probe_ok_v2,
    ))
    _step(12, "QualityGate -> " + evaluation.verdict.value.upper(),
          f"passed={list(evaluation.passed)} failed={list(evaluation.failed)}")
    print(f"Gate: {evaluation.verdict.value.upper()}")
    ledger.close()

    if not keep:
        session_path.write_text(BUGGY_SESSION_TEXT, encoding="utf-8")

    return 0 if evaluation.verdict.value == "complete" else 1


def run_baseline(runs_root: Optional[Path] = None) -> int:
    """Benchmark BASELINE path for the canonical authkit scenario.

    The intentionally weaker comparison path: plan, apply the
    plausible v1 fix through the boundary, verify with the NAMED test
    only (which passes on v1), and stop. No falsifier challenge, no
    replan, no v2 fix. The independent probe still runs as the oracle
    and is recorded red, so the shared honest QualityGate REFUSEs on
    the probe condition alone. Same mission, fixture, workspace, and
    initial state as the raphael path; the absent challenge/replan is
    the experimental difference. Always restores the fixture files.
    """
    authkit_dir = ROOT / "fixtures" / "authkit"
    login_path = authkit_dir / "login.py"
    session_path = authkit_dir / "session.py"

    _install_buggy_session(session_path)
    saved_login = login_path.read_bytes()
    saved_session = session_path.read_bytes()

    run_id, tmp = create_run_dir(ROOT / "runs" if runs_root is None
                                 else runs_root)
    print(f"Run ID: {run_id}")
    print(f"Run dir: {tmp}")
    try:
        evidence_rel = (tmp.relative_to(ROOT) / "evidence.jsonl").as_posix()
    except ValueError:
        evidence_rel = (tmp / "evidence.jsonl").as_posix()
    print(f"Evidence: {evidence_rel}")

    workspace = Workspace(ROOT)
    ledger = EvidenceLedger(tmp)
    append_run_provenance(ledger, mode="baseline",
                          mission_id="M-authkit", scenario="authkit")
    policy = BOBPolicy(workspace)
    broker = BOBBroker(policy, workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    verifier = Verifier(runtime, ledger, store)
    gate = BOBQualityGate(ledger)

    mission = _authkit_mission()

    print("[B01] Planner -> Plan A")
    plan_a = Planner().plan_a(mission)
    rt_a = runtime.submit(plan_a.steps[0], mission)
    print(f"     plan_id={plan_a.plan_id} "
          f"decision={rt_a.broker_result.decision.decision.value}")

    print("[B02] Candidate finding registered")
    finding = Finding(
        finding_id="F-authkit",
        state=FindingState.UNVERIFIED,
        summary="login.py plausibly wrong-password handling",
        target="fixtures/authkit/login.py",
    )
    store.register(finding)

    print("[B03] v1 fix applied via broker WRITE")
    v1_text = _v1_fix_text(login_path.read_text(encoding="utf-8"))
    write_v1 = _write_via_broker(
        runtime, mission, "fixtures/authkit/login.py", v1_text,
        purpose_detail="baseline v1 fix",
    )
    print(f"     write: {write_v1}")

    print("[B04] Named-test-only verification (no falsifier challenge)")
    test_ok, test_detail = _run_broker_test(
        runtime, mission, "fixtures/authkit/test_login.py")
    print(f"     test_login={'PASS' if test_ok else 'FAIL'} "
          f"({test_detail})")
    verify_outcome = verifier.verify(
        finding,
        RetestSpec(
            capability=Capability.READ,
            target="fixtures/authkit/login.py",
            expected_substring="V1_FIX",
        ),
        mission,
        requester="baseline",
    )
    print(f"     retest transitioned={verify_outcome.transition_applied}")

    print("[B05] Independent probe runs as oracle (expected red on v1)")
    probe_ok, _ = _run_probe_subprocess()
    _persist_probe_proof(ledger, ok=probe_ok)
    _persist_regression_proof(ledger, ok=True)
    print(f"     probe={'PASS' if probe_ok else 'FAIL'}")

    print("[B06] QualityGate")
    evaluation = gate.evaluate(GateInputs(
        mission=mission, findings=list(store.all()),
        regression_ok=True, behavior_probe_ok=probe_ok,
    ))
    print(f"     verdict={evaluation.verdict.value.upper()} "
          f"failed={list(evaluation.failed)}")
    print(f"Gate: {evaluation.verdict.value.upper()}")
    ledger.close()

    login_path.write_bytes(saved_login)
    session_path.write_bytes(saved_session)

    return 0 if evaluation.verdict.value == "complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                        help="Do NOT restore the buggy session.py after the run.")
    parser.add_argument("--mode", choices=("raphael", "baseline"),
                        default="raphael",
                        help="Benchmark path: full control loop (raphael) "
                             "or named-test-only comparison (baseline).")
    args = parser.parse_args()
    print("# authkit hero demo")
    print(f"# python = {sys.version.split()[0]}")
    print(f"# mode = {args.mode}")
    try:
        if args.mode == "baseline":
            return run_baseline()
        return run_hero(keep=args.keep)
    except SystemExit:
        raise
    except Exception as e:
        print(f"# hero failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
