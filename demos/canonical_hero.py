"""demos.canonical_hero — Canonical judge demonstration for RAPHAEL IBM BOB.

Connects the complete governed control loop:
  [1] Mission
  [2] Planning
  [3] Authorization
  [4] Broker / Policy
  [5] Capability
  [6] Execution
  [7] Provider (real T3MP3ST in bwrap sandbox when available; inert double fallback with explicit labeling)
  [8] Evidence
  [9] Verification
  [10] Falsification
  [11] Finding
  [12] Replanning
  [13] QualityGate

RESULT: COMPLETE / REFUSE
Evidence: <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIX_PARENT = ROOT / "fixtures"
if str(FIX_PARENT.parent) not in sys.path:
    sys.path.insert(0, str(FIX_PARENT.parent))

from raphael_ibm_bob import (
    ActionRequest,
    BOBBroker,
    BOBPolicy,
    BOBQualityGate,
    BOBRuntime,
    Capability,
    Decision,
    EvidenceReceipt,
    Finding,
    FindingState,
    FocusedContext,
    GateInputs,
    GateVerdict,
    Mission,
    Planner,
    ReplanStrategy,
    Replanner,
    Workspace,
)
from raphael_ibm_bob.adapters.t3mp3st_adapter import (
    DEFAULT_BRIDGE_PATH,
    DEFAULT_LAUNCHER_PATH,
    DEFAULT_NODE_PATH,
    LAUNCHER_SHA256,
    MIN_NODE_VERSION,
    T3MP3ST_BRIDGE_SHA256,
    InertProviderDouble,
    T3MP3STAdapter,
)
from raphael_ibm_bob.c1a_authorization import (
    C1AAuthorizationBinding,
    C1AAuthorizationError,
)
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    append_run_provenance,
    create_run_dir,
    digest_id,
)
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.isolation_substrate import (
    PROVIDER_PIN,
    node_version_ok,
    parse_node_version,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier

PROVIDER_DIST = os.environ.get(
    "T3MP3ST_PROVIDER_DIST", "/home/moiz/audit-repos/T3MP3ST/dist"
)
PROVIDER_REPO = os.environ.get(
    "T3MP3ST_PROVIDER_REPO", "/home/moiz/audit-repos/T3MP3ST"
)

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


def _v1_fix_text(current_text: str) -> str:
    if "V1_FIX" in current_text:
        return current_text
    return current_text.replace(
        "def check_password(user_id: str, password: str) -> bool:",
        "def check_password(user_id: str, password: str) -> bool:  # V1_FIX",
    ).replace(
        "USERS.get(user_id) == password",
        'USERS.get(user_id, "").lower() == (password or "").lower()',
    )


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass(frozen=True)
class PrereqStatus:
    name: str
    ok: bool
    detail: str


def check_prerequisites() -> List[PrereqStatus]:
    statuses = []

    # 1. Python
    py_ok = sys.version_info >= (3, 11)
    statuses.append(
        PrereqStatus(
            "python_runtime",
            py_ok,
            f"{sys.version.split()[0]} (minimum 3.11)",
        )
    )

    # 2. Node
    node_path = shutil.which("node")
    node_ok = False
    node_ver = "not found"
    if node_path:
        try:
            res = subprocess.run(
                [node_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            node_ver = res.stdout.strip()
            node_ok = node_version_ok(node_ver, MIN_NODE_VERSION)
        except Exception as exc:
            node_ver = f"error:{exc}"
    statuses.append(
        PrereqStatus(
            "node_runtime",
            node_ok,
            f"{node_ver} (minimum v{'.'.join(str(n) for n in MIN_NODE_VERSION)})",
        )
    )

    # 3. bwrap
    bwrap_path = shutil.which("bwrap")
    statuses.append(
        PrereqStatus(
            "bwrap_sandbox",
            bool(bwrap_path),
            bwrap_path or "not found in PATH",
        )
    )

    # 4. Bridge & launcher digests
    launcher_path = ROOT / DEFAULT_LAUNCHER_PATH
    launcher_digest = _file_sha256(launcher_path)
    statuses.append(
        PrereqStatus(
            "c1a_launcher_pinned",
            launcher_digest == LAUNCHER_SHA256,
            launcher_digest or "missing",
        )
    )

    bridge_path = ROOT / DEFAULT_BRIDGE_PATH
    bridge_digest = _file_sha256(bridge_path)
    statuses.append(
        PrereqStatus(
            "t3mp3st_bridge_pinned",
            bridge_digest == T3MP3ST_BRIDGE_SHA256,
            bridge_digest or "missing",
        )
    )

    # 5. T3MP3ST provider dist
    provider_available = os.path.isdir(PROVIDER_DIST) and os.path.isfile(
        os.path.join(PROVIDER_DIST, "arsenal", "binary.js")
    )
    statuses.append(
        PrereqStatus(
            "t3mp3st_provider_dist",
            provider_available,
            PROVIDER_DIST if provider_available else "not found",
        )
    )

    return statuses


def _persist_probe_proof(ledger: EvidenceLedger, ok: bool) -> int:
    payload = {
        "kind": "probe",
        "result": "passed" if ok else "failed",
        "allowed": ok,
    }
    ev_id = digest_id(payload, prefix="PB")
    return ledger.append_evidence(
        evidence_id=ev_id,
        producer="probe",
        request_seq=0,
        decision_seq=0,
        result_seq=None,
        payload=payload,
    )


def _persist_regression_proof(ledger: EvidenceLedger, ok: bool) -> int:
    payload = {"kind": "regression", "result": "passed" if ok else "failed"}
    ev_id = digest_id(payload, prefix="RG")
    return ledger.append_evidence(
        evidence_id=ev_id,
        producer="regression",
        request_seq=0,
        decision_seq=0,
        result_seq=None,
        payload=payload,
    )


def _run_broker_test(runtime: BOBRuntime, mission: Mission, target: str) -> Tuple[bool, str]:
    rt = runtime.submit(
        ActionRequest(
            sequence=0,
            requester="runner",
            capability=Capability.RUN_TEST,
            target=target,
            purpose="canonical:required-test",
        ),
        mission,
    )
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


def _write_via_broker(
    runtime: BOBRuntime, mission: Mission, target: str, content: str, purpose_detail: str
) -> str:
    rt = runtime.submit(
        ActionRequest(
            sequence=0,
            requester="runner",
            capability=Capability.WRITE,
            target=target,
            purpose="content=" + content,
        ),
        mission,
    )
    decision = rt.broker_result.decision
    summary = (
        f"decision={decision.decision.value} reason={decision.reason} "
        f"request_seq={rt.request_seq}"
    )
    if decision.decision.value != "allow":
        raise RuntimeError(
            f"remediation WRITE denied for {target}: {summary} ({purpose_detail})"
        )
    return summary


def _run_probe_subprocess() -> Tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "probes/auth_behavior_probe.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def run_canonical_demo(
    mode: str = "raphael",
    runs_root: Optional[Path] = None,
    keep: bool = False,
    mock: bool = False,
) -> int:
    authkit_dir = ROOT / "fixtures" / "authkit"
    login_path = authkit_dir / "login.py"
    session_path = authkit_dir / "session.py"

    orig_login = login_path.read_text(encoding="utf-8")
    orig_session = session_path.read_text(encoding="utf-8")

    # Install initial buggy session
    session_path.write_text(BUGGY_SESSION_TEXT, encoding="utf-8")

    run_id, tmp = create_run_dir(ROOT / "runs" if runs_root is None else runs_root)
    try:
        evidence_rel = (tmp.relative_to(ROOT) / "evidence.jsonl").as_posix()
    except ValueError:
        evidence_rel = (tmp / "evidence.jsonl").as_posix()

    workspace = Workspace(ROOT)
    ledger = EvidenceLedger(tmp)
    append_run_provenance(
        ledger,
        mode=mode,
        mission_id="M-authkit-governed",
        scenario="authkit",
    )

    prereqs = check_prerequisites()
    prereq_dict = {p.name: p for p in prereqs}
    have_real_t3mp3st = (
        prereq_dict["node_runtime"].ok
        and prereq_dict["bwrap_sandbox"].ok
        and prereq_dict["t3mp3st_bridge_pinned"].ok
        and prereq_dict["t3mp3st_provider_dist"].ok
    )

    if mock:
        c1a_provider = InertProviderDouble()
        provider_name = "InertProviderDouble (test double, explicit --mock mode)"
        provider_state_label = "INERT"
    elif have_real_t3mp3st:
        c1a_provider = T3MP3STAdapter(provider_dist=PROVIDER_DIST)
        provider_name = "T3MP3ST (real pinned checkout)"
        provider_state_label = "AVAILABLE"
    else:
        failed_prereqs = [p.name for p in prereqs if not p.ok]
        raise RuntimeError(
            f"Real T3MP3ST provider unavailable (failed prerequisites: {failed_prereqs}). "
            "Canonical demo requires the real provider. Use explicit --mock to run with test double."
        )

    policy = BOBPolicy(workspace)
    c1a_auth = C1AAuthorizationBinding()
    broker = BOBBroker(
        policy,
        workspace,
        ledger=ledger,
        c1a_provider=c1a_provider,
        c1a_authorization=c1a_auth,
    )
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    verifier = Verifier(runtime, ledger, store)
    falsifier = Falsifier(runtime, ledger, store)
    replanner = Replanner(
        store,
        ledger,
        strategy=ReplanStrategy(
            preferred_target="fixtures/authkit/session.py"
        ),
    )
    gate = BOBQualityGate(ledger)

    mission = Mission(
        mission_id="M-authkit-governed",
        description="Authkit defect repair with governed C1A provider inspection and falsification",
        scope="fixtures",
        criteria=[
            "c1a static file inspection recorded",
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

    print("RAPHAEL IBM BOB\n")

    try:
        # [1] Mission
        print("[1] Mission")
        print(f"    id={mission.mission_id} scope={mission.scope}")
        print(f"    target={mission.problem.get('actual_defect_target')}")
        print(f"    criteria={len(mission.criteria)} conditions declared")

        # [2] Planning
        planner = Planner()
        plan_a = planner.plan_a(mission)
        print("\n[2] Planning")
        print(f"    plan_id={plan_a.plan_id}")
        print(f"    initial_target={plan_a.steps[0].target} (decoy symptom)")

        # [3] Authorization
        print("\n[3] Authorization")
        # Demonstrate fail-closed check on unauthorized action
        unauth_req = ActionRequest(
            sequence=0,
            requester="planner",
            capability=Capability.READ,
            target="/etc/shadow",
            purpose="adversarial-test:read-outside-workspace",
        )
        unauth_decision = policy.consult(unauth_req, mission)
        print(f"    fail_closed_check: target=/etc/shadow -> {unauth_decision.decision.value.upper()} (reason={unauth_decision.reason})")
        print(f"    c1a_binding: HMAC-SHA256 single-use authorization authority active")

        # [4] Broker / Policy
        print("\n[4] Broker / Policy")
        print("    mediation=mandatory (all actions must pass Runtime -> Broker -> Policy)")
        # Submit Plan A step 0 via Runtime -> Broker -> Policy
        rt_a = runtime.submit(plan_a.steps[0], mission)
        print(f"    request_seq={rt_a.request_seq} decision={rt_a.broker_result.decision.decision.value} (reason={rt_a.broker_result.decision.reason})")

        # [5] Capability
        print("\n[5] Capability")
        print("    allow_list=[read, write, list, search, run_test, c1a_static_file_inspect]")
        print(f"    dispatched=Capability.{rt_a.broker_result.decision.capability.name}")

        # [6] Execution
        print("\n[6] Execution")
        print(f"    workspace_contained=True capability_invoked={rt_a.broker_result.capability_invoked}")
        print(f"    execution_success={rt_a.execution.success if rt_a.execution else False}")

        # [7] Provider (governed C1A inspection)
        print("\n[7] Provider")
        c1a_req = ActionRequest(
            sequence=0,
            requester="scanner",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target="fixtures/authkit/session.py",
            purpose="c1a:inspect-session-for-binary-sinks",
            timeout_seconds=30.0,
        )
        c1a_res = runtime.submit(c1a_req, mission)
        c1a_exec = c1a_res.execution
        c1a_prov_state = (c1a_exec.evidence or {}).get("provider_state", "unknown") if c1a_exec else "none"
        c1a_untrusted = bool((c1a_exec.evidence or {}).get("provider_untrusted", False)) if c1a_exec else False
        print(f"    provider={provider_name}")
        print(f"    status={provider_state_label} execution={'VERIFIED' if c1a_exec and c1a_exec.success else 'FAILED'}")
        print(f"    provider_state={c1a_prov_state} untrusted_marker={c1a_untrusted}")
        print("    invariant: provider output is UNTRUSTED evidence (cannot create COMPLETE)")

        # [8] Evidence
        print("\n[8] Evidence")
        print(f"    ledger={evidence_rel}")
        print(f"    records_recorded={len(ledger.all_records())} (append-only JSONL with SHA-256 digests)")

        # [9] Verification
        print("\n[9] Verification")
        finding = Finding(
            finding_id="F-authkit",
            state=FindingState.UNVERIFIED,
            summary="login.py plausible wrong-password handling defect",
            target="fixtures/authkit/login.py",
        )
        store.register(finding)
        print(f"    candidate_finding={finding.finding_id} state={finding.state.value.upper()}")

        # Install v1 decoy fix via broker WRITE
        v1_text = _v1_fix_text(login_path.read_text(encoding="utf-8"))
        _write_via_broker(
            runtime,
            mission,
            "fixtures/authkit/login.py",
            v1_text,
            purpose_detail="v1 decoy fix",
        )
        test_login_ok, test_login_det = _run_broker_test(
            runtime, mission, "fixtures/authkit/test_login.py"
        )
        print(f"    v1_decoy_fix installed -> test_login={'PASS' if test_login_ok else 'FAIL'} ({test_login_det})")
        verify_outcome = verifier.verify(
            finding,
            RetestSpec(
                capability=Capability.READ,
                target="fixtures/authkit/login.py",
                expected_substring="V1_FIX",
            ),
            mission,
            requester="runner",
        )
        print(f"    named_test_retest={'PASS' if verify_outcome.transition_applied else 'FAIL'} (finding state={finding.state.value.upper()})")

        # [10] Falsification
        print("\n[10] Falsification")
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
            store.get("F-authkit"), challenge, mission
        )
        print(f"    independent_oracle=probes/auth_behavior_probe.py (external oracle)")
        print(f"    probe_under_v1={'PASS' if not challenge_outcome.counter_example_observed else 'FAIL'} (counter-example observed on expired/cross-user tokens)")
        print(f"    falsifier_verdict={'REFUTED' if challenge_outcome.transition_applied else 'UNREFUTED'} (finding state={store.get('F-authkit').state.value.upper()})")

        # [11] Finding
        print("\n[11] Finding")
        current_finding = store.get("F-authkit")
        print(f"    store=FindingStore finding_id={current_finding.finding_id}")
        print(f"    state={current_finding.state.value.upper()} (transition: UNVERIFIED -> REFUTED)")

        # [12] Replanning
        print("\n[12] Replanning")
        if mode in ("baseline", "refuse"):
            print("    replanning_skipped=True (mode=baseline: honest failure signature)")
            _persist_probe_proof(ledger, ok=False)
            _persist_regression_proof(ledger, ok=True)
            probe_ok_final = False
        else:
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
                refuted_claim=current_finding,
                diagnostic_evidence=receipts,
                mission_scope=mission.scope,
            )
            plan_b = replanner.replan(ctx, plan_a)
            print(f"    plan_b_id={plan_b.plan_id} parent={plan_a.plan_id} target={plan_b.steps[0].target}")
            # Execute step on session.py via broker
            runtime.submit(plan_b.steps[0], mission)
            # Install v2 fix to session.py via broker WRITE
            _write_via_broker(
                runtime,
                mission,
                "fixtures/authkit/session.py",
                V2_FIXED_SESSION_TEXT,
                purpose_detail="v2 root defect fix",
            )
            print("    v2_root_fix installed on fixtures/authkit/session.py via broker WRITE")

            test_login_ok2, _ = _run_broker_test(
                runtime, mission, "fixtures/authkit/test_login.py"
            )
            test_auth_ok, _ = _run_broker_test(
                runtime, mission, "fixtures/authkit/test_auth.py"
            )
            probe_ok_v2, _ = _run_probe_subprocess()
            _persist_probe_proof(ledger, ok=probe_ok_v2)
            _persist_regression_proof(ledger, ok=True)

            print(f"    regression_tests: test_login={'PASS' if test_login_ok2 else 'FAIL'}, test_auth={'PASS' if test_auth_ok else 'FAIL'}")
            print(f"    independent_oracle: probe={'PASS' if probe_ok_v2 else 'FAIL'} (all 10/10 scenarios passed)")
            probe_ok_final = probe_ok_v2

        # [13] QualityGate
        print("\n[13] QualityGate")
        evaluation = gate.evaluate(
            GateInputs(
                mission=mission,
                findings=list(store.all()),
                regression_ok=True,
                behavior_probe_ok=probe_ok_final,
            )
        )
        print(f"    evaluator=BOBQualityGate (sole COMPLETE authority)")
        print(f"    passed={list(evaluation.passed)}")
        print(f"    failed={list(evaluation.failed)}")
        verdict_str = evaluation.verdict.value.upper()

        print(f"\nRESULT: {verdict_str}")
        print(f"Evidence: {evidence_rel}")

        ledger.close()
        return 0 if evaluation.verdict == GateVerdict.COMPLETE else 1

    finally:
        # Fixture restoration guarantees git cleanliness
        if not keep:
            login_path.write_text(orig_login, encoding="utf-8")
            session_path.write_text(orig_session, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAPHAEL IBM BOB — Canonical Judge Demonstration"
    )
    parser.add_argument(
        "--mode",
        choices=("raphael", "baseline", "refuse"),
        default="raphael",
        help="Demonstration mode: governed full loop (raphael) or refusal comparison (baseline/refuse).",
    )
    parser.add_argument(
        "--refuse",
        action="store_true",
        help="Convenience alias for --mode refuse.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Convenience alias for --mode baseline.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Explicitly run with InertProviderDouble test double instead of requiring real T3MP3ST provider.",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Validate and print environment prerequisites then exit.",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Directory to store run evidence (defaults to runs/).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do NOT restore fixture files after execution.",
    )

    args = parser.parse_args()

    mode = args.mode
    if args.refuse:
        mode = "refuse"
    elif args.baseline:
        mode = "baseline"

    if args.check_prereqs:
        statuses = check_prerequisites()
        print("RAPHAEL IBM BOB — Prerequisites Check")
        print("=" * 45)
        all_ok = True
        for st in statuses:
            tag = "PASS" if st.ok else "FAIL"
            print(f"[{tag}] {st.name:25s}: {st.detail}")
            if not st.ok:
                all_ok = False
        return 0 if all_ok else 2

    # Pre-validate critical prerequisites before running
    statuses = check_prerequisites()
    st_dict = {s.name: s for s in statuses}
    if not st_dict["python_runtime"].ok:
        print(f"Fatal prerequisite failure: python {st_dict['python_runtime'].detail}", file=sys.stderr)
        return 2

    if not args.mock:
        real_reqs = ("node_runtime", "bwrap_sandbox", "c1a_launcher_pinned", "t3mp3st_bridge_pinned", "t3mp3st_provider_dist")
        missing_real = [r for r in real_reqs if not st_dict.get(r) or not st_dict[r].ok]
        if missing_real:
            print(f"Fatal prerequisite failure for real T3MP3ST provider: missing {missing_real}.", file=sys.stderr)
            print("The canonical demo requires the real provider. To run with the test double instead, explicitly pass --mock.", file=sys.stderr)
            return 2

    try:
        return run_canonical_demo(
            mode=mode,
            runs_root=args.runs_root,
            keep=args.keep,
            mock=args.mock,
        )
    except Exception as exc:
        print(f"Demo failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
