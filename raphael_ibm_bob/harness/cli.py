"""raphael_ibm_bob.harness.cli — smallest usable Harness CLI.

Session/mission intake, governed run delegation, and post-process
inspection. Every run goes through `harness.run.start_run` (hence the
existing Runner); inspection reads from disk. No model provider here:
`run start` accepts an optional scripted-proposal target for the
opening probe, otherwise the run is purely Runner-driven.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import LedgerReader
from raphael_ibm_bob.harness.events import collect_events
from raphael_ibm_bob.harness.model import ScriptedModelAdapter
from raphael_ibm_bob.harness.run import load_run, start_run
from raphael_ibm_bob.harness.session import (
    RaphaelSession,
    WorkspaceContext,
    load_session,
    save_session,
)


def _mission_from_args(args) -> Mission:
    criteria = [c for c in (args.criteria or "").split(",") if c]
    return Mission(
        mission_id=args.mission_id,
        description=args.description,
        scope=args.scope,
        criteria=criteria,
        problem={
            "symptom_target": args.symptom_target,
            "capability": args.capability,
            "purpose": args.purpose or f"harness:probe:{args.symptom_target}",
        },
    )


def _add_mission_flags(parser) -> None:
    parser.add_argument("--mission-id", default="M-harness")
    parser.add_argument("--description", default="harness mission")
    parser.add_argument("--scope", default="src/")
    parser.add_argument("--criteria", default="recover,capped")
    parser.add_argument("--symptom-target", default="src/probe.txt")
    parser.add_argument("--capability", default="read")
    parser.add_argument("--purpose", default="")


def cmd_session_create(args) -> int:
    mission = _mission_from_args(args) if args.with_mission else None
    workspace = WorkspaceContext(
        workspace_root=str(Path(args.workspace).resolve()),
        project_name=args.project)
    session = RaphaelSession.create(
        mission=mission, workspace=workspace, model=args.model)
    path = save_session(session, args.sessions_root)
    print(f"session: {session.session_id}")
    print(f"saved: {path}")
    return 0


def cmd_session_show(args) -> int:
    session = load_session(args.session_id, args.sessions_root)
    print(json.dumps(session.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_mission_submit(args) -> int:
    session = load_session(args.session_id, args.sessions_root)
    session.mission = _mission_from_args(args)
    path = save_session(session, args.sessions_root)
    print(f"mission {session.mission.mission_id} stored for "
          f"session {session.session_id}")
    print(f"saved: {path}")
    return 0


def cmd_run_start(args) -> int:
    session = load_session(args.session_id, args.sessions_root)
    if session.mission is None:
        print("error: session has no mission; use mission submit first",
              file=sys.stderr)
        return 2
    if session.workspace is None:
        print("error: session has no workspace", file=sys.stderr)
        return 2
    model = None
    if args.probe_target:
        proposal = ActionRequest(
            sequence=0, requester="harness:model",
            capability=Capability.READ, target=args.probe_target,
            purpose=f"harness:opening-probe:{args.probe_target}")
        model = ScriptedModelAdapter(
            {session.mission.mission_id: proposal})
    verification = [t for t in (args.verification_tests or "").split(",")
                    if t]
    run = start_run(
        session, session.mission,
        Path(session.workspace.workspace_root),
        runs_root=args.runs_root,
        sessions_root=args.sessions_root,
        model=model,
        candidate_target=args.candidate_target,
        max_replans=args.max_replans,
        verification_tests=tuple(verification),
    )
    print(f"run: {run.run_id}")
    print(f"state: {run.state}")
    print(f"gate: {run.gate_verdict}")
    print(f"ledger: {run.ledger_dir}/evidence.jsonl")
    return 0


def _resolve_run(args) -> Path:
    return Path(args.run)


def cmd_run_show(args) -> int:
    run = load_run(_resolve_run(args))
    print(json.dumps(run.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_run_events(args) -> int:
    run_dir = _resolve_run(args)
    records = list(LedgerReader(run_dir / "evidence.jsonl").records())
    run = load_run(run_dir)
    for event in collect_events(
            records, session_id=run.session_id, run_id=run.run_id,
            mission_id=run.mission.mission_id):
        detail = {k: v for k, v in event.items()
                  if k not in ("seq", "type")}
        print(f"{event['seq']:4d} {event['type']:22s} {detail}")
    return 0


def cmd_run_evidence(args) -> int:
    run_dir = _resolve_run(args)
    records = list(LedgerReader(run_dir / "evidence.jsonl").records())
    kinds: dict = {}
    for rec in records:
        kinds[rec.get("kind")] = kinds.get(rec.get("kind"), 0) + 1
    print(f"records: {len(records)}")
    for kind in sorted(kinds):
        print(f"  {kind}: {kinds[kind]}")
    gates = [r for r in records if r.get("kind") == "gate"]
    for gate in gates:
        print(f"gate: {gate.get('decision')} "
              f"passed={gate.get('checks', [])}")
    return 0


def cmd_run_artifacts(args) -> int:
    artifacts = _resolve_run(args) / "artifacts"
    if not artifacts.is_dir():
        print(f"error: no artifacts dir: {artifacts}", file=sys.stderr)
        return 2
    for path in sorted(artifacts.iterdir()):
        print(f"{path.stat().st_size:8d}  {path.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Thin RAPHAEL Harness CLI (wraps the existing "
                    "Runner; never reimplements it).")
    parser.add_argument("--sessions-root", default="sessions")
    parser.add_argument("--runs-root", default="runs")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("session-create",
                              help="create a session")
    p_create.add_argument("--workspace", default=".")
    p_create.add_argument("--project", default="raphael")
    p_create.add_argument("--model", default="unconfigured")
    p_create.add_argument("--with-mission", action="store_true")
    _add_mission_flags(p_create)
    p_create.set_defaults(func=cmd_session_create)

    p_show = sub.add_parser("session-show", help="print a session")
    p_show.add_argument("session_id")
    p_show.set_defaults(func=cmd_session_show)

    p_submit = sub.add_parser("mission-submit",
                              help="attach a mission to a session")
    p_submit.add_argument("session_id")
    _add_mission_flags(p_submit)
    p_submit.set_defaults(func=cmd_mission_submit)

    p_start = sub.add_parser("run-start", help="drive a governed run")
    p_start.add_argument("session_id")
    p_start.add_argument("--candidate-target", default="src/fixed.py")
    p_start.add_argument("--max-replans", type=int, default=1)
    p_start.add_argument("--verification-tests", default="")
    p_start.add_argument("--probe-target", default="")
    p_start.set_defaults(func=cmd_run_start)

    for name, func, help_text in (
            ("run-show", cmd_run_show, "print a run record"),
            ("run-events", cmd_run_events, "fold ledger into events"),
            ("run-evidence", cmd_run_evidence, "summarize ledger"),
            ("run-artifacts", cmd_run_artifacts, "list artifacts")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("run", help="run ledger directory")
        p.set_defaults(func=func)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
