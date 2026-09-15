"""raphael_ibm_bob.harness.run — run lifecycle over the existing Runner.

`start_run` builds the standard stack, optionally takes ONE model
proposal through the boundary, then delegates to `Runner.run` — the
only control loop. The returned `RaphaelRun` references authoritative
objects (plan/finding IDs, ledger dir, gate verdict) without copying
their truth. Cancellation is cooperative and honest: a pending run
can be cancelled; a synchronously executing run cannot be preempted,
so `cancel()` reports whether it acted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, create_run_dir
from raphael_ibm_bob.falsifier import Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.model import ModelAdapter, ModelContext
from raphael_ibm_bob.harness.session import RaphaelSession, save_session
from raphael_ibm_bob.planner import Planner
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate
from raphael_ibm_bob.replanner import Replanner
from raphael_ibm_bob.runner import Runner, RunnerOutcome
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.verifier import Verifier
from raphael_ibm_bob.workspace import Workspace

RUN_STATES = ("pending", "running", "completed", "refused", "failed",
              "cancelled")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RaphaelRun:
    """A Harness run record: references, not duplicated truth."""
    run_id: str
    session_id: str
    mission: Mission
    workspace_root: str
    state: str = "pending"
    ledger_dir: str = ""
    gate_verdict: Optional[str] = None
    plan_ids: List[str] = field(default_factory=list)
    finding_ids: List[str] = field(default_factory=list)
    failure_reason: Optional[str] = None
    started_at: str = field(default_factory=_utcnow)
    finished_at: Optional[str] = None

    def cancel(self) -> bool:
        """Mark cancelled iff still pending. Synchronous execution
        cannot be preempted once started: returns False then."""
        if self.state != "pending":
            return False
        self.state = "cancelled"
        self.finished_at = _utcnow()
        return True

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mission"] = self.mission.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RaphaelRun":
        mission = data["mission"]
        if isinstance(mission, dict):
            mission = Mission(**mission)
        return cls(
            run_id=data["run_id"],
            session_id=data["session_id"],
            mission=mission,
            workspace_root=data["workspace_root"],
            state=data.get("state", "pending"),
            ledger_dir=data.get("ledger_dir", ""),
            gate_verdict=data.get("gate_verdict"),
            plan_ids=list(data.get("plan_ids", [])),
            finding_ids=list(data.get("finding_ids", [])),
            failure_reason=data.get("failure_reason"),
            started_at=data.get("started_at", _utcnow()),
            finished_at=data.get("finished_at"),
        )


def _harness_path(ledger_dir: Path) -> Path:
    return Path(ledger_dir) / "harness.json"


def save_run(run: RaphaelRun) -> Path:
    path = _harness_path(run.ledger_dir)
    path.write_text(
        json.dumps(run.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return path


def load_run(ledger_dir: Path) -> RaphaelRun:
    return RaphaelRun.from_dict(json.loads(
        _harness_path(ledger_dir).read_text(encoding="utf-8")))


def start_run(session: RaphaelSession, mission: Mission,
              workspace_root: Path, *, runs_root: Path,
              sessions_root: Optional[Path] = None,
              model: Optional[ModelAdapter] = None,
              **runner_kwargs: Any) -> RaphaelRun:
    """Drive one governed run and record it.

    Builds the standard stack in `runs/<run_id>/`, optionally submits
    ONE model proposal through Runtime/Broker/Policy (a DENY is
    recorded, never fatal), then delegates to `Runner.run`. Updates
    `session.current_run_id` and persists the session when
    `sessions_root` is given. Failures are recorded as failed runs
    with a reason, never raised past the Harness boundary... except
    unexpected exceptions, which are recorded AND re-raised after the
    ledger is closed so callers see them.
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
    workspace = Workspace(workspace_root)
    ledger = EvidenceLedger(run_dir)
    try:
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        store = FindingStore(ledger)
        verifier = Verifier(runtime, ledger, store)
        falsifier = Falsifier(runtime, ledger, store)
        replanner = Replanner(store, ledger)
        gate = BOBQualityGate(ledger)
        runner = Runner(runtime, ledger, store, verifier, falsifier,
                        replanner, gate, planner=Planner())
        if model is not None:
            context = ModelContext(
                mission=mission, findings=[],
                workspace_root=str(workspace_root),
                evidence_count=0,
                session_id=session.session_id)
            proposal = model.propose(context)
            runtime.submit(proposal, mission)
        outcome: RunnerOutcome = runner.run(mission, **runner_kwargs)
        plans = [p for p in (outcome.plan_a, outcome.plan_b,
                             outcome.plan_c) if p is not None]
        run.plan_ids = [p.plan_id for p in plans]
        run.finding_ids = [f.finding_id for f in outcome.findings]
        run.gate_verdict = outcome.gate_verdict.value
        run.state = ("completed"
                     if outcome.gate_verdict.value == "complete"
                     else "refused")
        run.finished_at = _utcnow()
    except Exception as exc:
        run.state = "failed"
        run.failure_reason = f"{type(exc).__name__}:{exc}"
        run.finished_at = _utcnow()
        save_run(run)
        ledger.close()
        raise
    save_run(run)
    ledger.close()
    session.current_run_id = run_id
    if sessions_root is not None:
        save_session(session, sessions_root)
    return run


__all__ = [
    "RUN_STATES",
    "RaphaelRun",
    "load_run",
    "save_run",
    "start_run",
]
