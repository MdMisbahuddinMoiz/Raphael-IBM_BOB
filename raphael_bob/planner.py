"""raphael_bob.planner — M7/M8 real Planner.

The Planner reads a Mission and produces Plan A: a sequence of
BOB-native ActionRequests.

M7: the Planner's constructor accepted a `symptom_target` kwarg. The
     Runner passed the target through, which was a hidden dependency
     (the Runner was secretly injecting the target the Planner then
     "selected").

M8: the Planner is mission-driven. It reads `mission.problem` to
     determine the initial target. The Runner no longer supplies the
     target directly.

For the authkit hero, the Runner constructs the Mission as:

    Mission(
        mission_id="M-authkit",
        scope="fixtures",
        criteria=[...],
        problem={
            "symptom_target": "fixtures/authkit/login.py",
            "actual_defect_target": "fixtures/authkit/session.py",
        },
    )

The Planner emits a single READ action against `problem["symptom_target"]`.

If `problem["symptom_target"]` is missing, the Planner raises
`ValueError` — it must NEVER fall back to a constant target.

Legacy reference (ADAPT, NOT imported):
    src/orchestrator/brain/action.py:149 Action / Precondition / Effect
        - the Planner uses the same shape (capability + target + purpose)
          but emits BOB-native READ actions, not offensive ActionType
          grammar.
    src/orchestrator/brain/world.py WorldModel
        - not imported. M8 Planner uses `mission.problem` as its world
          model.
    src/raphael/cognitive/planner.py GreedyPlanner
        - REPLACE. M8 Planner is mission-driven, not utility-driven.
    src/raphael/main.py
        - ISOLATE. M8 Planner does NOT invoke the Wave1 loop.

Determinism:
    Same Mission -> same Plan A. SHA-256 of canonical
    {mission_id, "plan-a"} gives the plan_id. No wall-clock, no random
    seeds.

Limitations at M8:
    - The Planner emits exactly one action. Multi-step plans are M9.
    - The Planner does NOT inspect `mission.description` for the target
      (description is human-readable only).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    Mission,
    Plan,
)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Planner:
    """Mission-driven Planner.

    The Planner has NO constructor arguments; the target and capability
    are derived from the Mission. This is the M8 architectural rule:
    the Runner cannot secretly inject the target.
    """

    def plan_a(self, mission: Mission) -> Plan:
        """Produce Plan A from the Mission.

        Reads:
            mission.problem["symptom_target"]  -> READ target
            mission.problem["capability"]      -> BOB-native capability
                                                  (default Capability.READ)
            mission.problem["purpose"]         -> ActionRequest.purpose
                                                  (default: "plan-a:initial-probe")
        """
        if not isinstance(mission.problem, dict):
            raise ValueError(
                f"mission.problem must be a dict; got {type(mission.problem).__name__}"
            )
        target = mission.problem.get("symptom_target")
        if not target:
            raise ValueError(
                "Planner.plan_a requires mission.problem['symptom_target']; "
                "the Runner must NOT inject the target directly."
            )
        capability_str = mission.problem.get("capability", "read")
        try:
            capability = Capability(capability_str)
        except ValueError as e:
            raise ValueError(
                f"mission.problem['capability']={capability_str!r} is not a "
                f"valid BOB Capability: {e}"
            )
        purpose = mission.problem.get(
            "purpose", f"plan-a:probe:{target}",
        )

        plan_a_id = derive_plan_a_id(mission)
        step = ActionRequest(
            sequence=0,
            requester="planner",
            capability=capability,
            target=target,
            purpose=purpose,
            plan_id=plan_a_id,
            finding_id=None,
        )
        return Plan(
            plan_id=plan_a_id,
            mission_id=mission.mission_id,
            steps=[step],
            parent_plan_id=None,
        )


def derive_plan_a_id(mission: Mission) -> str:
    """Deterministic Plan A identifier from the mission."""
    h = hashlib.sha256(_canonical({
        "mission_id": mission.mission_id,
        "stage": "plan-a",
    }).encode("utf-8")).hexdigest()
    return f"P-{h[:12]}"


__all__ = ["Planner", "derive_plan_a_id"]
