"""demos.live_authkit_hero — live model-driven authkit hero (M12).

Judge-facing demonstration of the complete governed loop driven by a
REAL model over the existing RAPHAEL core:

    Mission -> model proposal (SkillRegistry-validated)
      -> ActionRequest -> Runtime -> Broker -> Policy -> Execution
      -> Evidence -> Finding -> Verification -> Falsification
      -> independent behavior probe -> QualityGate -> COMPLETE/REFUSE

Run:

    RAPHAEL_MODEL_ENDPOINT=https://opencode.ai/zen/go/v1 \
    RAPHAEL_MODEL_NAME=deepseek-v4.1-flash \
    RAPHAEL_MODEL_API_KEY=<key> \
    PYTHONPATH=. python3 demos/live_authkit_hero.py

The credential is read from the environment ONLY — never hardcoded,
logged, persisted, or committed. If the model configuration is absent
the script exits 2 with a clear message; it never fabricates a run.
The deterministic fallback is `demos/authkit_hero.py`.

The model only PROPOSES. Every proposed action is validated against
the skill registry and then submitted through the existing
Runtime/Broker/Policy boundary — the model cannot execute, authorize,
or declare completion itself. This driver contains no governance
logic of its own; it coordinates model turns around the core.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _setup_path() -> Path:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return ROOT


ROOT = _setup_path()

from raphael_ibm_bob import (  # noqa: E402
    Capability,
    Finding,
    FindingState,
    Mission,
    Workspace,
)
from raphael_ibm_bob.broker import BOBBroker  # noqa: E402
from raphael_ibm_bob.evidence_ledger import (  # noqa: E402
    EvidenceLedger,
    create_run_dir,
    digest_id,
)
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier  # noqa: E402
from raphael_ibm_bob.finding import FindingStore  # noqa: E402
from raphael_ibm_bob.harness.loop import excerpt_output  # noqa: E402
from raphael_ibm_bob.harness.model import ModelContext  # noqa: E402
from raphael_ibm_bob.harness.providers.openai_compat import (  # noqa: E402
    DoneSignal,
    OpenAICompatAdapter,
    ProviderConfigError,
    ProviderError,
    StructuredProposalError,
    config_from_env,
)
from raphael_ibm_bob.policy import BOBPolicy  # noqa: E402
from raphael_ibm_bob.quality_gate import (  # noqa: E402
    BOBQualityGate,
    GateInputs,
)
from raphael_ibm_bob.runtime import BOBRuntime  # noqa: E402
from raphael_ibm_bob.skills import (  # noqa: E402
    default_registry,
    register_default_skills,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier  # noqa: E402

AUTHKIT = ROOT / "fixtures" / "authkit"
MAX_TURNS = 14
HISTORY_WINDOW = 5
WORKSPACE_FILES = tuple(sorted(
    f"fixtures/authkit/{p.name}" for p in AUTHKIT.iterdir()
    if p.suffix == ".py"))


def _snapshot() -> Dict[str, bytes]:
    return {p.name: p.read_bytes() for p in AUTHKIT.iterdir()
            if p.is_file()}


def _restore(snap: Dict[str, bytes]) -> None:
    for name, data in snap.items():
        (AUTHKIT / name).write_bytes(data)


def _run_probe() -> Tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "probes/auth_behavior_probe.py"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _persist(ledger: EvidenceLedger, kind: str, ok: bool) -> None:
    if kind == "probe":
        payload = {"kind": "probe",
                   "result": "passed" if ok else "failed",
                   "allowed": ok}
        prefix = "PB"
    else:
        payload = {"kind": "regression",
                   "result": "passed" if ok else "failed"}
        prefix = "RG"
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix=prefix),
        producer=kind, request_seq=0, decision_seq=0,
        result_seq=None, payload=payload)


def _passing_run_tests(ledger: EvidenceLedger) -> bool:
    """True iff some RUN_TEST executed with artifact returncode 0."""
    records = ledger.all_records()
    run_test_seqs = {
        rec.get("seq") for rec in records
        if rec.get("kind") == "request"
        and rec.get("capability") == "run_test"
    }
    for rec in records:
        if rec.get("kind") != "result":
            continue
        if rec.get("request_seq") not in run_test_seqs:
            continue
        ref = rec.get("artifact_ref", "")
        try:
            data = json.loads(Path(ref).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("success") is True and \
                (data.get("evidence") or {}).get("returncode") == 0:
            return True
    return False


def _authkit_mission() -> Mission:
    return Mission(
        mission_id="M-authkit-live",
        description=("Work this mission to completion: investigate the "
                     "authkit session defect, verify behavior with the "
                     "named tests, implement the fix, re-run tests and "
                     "the probe until green, then declare done."),
        scope="fixtures",
        criteria=[
            "named tests pass (fixtures.authkit.test_login)",
            "invariant tests pass (fixtures.authkit.test_auth)",
            "independent behavior probe passes",
        ],
        problem={
            "symptom_target": "fixtures/authkit/login.py",
            "capability": "read",
            "purpose": "plan-a:probe-symptom",
        },
    )


def run_live_hero(max_turns: int = MAX_TURNS) -> int:
    """Drive one live authkit mission; returns process exit code."""
    try:
        config = config_from_env()
    except ProviderConfigError as exc:
        print(f"# live hero not configured: {exc}")
        print("# set RAPHAEL_MODEL_ENDPOINT / RAPHAEL_MODEL_NAME "
              "(and RAPHAEL_MODEL_API_KEY if required)")
        print("# deterministic fallback: PYTHONPATH=. python3 "
              "demos/authkit_hero.py")
        return 2

    snap = _snapshot()
    started = time.time()
    try:
        return _drive(config, max_turns, started)
    finally:
        _restore(snap)


def _drive(config, max_turns: int, started: float) -> int:
    registry = register_default_skills(default_registry())
    adapter = OpenAICompatAdapter(config, registry)
    mission = _authkit_mission()

    run_id, run_dir = create_run_dir(ROOT / "runs")
    print("# live authkit hero")
    print(f"# provider = {config.endpoint}")
    print(f"# model = {config.model}")
    print(f"Run ID: {run_id}")
    print(f"Run dir: {run_dir}")

    workspace = Workspace(ROOT)
    ledger = EvidenceLedger(run_dir)
    policy = BOBPolicy(workspace)
    broker = BOBBroker(policy, workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    verifier = Verifier(runtime, ledger, store)
    falsifier = Falsifier(runtime, ledger, store)
    gate = BOBQualityGate(ledger)

    transcript: Dict[str, object] = {
        "run_id": run_id,
        "model": config.model,
        "endpoint": config.endpoint,
        "turns": [],
        "events": [],
    }
    turn_log: List[dict] = []
    current_finding_id: Optional[str] = None
    terminal: Optional[str] = None

    for index in range(max_turns):
        context = ModelContext(
            mission=mission,
            findings=list(store.all()),
            workspace_root=str(ROOT),
            evidence_count=len(ledger.all_records()),
            workspace_files=WORKSPACE_FILES,
            recent_turns=tuple(turn_log[-HISTORY_WINDOW:]),
        )
        try:
            request = adapter.propose(context)
        except DoneSignal:
            terminal = "done"
            print(f"[{index:02d}] model declared done")
            transcript["events"].append(f"turn-{index}: done")
            break
        except (StructuredProposalError, ProviderError, KeyError) as exc:
            terminal = f"model-error:{type(exc).__name__}"
            print(f"[{index:02d}] proposal failed: "
                  f"{type(exc).__name__}: {str(exc)[:160]}")
            transcript["events"].append(
                f"turn-{index}: {type(exc).__name__}")
            break

        try:
            result = runtime.submit(request, mission)
        except Exception as exc:  # broker rejection recorded, not hidden
            turn_log.append({
                "capability": request.capability.value,
                "target": request.target,
                "decision": "submission-error",
                "executed": False, "success": None,
                "error": type(exc).__name__})
            terminal = "runtime-error"
            print(f"[{index:02d}] submit raised {type(exc).__name__}")
            break

        decision = result.broker_result.decision
        turn = {
            "capability": request.capability.value,
            "target": request.target,
            "decision": decision.decision.value,
            "executed": result.broker_result.capability_invoked,
            "success": (result.execution.success
                        if result.execution else None),
            "output": "",
            "error": "",
        }
        if result.execution is not None:
            turn["output"] = (
                excerpt_output(request, result.execution) or "")[:800]

        line = (f"[{index:02d}] {request.capability.value} "
                f"{request.target} -> {decision.decision.value}")

        if (request.capability is Capability.WRITE
                and decision.decision.value == "allow"):
            previous = (store.get(current_finding_id)
                        if current_finding_id else None)
            new_finding = Finding(
                finding_id=f"F-live-{index:02d}",
                state=FindingState.UNVERIFIED,
                summary=f"model-proposed fix: {request.target}",
                target=request.target,
                supersedes=(previous.finding_id
                            if previous is not None else None),
            )
            store.register(new_finding)
            if previous is not None and \
                    previous.state is FindingState.REFUTED:
                # New claim replaces the refuted one (legal passage).
                store.transition(
                    previous.finding_id, FindingState.SUPERSEDED,
                    evidence_seqs=(), supersedes=new_finding.finding_id)
            current_finding_id = new_finding.finding_id
            verify_out = verifier.verify(
                new_finding,
                RetestSpec(capability=Capability.READ,
                           target=request.target,
                           expected_substring=None),
                mission, requester="live-harness")
            if verify_out.transition_applied:
                probe_ok, _ = _run_probe()
                challenge_out = falsifier.challenge(
                    store.get(new_finding.finding_id),
                    ChallengeSpec(
                        capability=Capability.READ,
                        target=request.target,
                        purpose="live:probe-counter-example",
                        predicate=(lambda _p, _ok=probe_ok: not _ok)),
                    mission, requester="live-harness")
                line += (f" verify=VERIFIED probe="
                         f"{'PASS' if probe_ok else 'FAIL'} "
                         f"refuted={challenge_out.counter_example_observed}")
            else:
                line += f" verify={verify_out.transition_reason}"

        turn_log.append(turn)
        transcript["turns"].append(dict(turn, index=index))
        print(line)
    else:
        terminal = "max-turns"

    print(f"terminal: {terminal}")

    probe_ok, _ = _run_probe()
    _persist(ledger, "probe", probe_ok)
    tests_ok = _passing_run_tests(ledger)
    _persist(ledger, "regression", tests_ok)
    evaluation = gate.evaluate(GateInputs(
        mission=mission, findings=list(store.all()),
        regression_ok=tests_ok, behavior_probe_ok=probe_ok))
    print(f"Gate: {evaluation.verdict.value.upper()}")
    print(f"passed={list(evaluation.passed)}")
    print(f"failed={list(evaluation.failed)}")

    transcript["events"].append(f"gate:{evaluation.verdict.value}")
    transcript["terminal"] = terminal
    transcript["elapsed_s"] = round(time.time() - started, 1)
    (run_dir / "live_transcript.json").write_text(
        json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    ledger.close()
    return 0 if evaluation.verdict.value == "complete" else 1


def main() -> int:
    return run_live_hero()


if __name__ == "__main__":
    sys.exit(main())
