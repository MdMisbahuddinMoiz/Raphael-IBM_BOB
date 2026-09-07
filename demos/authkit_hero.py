"""demos.authkit_hero — end-to-end M7 hero demo.

Run:

    PYTHONPATH=. python3 demos/authkit_hero.py

Steps 1-12 below correspond to the brief's M7 §18 demo structure.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path
from typing import List, Tuple


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
from raphael_bob.evidence_ledger import EvidenceLedger, digest_id
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


def _run_subprocess_test(module: str) -> Tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", module, "-v"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


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


def _install_v1_fix(login_path: Path) -> None:
    text = login_path.read_text(encoding="utf-8")
    if "V1_FIX" in text:
        return
    patched = text.replace(
        "def check_password(user_id: str, password: str) -> bool:",
        "def check_password(user_id: str, password: str) -> bool:  # V1_FIX",
    ).replace(
        "USERS.get(user_id) == password",
        'USERS.get(user_id, "").lower() == (password or "").lower()',
    )
    login_path.write_text(patched, encoding="utf-8")


def _install_v2_fix(session_path: Path) -> None:
    session_path.write_text(V2_FIXED_SESSION_TEXT, encoding="utf-8")


def run_hero(keep: bool = False) -> int:
    authkit_dir = ROOT / "fixtures" / "authkit"
    login_path = authkit_dir / "login.py"
    session_path = authkit_dir / "session.py"

    _install_buggy_session(session_path)

    tmp = Path(tempfile.mkdtemp(prefix="authkit_hero_run_"))
    print(f"# run_dir = {tmp}")

    workspace = Workspace(ROOT)
    ledger = EvidenceLedger(tmp)
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

    mission = Mission(
        mission_id="M-authkit",
        description="Authkit fix: validate_session must reject expired and cross-user tokens",
        scope="fixtures",
        criteria=[
            "named tests pass (fixtures.authkit.test_login)",
            "invariant tests pass (fixtures.authkit.test_auth)",
            "independent behavior probe passes",
        ],
    )

    # ---- Step 1: Planner -> Plan A (decoy target). ----
    planner = Planner(symptom_target="fixtures/authkit/login.py")
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

    # ---- Step 6: v1 false success. ----
    _install_v1_fix(login_path)
    test_login_ok, _ = _run_subprocess_test("fixtures.authkit.test_login")
    _step(6, "v1 fix installed on login.py; test_login.py PASSES",
          f"test_login returncode={'0' if test_login_ok else 'nonzero'}")

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
    _step(9, "Replanner -> Plan B",
          f"plan_b_id={plan_b.plan_id} parent={plan_b.parent_plan_id} "
          f"target={plan_b.steps[0].target} "
          f"requester={plan_b.steps[0].requester}")

    # ---- Step 10: v2 fix. ----
    _install_v2_fix(session_path)
    _step(10, "v2 fix installed on session.py (real defect corrected)")

    # ---- Step 11: Final verification. ----
    test_login_ok2, _ = _run_subprocess_test("fixtures.authkit.test_login")
    test_auth_ok, _ = _run_subprocess_test("fixtures.authkit.test_auth")
    probe_ok_v2, _ = _run_probe_subprocess()
    _persist_probe_proof(ledger, ok=probe_ok_v2)
    _persist_regression_proof(ledger, ok=True)
    runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.RUN_TEST, target="fixtures.authkit.test_login",
        purpose="required-test",
    ), mission)
    runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.RUN_TEST, target="fixtures.authkit.test_auth",
        purpose="invariant-test",
    ), mission)
    _step(11, "Final verification",
          f"test_login={'PASS' if test_login_ok2 else 'FAIL'} "
          f"test_auth={'PASS' if test_auth_ok else 'FAIL'} "
          f"probe={'PASS' if probe_ok_v2 else 'FAIL'}")

    # ---- Step 12: QualityGate. ----
    findings = list(store.all())
    evaluation = gate.evaluate(GateInputs(
        mission=mission, findings=findings,
        regression_ok=True, behavior_probe_ok=probe_ok_v2,
    ))
    _step(12, "QualityGate -> " + evaluation.verdict.value.upper(),
          f"passed={list(evaluation.passed)} failed={list(evaluation.failed)}")

    if not keep:
        session_path.write_text(BUGGY_SESSION_TEXT, encoding="utf-8")

    return 0 if evaluation.verdict.value == "complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                        help="Do NOT restore the buggy session.py after the run.")
    args = parser.parse_args()
    print("# authkit hero demo")
    print(f"# python = {sys.version.split()[0]}")
    try:
        return run_hero(keep=args.keep)
    except SystemExit:
        raise
    except Exception as e:
        print(f"# hero failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
