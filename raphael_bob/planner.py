"""raphael_bob.planner — M7 real Planner.

Replaces the M5 PlannerStub. The Planner reads a Mission and produces
Plan A: a sequence of BOB-native ActionRequests.

For the authkit hero, the Planner produces:

    Plan A = [
        ActionRequest(
            capability=READ,
            target="fixtures/authkit/login.py",
            purpose="plan-a:probe-decoy-location",
        )
    ]

The decoy target is the result of the Planner's analysis of the
Mission: it inspects the mission scope and the candidate symptom
described in the mission description, then emits a `READ` action
against the symptom location (NOT the actual defect). The Replanner
will derive the actual defect from the Falsifier's counter-example
evidence at M5.

Legacy reference (ADAPT, NOT imported):
    src/orchestrator/brain/action.py:149 Action / Precondition / Effect
        - the M7 Planner borrows the Precondition/Effect vocabulary
          shape but emits BOB-native READ/LIST/SEARCH/WRITE/RUN_TEST
          actions, NOT offensive ActionType grammar.
    src/orchestrator/brain/world.py WorldModel
        - not imported. M7 Planner uses the Mission + scope as its
          world model.
    src/raphael/cognitive/planner.py GreedyPlanner
        - REPLACE. M7 Planner is evidence-aware, not utility-driven.
    src/raphael/main.py
        - ISOLATE. M7 Planner does NOT invoke the Wave1 loop.

Determinism:
    Same Mission -> same Plan A. No wall-clock, no random seeds.

Limitations at M7:
    - The Planner targets the symptom location (login.py) because
      that is what the mission description points to. The Replanner
      is responsible for deriving the real defect location.
    - The Planner does NOT itself attempt unauthorized actions. The
      hero Runner may inject FC1 demonstration actions separately.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

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
    """BOB-native Planner.

    `symptom_target` is the file the Mission points to as the visible
    symptom. For the authkit hero this is `fixtures/authkit/login.py`.
    `discovery_targets` are additional READs the Planner emits so
    that the runner can build a richer initial evidence trail.
    """

    symptom_target: str = "fixtures/authkit/login.py"
    capability: Capability = Capability.READ
    discovery_targets: tuple[str, ...] = ()

    def plan_a(self, mission: Mission) -> Plan:
        """Produce Plan A from the Mission.

        The plan contains exactly one BOB-native action: a READ on
        `symptom_target`. The runner registers a candidate Finding
        from this step and the rest of the loop follows.
        """
        plan_a_id = derive_plan_a_id(mission)
        step = ActionRequest(
            sequence=0,
            requester="planner",
            capability=self.capability,
            target=self.symptom_target,
            purpose=f"plan-a:probe-symptom:{self.symptom_target}",
            plan_id=plan_a_id,
            finding_id=None,
        )
        return Plan(
            plan_id=plan_a_id,
            mission_id=mission.mission_id,
            steps=[step],
            parent_plan_id=None,
        )

    def plan_a_steps(self, mission: Mission) -> List[ActionRequest]:
        """Return just the steps (used by the hero Runner)."""
        return list(self.plan_a(mission).steps)


def derive_plan_a_id(mission: Mission) -> str:
    """Deterministic Plan A identifier from the mission."""
    h = hashlib.sha256(_canonical({
        "mission_id": mission.mission_id,
        "stage": "plan-a",
    }).encode("utf-8")).hexdigest()
    return f"P-{h[:12]}"


__all__ = ["Planner", "derive_plan_a_id"]
