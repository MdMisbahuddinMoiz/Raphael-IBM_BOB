"""raphael_ibm_bob.harness — thin RAPHAEL-specific Harness foundation.

The Harness WRAPS the existing Runner; it never reimplements the
control loop, Policy, Broker, or Quality Gate. It owns only what the
core lacks: sessions, mission intake, model boundary, workspace
context, run lifecycle records, event folding, and a CLI.

Adapted concepts (not copied code):
- DeepSeek session/event discipline
  (`packages/session/`, `packages/bundle/headless/`,
  `packages/workspace/`): append-only event log as truth, headless
  runner shape (adopt/create, drive to quiescence, flush, report),
  stable workspace identity over canonical paths.
- DeepSeek skill/capability declaration
  (`packages/core/tools/`, `packages/skill/`): see `skills.py`.
- Decepticon skill registry + proposal shape
  (`packages/decepticon-core/.../registry/skills.py`,
  `packages/decepticon/.../tools/skills.py`): see `skills.py`.

Deliberately NOT built: plugin systems, multi-agent orchestration,
distributed workers, model routing, databases, UI stacks, sandbox
backends. The model boundary (`model.py`) is an interface plus a
clearly-labeled scripted test double; no provider is fabricated.
"""
from raphael_ibm_bob.harness.session import (
    RaphaelSession,
    WorkspaceContext,
    load_session,
    save_session,
)
from raphael_ibm_bob.harness.run import RaphaelRun, start_run
from raphael_ibm_bob.harness.loop import (
    LoopOutcome,
    TurnRecord,
    drive_turns,
)
from raphael_ibm_bob.harness.model import (
    ModelAdapter,
    ModelContext,
    ScriptedModelAdapter,
)
from raphael_ibm_bob.harness.events import (
    EVENT_TYPES,
    collect_events,
)

__all__ = [
    "RaphaelSession",
    "WorkspaceContext",
    "load_session",
    "save_session",
    "RaphaelRun",
    "start_run",
    "LoopOutcome",
    "TurnRecord",
    "drive_turns",
    "ModelAdapter",
    "ModelContext",
    "ScriptedModelAdapter",
    "EVENT_TYPES",
    "collect_events",
]
