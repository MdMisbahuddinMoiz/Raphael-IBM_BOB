"""raphael_ibm_bob.harness.cli — Harness CLI.

Session/mission intake, governed run delegation, and post-process
inspection. Commands call the public Harness API (`harness.api`); the
API delegates to the existing Runner / core. Inspection reads from
disk. The opening probe may come from a scripted proposal, a single
live provider proposal, or a multi-turn live model run
(`--model-turns`).
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
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.events import collect_events
from raphael_ibm_bob.harness.model import ScriptedModelAdapter
from raphael_ibm_bob.harness.providers import ProviderConfigError
from raphael_ibm_bob.harness.run import find_run_dir, load_run


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
    session = api.create_session(
        mission=mission,
        workspace_root=Path(args.workspace),
        project_name=args.project,
        model=args.model,
        provider=args.provider,
        sessions_root=args.sessions_root)
    print(f"session: {session.session_id}")
    print(f"saved: {Path(args.sessions_root) / session.session_id / 'session.json'}")
    return 0


def cmd_session_show(args) -> int:
    session = api.get_session(args.session_id, args.sessions_root)
    print(json.dumps(session.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_session_list(args) -> int:
    for session_id in api.get_sessions(args.sessions_root):
        print(session_id)
    return 0


def cmd_mission_submit(args) -> int:
    session = api.submit_mission(
        args.session_id, _mission_from_args(args), args.sessions_root)
    print(f"mission {session.mission.mission_id} stored for "
          f"session {session.session_id}")
    return 0


def _build_provider(args):
    try:
        return api.make_model_adapter(args.model_provider)
    except ProviderConfigError as exc:
        print(f"error: model provider unusable: {exc}", file=sys.stderr)
        return None


def cmd_run_start(args) -> int:
    session = api.get_session(args.session_id, args.sessions_root)
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
    elif args.model_provider != "none":
        model = _build_provider(args)
        if model is None:
            return 2

    verification = [t for t in (args.verification_tests or "").split(",")
                    if t]
    if args.model_turns > 0:
        if model is None:
            print("error: --model-turns requires --model-provider",
                  file=sys.stderr)
            return 2
        result = api.start_model_run(
            session, model=model, max_turns=args.model_turns,
            sessions_root=args.sessions_root, runs_root=args.runs_root)
        run = result.run
        print(f"terminal: {result.terminal} turns: {result.turns}")
    else:
        run = api.start_run(
            session,
            model=model,
            sessions_root=args.sessions_root,
            runs_root=args.runs_root,
            candidate_target=args.candidate_target,
            max_replans=args.max_replans,
            verification_tests=tuple(verification),
        )
    print(f"run: {run.run_id}")
    print(f"state: {run.state}")
    print(f"gate: {run.gate_verdict}")
    print(f"ledger: {run.ledger_dir}/evidence.jsonl")
    return 0


def cmd_run_cancel(args) -> int:
    run = api.cancel_run(args.run, args.runs_root)
    print(f"run: {run.run_id}")
    print(f"state: {run.state}")
    print(f"cancelled: {run.state == 'cancelled'}")
    return 0


def _run_dir_from_arg(args) -> Path:
    candidate = Path(args.run)
    if candidate.is_dir():
        return candidate
    return find_run_dir(Path(args.runs_root), args.run)


def cmd_run_show(args) -> int:
    run = load_run(_run_dir_from_arg(args))
    print(json.dumps(run.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_run_events(args) -> int:
    run_dir = _run_dir_from_arg(args)
    records = list(LedgerReader(run_dir / "evidence.jsonl").records())
    run = load_run(run_dir)
    for event in collect_events(
            records, session_id=run.session_id, run_id=run.run_id,
            mission_id=run.mission.mission_id, terminal=run.state):
        detail = {k: v for k, v in event.items()
                  if k not in ("seq", "type")}
        print(f"{event['seq']:4d} {event['type']:22s} {detail}")
    return 0


def cmd_run_evidence(args) -> int:
    run_dir = _run_dir_from_arg(args)
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
    artifacts = _run_dir_from_arg(args) / "artifacts"
    if not artifacts.is_dir():
        print(f"error: no artifacts dir: {artifacts}", file=sys.stderr)
        return 2
    for path in sorted(artifacts.iterdir()):
        print(f"{path.stat().st_size:8d}  {path.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="RAPHAEL Harness CLI (wraps the existing Runner "
                    "and core; never reimplements them).")
    parser.add_argument("--sessions-root", default="sessions")
    parser.add_argument("--runs-root", default="runs")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("session-create", help="create a session")
    p_create.add_argument("--workspace", default=".")
    p_create.add_argument("--project", default="raphael")
    p_create.add_argument("--model", default="unconfigured")
    p_create.add_argument("--provider", default="none")
    p_create.add_argument("--with-mission", action="store_true")
    _add_mission_flags(p_create)
    p_create.set_defaults(func=cmd_session_create)

    p_show = sub.add_parser("session-show", help="print a session")
    p_show.add_argument("session_id")
    p_show.set_defaults(func=cmd_session_show)

    p_list = sub.add_parser("session-list", help="list sessions")
    p_list.set_defaults(func=cmd_session_list)

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
    p_start.add_argument("--model-provider", default="none",
                         help="live model provider (env-configured); "
                              "'none' disables it")
    p_start.add_argument("--model-turns", type=int, default=0,
                         help="drive a multi-turn model-led run "
                              "(requires --model-provider)")
    p_start.set_defaults(func=cmd_run_start)

    p_cancel = sub.add_parser("run-cancel",
                              help="cooperatively cancel a pending run")
    p_cancel.add_argument("run", help="run id or run directory")
    p_cancel.set_defaults(func=cmd_run_cancel)

    for name, func, help_text in (
            ("run-show", cmd_run_show, "print a run record"),
            ("run-events", cmd_run_events, "fold ledger into events"),
            ("run-evidence", cmd_run_evidence, "summarize ledger"),
            ("run-artifacts", cmd_run_artifacts, "list artifacts")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("run", help="run id or run directory")
        p.set_defaults(func=func)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
