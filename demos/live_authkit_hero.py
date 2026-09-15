"""demos.live_authkit_hero — live model-driven authkit hero.

Judge-facing demonstration of the complete governed loop driven by a
REAL model, now routed through the Harness API's model-run component
(`raphael_ibm_bob.harness.model_run.run_model_mission`):

    Harness (Session → Run)
      → Model → Skill Registry → ActionRequest
      → Runtime → Broker → Policy → Execution → Evidence
      → Finding → Verification → Falsification → independent probe
      → QualityGate → COMPLETE / REFUSE

Run:

    RAPHAEL_MODEL_ENDPOINT=https://opencode.ai/zen/go/v1 \
    RAPHAEL_MODEL_NAME=deepseek-v4.1-flash \
    RAPHAEL_MODEL_API_KEY=<key> \
    PYTHONPATH=. python3 demos/live_authkit_hero.py

The credential is read from the environment ONLY — never hardcoded,
logged, persisted, or committed. If the model configuration is absent
the script exits 2 with a clear message; it never fabricates a run.
Deterministic fallback: `demos/authkit_hero.py`.

The model only PROPOSES; every proposal is validated and submitted
through the existing Runtime/Broker/Policy boundary. This demo owns
the independent probe (an external oracle); the Harness consumes its
result and persists the corresponding evidence.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def _setup_path() -> Path:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return ROOT


ROOT = _setup_path()

from raphael_ibm_bob.contracts import Mission  # noqa: E402
from raphael_ibm_bob.harness import api  # noqa: E402
from raphael_ibm_bob.harness.providers.openai_compat import (  # noqa: E402
    OpenAICompatAdapter,
    ProviderConfigError,
    config_from_env,
)
from raphael_ibm_bob.harness.session import (  # noqa: E402
    RaphaelSession,
    WorkspaceContext,
)
from raphael_ibm_bob.skills import (  # noqa: E402
    default_registry,
    register_default_skills,
)

AUTHKIT = ROOT / "fixtures" / "authkit"
MAX_TURNS = 14


def _snapshot() -> dict:
    return {p.name: p.read_bytes() for p in AUTHKIT.iterdir()
            if p.is_file()}


def _restore(snap: dict) -> None:
    for name, data in snap.items():
        (AUTHKIT / name).write_bytes(data)


def _probe_callable():
    """The independent oracle, owned by the caller (not the Harness)."""
    def _run() -> bool:
        proc = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)})
        return proc.returncode == 0
    return _run


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
        adapter = OpenAICompatAdapter(
            config, register_default_skills(default_registry()))
        session = RaphaelSession.create(
            mission=_authkit_mission(),
            workspace=WorkspaceContext(
                workspace_root=str(ROOT), project_name="authkit"),
            model=config.model,
            provider="openai-compatible")
        mission = _authkit_mission()

        print("# live authkit hero (via Harness model run)")
        print(f"# provider = {config.endpoint}")
        print(f"# model = {config.model}")

        result = api.start_model_run(
            session, mission, model=adapter,
            probe=_probe_callable(), max_turns=max_turns,
            runs_root=ROOT / "runs")
        run = result.run

        print(f"Run ID: {run.run_id}")
        print(f"Run dir: {run.ledger_dir}")
        print(f"terminal: {result.terminal} turns: {result.turns}")
        print(f"Gate: {(run.gate_verdict or 'unknown').upper()}")

        events = _read_events(Path(run.ledger_dir))
        for event in events:
            if event["type"] in ("ACTION_REQUESTED", "POLICY_DECISION",
                                 "FINDING_CHANGED", "GATE_EVALUATED"):
                print(f"  {event['type']}: "
                      f"{ {k: v for k, v in event.items() if k not in ('seq', 'type', 'run_id')} }")

        transcript = {
            "run_id": run.run_id,
            "model": config.model,
            "endpoint": config.endpoint,
            "terminal": result.terminal,
            "turns": result.turns,
            "gate": run.gate_verdict,
            "events": events,
            "elapsed_s": round(time.time() - started, 1),
        }
        (Path(run.ledger_dir) / "live_transcript.json").write_text(
            json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
        return 0 if run.gate_verdict == "complete" else 1
    finally:
        _restore(snap)


def _read_events(run_dir: Path):
    from raphael_ibm_bob.evidence_ledger import LedgerReader
    from raphael_ibm_bob.harness.events import collect_events
    from raphael_ibm_bob.harness.run import load_run
    run = load_run(run_dir)
    records = list(LedgerReader(run_dir / "evidence.jsonl").records())
    return collect_events(
        records, session_id=run.session_id, run_id=run.run_id,
        mission_id=run.mission.mission_id, terminal=run.state)


def main() -> int:
    return run_live_hero()


if __name__ == "__main__":
    sys.exit(main())
