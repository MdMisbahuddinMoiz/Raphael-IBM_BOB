"""raphael_ibm_bob.harness.model_run — governed multi-turn model run.

Promotes the live model loop (previously demo-only) into the Harness
as a reusable, mission-generic component. The model only PROPOSES;
every proposal is validated against the skill registry and submitted
through the existing Runtime -> Broker -> Policy boundary. The loop
performs NO authorization and NO gating of its own: it coordinates
turns, registers a finding when the model applies a remediation, asks
the existing Verifier/Falsifier to retest/challenge it, persists
probe/regression proofs, and finally asks the existing QualityGate
for the verdict.

This module contains NO subprocess and NO capability dispatch. The
optional `probe` is a caller-supplied callable (an independent
oracle the caller owns); the Harness only consumes its boolean result
and persists the corresponding evidence record.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
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
from raphael_ibm_bob.harness.loop import excerpt_output
from raphael_ibm_bob.harness.model import ModelAdapter, ModelContext
from raphael_ibm_bob.harness.providers import (
    DoneSignal,
    ProviderError,
    StructuredProposalError,
)
from raphael_ibm_bob.harness.run import RaphaelRun, save_run
from raphael_ibm_bob.harness.session import RaphaelSession, save_session
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.specialization import (
    TaskState,
    decompose_mission,
    default_roles,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier
from raphael_ibm_bob.workspace import Workspace

ProbeCallable = Callable[[], bool]

#: Single source of truth for the model-loop turn bound. Referenced by
#: `harness.api.start_model_run` and the HTTP layer so an omitted
#: `max_turns` means the SAME thing on every entry point (M15.2 parity).
DEFAULT_MAX_TURNS = 14

#: Which pipeline step each capability advances (M14 orchestration).
_CAPABILITY_STEP = {
    Capability.READ: "investigate",
    Capability.LIST: "investigate",
    Capability.SEARCH: "investigate",
    Capability.RUN_TEST: "reproduce",
    Capability.WRITE: "remediate",
}


def _roles_context() -> Tuple[dict, ...]:
    """Compact, deterministic role vocabulary for the model."""
    return tuple({
        "role": role.id,
        "purpose": role.purpose,
        "capabilities": sorted(c.value for c in role.capabilities),
    } for role in default_roles().list_roles())


def _task_context(plan) -> dict:
    root = plan.root
    return {
        "task_id": root.task_id,
        "name": root.name,
        "role": root.role,
        "steps": [{"task_id": t.task_id, "name": t.name,
                   "role": t.role, "skills": list(t.skills),
                   "state": plan.states[t.task_id].value}
                  for t in root.subtasks],
    }


def _advance_task(plan, mission_id: str, capability: Capability,
                  success: bool) -> None:
    """Nudge the matching pipeline step's state (declaration only).

    Guarded: only PENDING -> ACTIVE and ACTIVE -> COMPLETED are
    applied; any other current state is left untouched. Never affects
    the QualityGate.
    """
    step = _CAPABILITY_STEP.get(capability)
    if step is None:
        return
    task_id = f"{mission_id}::{step}"
    if task_id not in plan.states:
        return
    current = plan.states[task_id]
    if current is TaskState.PENDING:
        plan.mark(task_id, TaskState.ACTIVE)
    elif current is TaskState.ACTIVE and success:
        plan.mark(task_id, TaskState.COMPLETED)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminal_reason(exc: BaseException) -> str:
    """Redacted, bounded reason string for a non-`done` terminal.

    Provider errors are already redacted by the adapter; this only
    bounds length so a malformed model response cannot bloat records.
    """
    return f"{type(exc).__name__}:{exc}"[:500]


def _workspace_files(workspace_root: Path, mission: Mission,
                     limit: int = 40) -> Tuple[str, ...]:
    """Bounded, deterministic listing of in-scope files for context.

    Lists regular files under `workspace_root/<mission.scope>` (or the
    root when scope is empty), sorted, capped. Gives the model the
    file surface without dumping the whole repository.
    """
    root = Path(workspace_root)
    base = root / mission.scope if mission.scope else root
    if not base.is_dir():
        base = root
    files: List[str] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part == "__pycache__" for part in path.parts):
            continue
        try:
            files.append(path.relative_to(root).as_posix())
        except ValueError:
            continue
        if len(files) >= limit:
            break
    return tuple(files)


def _latest_bound_execution(ledger: EvidenceLedger):
    records = ledger.all_records()
    decisions = {r.get("request_seq"): r.get("decision") for r in records
                 if r.get("kind") == "decision"}
    results = {r.get("request_seq"): r for r in records
               if r.get("kind") == "result"}
    req_seq = None
    for r in records:
        if r.get("kind") != "request":
            continue
        seq = r.get("seq")
        if (decisions.get(seq) == "allow"
                and results.get(seq, {}).get("success") is True):
            req_seq = seq
    if req_seq is None:
        return 0, 0, None
    decs = [r for r in records if r.get("kind") == "decision"
            and r.get("request_seq") == req_seq]
    dec_seq = decs[-1].get("seq") if decs else 0
    res_seq = (results.get(req_seq) or {}).get("seq")
    return req_seq, dec_seq, res_seq


def _persist_proof(ledger: EvidenceLedger, kind: str, ok: bool) -> None:
    req_seq, dec_seq, res_seq = (0, 0, None)
    if ok:
        req_seq, dec_seq, res_seq = _latest_bound_execution(ledger)
    if kind == "probe":
        payload = {"kind": "probe",
                   "result": "passed" if ok else "failed",
                   "allowed": ok, "request_seq": req_seq,
                   "result_seq": res_seq}
        prefix = "PB"
    else:
        payload = {"kind": "regression",
                   "result": "passed" if ok else "failed",
                   "request_seq": req_seq, "result_seq": res_seq}
        prefix = "RG"
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix=prefix),
        producer=kind, request_seq=req_seq, decision_seq=dec_seq,
        result_seq=res_seq, payload=payload)


def passing_run_tests(ledger: EvidenceLedger) -> bool:
    """True iff some RUN_TEST executed with artifact returncode 0.

    Reads the persisted result artifacts — the same evidence the
    QualityGate inspects — so a failing test does not count.
    """
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


@dataclass
class ModelRunResult:
    """Authoritative run record plus terminal-loop details."""
    run: RaphaelRun
    terminal: str
    turns: int
    gate_verdict: Optional[str]
    task_plan: Optional[dict] = None
    terminal_reason: str = ""


def run_model_mission(session: RaphaelSession, mission: Mission,
                      workspace_root: Path, *, runs_root: Path,
                      model: ModelAdapter,
                      sessions_root: Optional[Path] = None,
                      max_turns: int = DEFAULT_MAX_TURNS,
                      probe: Optional[ProbeCallable] = None,
                      history_window: int = 5) -> ModelRunResult:
    """Drive one governed, model-led mission to a terminal state.

    The `RaphaelRun.state` becomes `completed`/`refused` per the
    QualityGate verdict, or `failed` when the loop itself raises. A
    model error is not fatal: it ends the turn loop and the gate
    judges whatever evidence exists.
    """
    run_id, run_dir = create_run_dir(runs_root)
    run = RaphaelRun(
        run_id=run_id,
        session_id=session.session_id,
        mission=mission,
        workspace_root=str(workspace_root),
        state="running",
        ledger_dir=str(run_dir),
    )
    session.add_run(run_id)
    # Persist the run record immediately (state="running") so an active
    # model run is observable while it executes (live operator streaming).
    save_run(run)

    workspace = Workspace(workspace_root)
    ledger = EvidenceLedger(run_dir)
    terminal = "max-turns"
    terminal_reason = ""
    turn_log: List[dict] = []
    current_finding_id: Optional[str] = None
    plan = None

    try:
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        store = FindingStore(ledger)
        verifier = Verifier(runtime, ledger, store)
        falsifier = Falsifier(runtime, ledger, store)
        gate = BOBQualityGate(ledger)
        files = _workspace_files(Path(workspace_root), mission)
        plan = decompose_mission(mission)
        roles_ctx = _roles_context()

        for index in range(max_turns):
            context = ModelContext(
                mission=mission,
                findings=list(store.all()),
                workspace_root=str(workspace_root),
                evidence_count=len(ledger.all_records()),
                workspace_files=files,
                recent_turns=tuple(turn_log[-history_window:]),
                session_id=session.session_id,
                available_roles=roles_ctx,
                active_task=_task_context(plan),
            )
            try:
                request = model.propose(context)
            except DoneSignal:
                terminal = "done"
                terminal_reason = "model declared done"
                break
            except (StructuredProposalError, ProviderError, KeyError) as exc:
                terminal = "model-error"
                terminal_reason = _terminal_reason(exc)
                break

            try:
                result = runtime.submit(request, mission)
            except Exception as exc:
                terminal = "runtime-error"
                terminal_reason = _terminal_reason(exc)
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

            if (request.capability is Capability.WRITE
                    and decision.decision.value == "allow"):
                previous = (store.get(current_finding_id)
                            if current_finding_id else None)
                finding = Finding(
                    finding_id=f"F-{run_id[-6:]}-{index:02d}",
                    state=FindingState.UNVERIFIED,
                    summary=f"model-proposed fix: {request.target}",
                    target=request.target,
                    supersedes=(previous.finding_id
                                if previous is not None else None),
                )
                store.register(finding)
                if previous is not None and \
                        previous.state is FindingState.REFUTED:
                    store.transition(
                        previous.finding_id, FindingState.SUPERSEDED,
                        evidence_seqs=(),
                        supersedes=finding.finding_id)
                current_finding_id = finding.finding_id
                verify_out = verifier.verify(
                    finding,
                    RetestSpec(capability=Capability.READ,
                               target=request.target,
                               expected_substring=None),
                    mission, requester="harness")
                if verify_out.transition_applied and probe is not None:
                    try:
                        probe_ok_now = bool(probe())
                    except Exception:
                        probe_ok_now = False
                    falsifier.challenge(
                        store.get(finding.finding_id),
                        ChallengeSpec(
                            capability=Capability.READ,
                            target=request.target,
                            purpose="harness:probe-counter-example",
                            predicate=(lambda _p, _ok=probe_ok_now: not _ok)),
                        mission, requester="harness")

            turn_log.append(turn)
            _advance_task(plan, mission.mission_id,
                          request.capability, bool(turn["success"]))

        probe_ok: Optional[bool] = None
        if probe is not None:
            try:
                probe_ok = bool(probe())
            except Exception:
                probe_ok = False
            _persist_proof(ledger, "probe", probe_ok)
        tests_ok = passing_run_tests(ledger)
        _persist_proof(ledger, "regression", tests_ok)

        if terminal == "max-turns":
            terminal_reason = f"reached max_turns={max_turns}"

        evaluation = gate.evaluate(GateInputs(
            mission=mission,
            findings=list(store.all()),
            regression_ok=tests_ok,
            behavior_probe_ok=bool(probe_ok),
        ))
        run.gate_verdict = evaluation.verdict.value
        run.finding_ids = [f.finding_id for f in store.all()]
        run.state = ("completed"
                     if evaluation.verdict.value == "complete"
                     else "refused")
        run.finished_at = _utcnow()
    except Exception as exc:
        run.state = "failed"
        run.failure_reason = f"{type(exc).__name__}:{exc}"
        run.finished_at = _utcnow()
        save_run(run)
        ledger.close()
        if sessions_root is not None:
            save_session(session, sessions_root)
        raise
    save_run(run)
    ledger.close()
    if sessions_root is not None:
        save_session(session, sessions_root)
    task_plan = plan.to_dict() if plan is not None else None
    if task_plan is not None:
        (run_dir / "tasks.json").write_text(
            json.dumps(task_plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return ModelRunResult(run=run, terminal=terminal,
                          turns=len(turn_log),
                          gate_verdict=run.gate_verdict,
                          task_plan=task_plan,
                          terminal_reason=terminal_reason)


__all__ = [
    "DEFAULT_MAX_TURNS",
    "ModelRunResult",
    "ProbeCallable",
    "passing_run_tests",
    "run_model_mission",
]
