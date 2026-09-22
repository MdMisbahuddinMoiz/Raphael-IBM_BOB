"""raphael_ibm_bob.harness.api — public Harness API.

Thin orchestration over the existing Harness components and the
RAPHAEL core. The Harness is NOT an authority: it creates sessions,
records missions, starts runs (delegating to the existing Runner /
model loop), and exposes READ-ONLY views over authoritative persisted
state (ledger records, artifacts, gate record, seal). It never
executes a capability directly, never bypasses Runtime/Broker/Policy,
and never decides completion — the QualityGate does.

Conceptual boundary:

    HARNESS: session, workspace, mission, run, events, evidence,
             artifacts, model configuration, cancellation, inspection.
    RAPHAEL: authorization (Policy), execution (Broker/capabilities),
             Evidence, Verification, Falsification, Replan, QualityGate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.evidence_ledger import LedgerReader
from raphael_ibm_bob.harness.events import collect_events
from raphael_ibm_bob.harness.model import ModelAdapter
from raphael_ibm_bob.harness.model_run import (
    DEFAULT_MAX_TURNS,
    ModelRunResult,
    run_model_mission,
)
from raphael_ibm_bob.harness.run import (
    RUN_STATES,
    TERMINAL_STATES,
    RaphaelRun,
    find_run_dir,
    load_run,
    save_run,
    start_run as _start_run,
)
from raphael_ibm_bob.harness.session import (
    RaphaelSession,
    WorkspaceContext,
    list_sessions,
    load_session,
    save_session,
)
from raphael_ibm_bob.seal import verify_seal

DEFAULT_SESSIONS_ROOT = Path("sessions")
DEFAULT_RUNS_ROOT = Path("runs")


# -----------------------------------------------------------------------------
# Sessions
# -----------------------------------------------------------------------------

def create_session(*, mission: Optional[Mission] = None,
                   workspace_root: Optional[Path] = None,
                   project_name: str = "raphael",
                   model: str = "unconfigured",
                   provider: str = "none",
                   session_id: Optional[str] = None,
                   sessions_root: Path = DEFAULT_SESSIONS_ROOT,
                   ) -> RaphaelSession:
    """Create and persist a session.

    Only a *reference* (provider/model names) is stored — never
    credentials, keys, or headers.
    """
    workspace = None
    if workspace_root is not None:
        workspace = WorkspaceContext(
            workspace_root=str(Path(workspace_root).resolve()),
            project_name=project_name)
    session = RaphaelSession.create(
        mission=mission, workspace=workspace, model=model,
        provider=provider, session_id=session_id)
    save_session(session, Path(sessions_root))
    return session


def get_session(session_id: str,
                sessions_root: Path = DEFAULT_SESSIONS_ROOT,
                ) -> RaphaelSession:
    """Load a persisted session (FileNotFoundError if absent)."""
    return load_session(session_id, Path(sessions_root))


def get_sessions(sessions_root: Path = DEFAULT_SESSIONS_ROOT,
                 ) -> List[str]:
    """List persisted session ids, sorted."""
    return list_sessions(Path(sessions_root))


def submit_mission(session_id: str, mission: Mission,
                   sessions_root: Path = DEFAULT_SESSIONS_ROOT,
                   ) -> RaphaelSession:
    """Attach/replace the session mission and persist."""
    session = load_session(session_id, Path(sessions_root))
    session.mission = mission
    save_session(session, Path(sessions_root))
    return session


# -----------------------------------------------------------------------------
# Model configuration (reference only; credentials stay in the env)
# -----------------------------------------------------------------------------

def make_model_adapter(provider: str = "openai-compatible",
                       registry=None) -> ModelAdapter:
    """Build a live provider adapter from environment configuration.

    Delegates to the existing provider factory. Only adapter/provider
    *names* appear in Harness records; the credential is read from the
    environment by the provider itself and never persisted.
    """
    from raphael_ibm_bob.harness.providers import provider_from_env
    from raphael_ibm_bob.skills import (
        default_registry,
        register_default_skills,
    )
    reg = registry or register_default_skills(default_registry())
    return provider_from_env(provider, reg)


# -----------------------------------------------------------------------------
# Runs
# -----------------------------------------------------------------------------

def start_run(session: RaphaelSession, mission: Optional[Mission] = None,
              *, sessions_root: Optional[Path] = None,
              runs_root: Path = DEFAULT_RUNS_ROOT,
              **runner_kwargs: Any) -> RaphaelRun:
    """Start a Runner-driven governed run (existing control loop)."""
    mission = mission or session.mission
    if mission is None:
        raise ValueError("no mission: submit one or pass mission=")
    if session.workspace is None:
        raise ValueError("session has no workspace")
    return _start_run(
        session, mission, Path(session.workspace.workspace_root),
        runs_root=Path(runs_root),
        sessions_root=(Path(sessions_root)
                       if sessions_root is not None else None),
        **runner_kwargs)


def start_model_run(session: RaphaelSession,
                    mission: Optional[Mission] = None,
                    *, model: ModelAdapter,
                    probe=None, max_turns: int = DEFAULT_MAX_TURNS,
                    sessions_root: Optional[Path] = None,
                    runs_root: Path = DEFAULT_RUNS_ROOT,
                    ) -> ModelRunResult:
    """Start a model-led governed run (multi-turn, gate at the end)."""
    mission = mission or session.mission
    if mission is None:
        raise ValueError("no mission: submit one or pass mission=")
    if session.workspace is None:
        raise ValueError("session has no workspace")
    return run_model_mission(
        session, mission, Path(session.workspace.workspace_root),
        runs_root=Path(runs_root), model=model, probe=probe,
        max_turns=max_turns,
        sessions_root=(Path(sessions_root)
                       if sessions_root is not None else None))


def start_network_run(session: RaphaelSession, mission: Optional[Mission] = None,
                      *, runs_root: Path = DEFAULT_RUNS_ROOT,
                      sessions_root: Optional[Path] = None,
                      target_store: Any = None,
                      mediator: Any = None,
                      timeout_seconds: Optional[float] = None) -> Any:
    """Start a deterministic governed network mission (D9.1).

    Delegates to the existing Harness network mission, which orchestrates
    the existing D9 governed network capability through Runtime -> Broker ->
    Policy -> NetworkMediator. It is NOT a second execution path.
    """
    from raphael_ibm_bob.harness.network_run import run_network_mission
    mission = mission or session.mission
    if mission is None:
        raise ValueError("no mission: submit one or pass mission=")
    if session.workspace is None:
        raise ValueError("session has no workspace")
    workspace_root = Path(session.workspace.workspace_root)

    # D12: a mission that declares a Telnet session uses the additive
    # governed Telnet mission; everything else uses the HTTP network mission.
    if isinstance(mission.problem, dict) and mission.problem.get("telnet"):
        from raphael_ibm_bob.harness.telnet_run import run_telnet_mission
        telnet_kwargs: Dict[str, Any] = {}
        if timeout_seconds is not None:
            telnet_kwargs["timeout_seconds"] = timeout_seconds
        return run_telnet_mission(
            session, mission, workspace_root,
            runs_root=Path(runs_root),
            sessions_root=(Path(sessions_root)
                           if sessions_root is not None else None),
            target_store=target_store, **telnet_kwargs)

    kwargs: Dict[str, Any] = {}
    if mediator is not None:
        kwargs["mediator"] = mediator
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    return run_network_mission(
        session, mission, workspace_root,
        runs_root=Path(runs_root),
        sessions_root=(Path(sessions_root)
                       if sessions_root is not None else None),
        target_store=target_store, **kwargs)


def get_run(run_id: str, runs_root: Path = DEFAULT_RUNS_ROOT) -> RaphaelRun:
    """Load a Harness run record by id (FileNotFoundError if absent)."""
    return load_run(find_run_dir(Path(runs_root), run_id))


def get_runs(runs_root: Path = DEFAULT_RUNS_ROOT) -> List[str]:
    """List Harness run ids (those with a harness.json), sorted."""
    root = Path(runs_root)
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "harness.json").is_file())


def cancel_run(run_id: str,
               runs_root: Path = DEFAULT_RUNS_ROOT) -> RaphaelRun:
    """Cooperatively cancel a PENDING run.

    An already-started synchronous run cannot be preempted; the
    returned run reflects whether cancellation acted (state ==
    'cancelled') or not (unchanged). A terminal run is never restarted.
    """
    run = get_run(run_id, runs_root)
    if run.cancel():
        save_run(run)
    return run


# -----------------------------------------------------------------------------
# Read-only inspection (authoritative persisted state)
# -----------------------------------------------------------------------------

def _run_dir(run_id: str, runs_root: Path) -> Path:
    return find_run_dir(Path(runs_root), run_id)


def get_evidence(run_id: str,
                 runs_root: Path = DEFAULT_RUNS_ROOT) -> List[Dict[str, Any]]:
    """Read every persisted ledger record for a run (read-only)."""
    run_dir = _run_dir(run_id, runs_root)
    return list(LedgerReader(run_dir / "evidence.jsonl").records())


def get_events(run_id: str,
               runs_root: Path = DEFAULT_RUNS_ROOT) -> List[Dict[str, Any]]:
    """Deterministically fold a run's ledger into Harness events."""
    run_dir = _run_dir(run_id, runs_root)
    run = load_run(run_dir)
    records = list(LedgerReader(run_dir / "evidence.jsonl").records())
    return collect_events(
        records, session_id=run.session_id, run_id=run.run_id,
        mission_id=run.mission.mission_id, terminal=run.state)


def get_artifacts(run_id: str,
                  runs_root: Path = DEFAULT_RUNS_ROOT) -> List[Path]:
    """List artifact files for a run (sorted; empty if none)."""
    art_dir = _run_dir(run_id, runs_root) / "artifacts"
    if not art_dir.is_dir():
        return []
    return sorted(p for p in art_dir.iterdir() if p.is_file())


def get_gate(run_id: str,
             runs_root: Path = DEFAULT_RUNS_ROOT) -> Optional[Dict[str, Any]]:
    """Return the LAST persisted QualityGate record, or None."""
    gates = [r for r in get_evidence(run_id, runs_root)
             if r.get("kind") == "gate"]
    return gates[-1] if gates else None


def get_seal(run_id: str,
             runs_root: Path = DEFAULT_RUNS_ROOT) -> Tuple[bool, str]:
    """Verify a run's evidence seal: (ok, reason)."""
    return verify_seal(_run_dir(run_id, runs_root))


def get_tasks(run_id: str,
              runs_root: Path = DEFAULT_RUNS_ROOT) -> Dict[str, Any]:
    """Read a run's task decomposition (read-only).

    Prefers the persisted `tasks.json` written by a model-led run;
    otherwise derives the deterministic decomposition from the run's
    mission. Descriptive orchestration metadata only — never execution,
    and never a completion authority.
    """
    run_dir = _run_dir(run_id, runs_root)
    tasks_path = run_dir / "tasks.json"
    if tasks_path.is_file():
        return json.loads(tasks_path.read_text(encoding="utf-8"))
    from raphael_ibm_bob.specialization import decompose_mission
    return decompose_mission(load_run(run_dir).mission).to_dict()


# -----------------------------------------------------------------------------
# Discovery (M14 read-only catalog; declarations grant no authority)
# -----------------------------------------------------------------------------

def _skill_registry():
    """The authoritative CapabilityRegistry (single source of truth)."""
    from raphael_ibm_bob.skills import (
        default_registry,
        register_default_skills,
    )
    return register_default_skills(default_registry())


def list_roles() -> List[Any]:
    """Declared specialist roles (read-only)."""
    return _skill_registry().list_roles()


def list_capabilities(role: Optional[str] = None) -> List[Any]:
    """Declared capability definitions, optionally filtered by role."""
    registry = _skill_registry()
    definitions = registry.list_capabilities()
    if role is None:
        return definitions
    allowed = set(registry.list_capabilities_for_role(role))
    return [d for d in definitions if d.capability in allowed]


def list_skills(*, role: Optional[str] = None, capability: Optional[Any] = None,
                evidence_available: Tuple[str, ...] = ()) -> List[Any]:
    """Read-only role/capability/evidence-aware skill discovery."""
    return _skill_registry().discover_skills(
        role=role, capability=capability,
        evidence_available=tuple(evidence_available))


# -----------------------------------------------------------------------------
# Workspace view
# -----------------------------------------------------------------------------

def describe_workspace(workspace_root: Path,
                       sessions_root: Optional[Path] = None,
                       runs_root: Path = DEFAULT_RUNS_ROOT,
                       ) -> Dict[str, Any]:
    """Read-only description of a workspace and its associations.

    Describes; never executes. `available_capabilities` is the
    declared MVP allow-list, not a grant of authority.
    """
    from raphael_ibm_bob.contracts import Capability
    root = str(Path(workspace_root).resolve())
    associated_sessions: List[str] = []
    run_ids: List[str] = []
    if sessions_root is not None:
        for sid in list_sessions(Path(sessions_root)):
            session = load_session(sid, Path(sessions_root))
            if session.workspace and \
                    session.workspace.workspace_root == root:
                associated_sessions.append(sid)
                run_ids.extend(session.run_ids)
    return {
        "workspace_root": root,
        "is_directory": Path(workspace_root).is_dir(),
        "sessions": sorted(set(associated_sessions)),
        "runs": sorted(set(run_ids)),
        "available_capabilities": sorted(c.value for c in Capability),
    }


__all__ = [
    "DEFAULT_MAX_TURNS",
    "DEFAULT_RUNS_ROOT",
    "DEFAULT_SESSIONS_ROOT",
    "RUN_STATES",
    "TERMINAL_STATES",
    "cancel_run",
    "create_session",
    "describe_workspace",
    "get_artifacts",
    "get_events",
    "get_evidence",
    "get_gate",
    "get_run",
    "get_runs",
    "get_seal",
    "get_session",
    "get_sessions",
    "get_tasks",
    "list_capabilities",
    "list_roles",
    "list_skills",
    "make_model_adapter",
    "start_model_run",
    "start_network_run",
    "start_run",
    "submit_mission",
]
