"""raphael_ibm_bob.specialization — M14 capability specialization.

Decepticon-INSPIRED specialization model implemented inside RAPHAEL:
a small, safe vocabulary of specialist **roles**, richer **skill /
capability declarations**, a descriptive **task decomposition** layer,
and **evidence contracts** — all as metadata.

This module declares; it never authorizes or executes. Every executable
action still travels:

    Model/Specialist -> Skill Registry -> ActionRequest
      -> Runtime -> Broker -> Policy -> Execution -> Evidence
      -> Verification -> Falsification -> Replan -> QualityGate

Nothing here imports Decepticon, vendors its source, or adds an
execution path. Roles describe *responsibility*, not permission.

Design references (concepts only, no code): Decepticon's role/registry
separation (`packages/decepticon-core/.../registry/roles.py`) and
skill declarations (`.../registry/skills.py`); DeepSeek's skill
bundles (`packages/skill/`). Only the *shape* — declared roles, skills,
and task decomposition distinct from execution — is adapted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import Capability, Mission


# -----------------------------------------------------------------------------
# Roles — responsibility, never permission
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Role:
    """A specialist responsibility in the defensive coding workflow.

    `capabilities` lists the capabilities this role is *intended to
    use* — a declaration of fit, not a grant. Policy still authorizes
    every individual action.
    """
    id: str
    name: str
    purpose: str
    capabilities: Tuple[Capability, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("role id and name are required")
        if not self.purpose:
            raise ValueError("role purpose is required")
        if not self.capabilities:
            raise ValueError("role must declare at least one capability")
        for cap in self.capabilities:
            if not isinstance(cap, Capability):
                raise ValueError(
                    f"role {self.id} capabilities must be Capability "
                    f"members, got {cap!r}")


#: The deliberately small, safe role vocabulary (six roles).
DEFAULT_ROLES: Tuple[Role, ...] = (
    Role(
        id="investigator",
        name="Investigator",
        purpose="Locate relevant implementation and evidence.",
        capabilities=(Capability.READ, Capability.LIST,
                      Capability.SEARCH),
    ),
    Role(
        id="test_analyst",
        name="Test analyst",
        purpose="Execute authorized verification tests.",
        capabilities=(Capability.RUN_TEST,),
    ),
    Role(
        id="remediation_planner",
        name="Remediation planner",
        purpose="Propose a corrective change.",
        capabilities=(Capability.WRITE,),
    ),
    Role(
        id="verifier",
        name="Verifier",
        purpose=("Establish whether the proposed correction satisfies "
                 "the proof obligation."),
        capabilities=(Capability.READ, Capability.RUN_TEST),
    ),
    Role(
        id="falsifier",
        name="Falsifier",
        purpose=("Challenge apparent success with negative controls."),
        capabilities=(Capability.READ, Capability.SEARCH),
    ),
    Role(
        id="evidence_analyst",
        name="Evidence analyst",
        purpose="Interpret persisted evidence and reconstruct state.",
        capabilities=(Capability.READ, Capability.LIST),
    ),
)


class RoleRegistry:
    """Read-mostly index of declared roles (no authority)."""

    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {}

    def register_role(self, role: Role) -> None:
        if role.id in self._roles:
            raise ValueError(f"duplicate role: {role.id}")
        self._roles[role.id] = role

    def has_role(self, role_id: str) -> bool:
        return role_id in self._roles

    def get_role(self, role_id: str) -> Role:
        try:
            return self._roles[role_id]
        except KeyError:
            raise KeyError(f"role not registered: {role_id!r}") from None

    def list_roles(self) -> List[Role]:
        return [self._roles[k] for k in sorted(self._roles)]


def default_roles() -> RoleRegistry:
    """Registry preloaded with the six safe roles."""
    registry = RoleRegistry()
    for role in DEFAULT_ROLES:
        registry.register_role(role)
    return registry


# -----------------------------------------------------------------------------
# Task decomposition — descriptive orchestration metadata
# -----------------------------------------------------------------------------

class TaskState(str, Enum):
    """Orchestration state of a task (distinct from run lifecycle).

    A task reaching COMPLETED never makes the run COMPLETE — the
    QualityGate remains the sole completion authority.
    """
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    REFUTED = "refuted"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


#: Allowed task-state transitions (small, explicit state machine).
_TASK_TRANSITIONS = {
    TaskState.PENDING: {TaskState.ACTIVE, TaskState.BLOCKED,
                        TaskState.CANCELLED},
    TaskState.ACTIVE: {TaskState.COMPLETED, TaskState.REFUTED,
                       TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.REFUTED: {TaskState.ACTIVE, TaskState.BLOCKED,
                        TaskState.CANCELLED},
    TaskState.BLOCKED: {TaskState.ACTIVE, TaskState.CANCELLED},
    TaskState.CANCELLED: set(),
}


class InvalidTaskTransitionError(Exception):
    """Raised when a task transition is not allowed."""


@dataclass(frozen=True)
class Task:
    """One declared step of a mission decomposition.

    `role` and `skills` are references to declarations; they grant
    nothing. Subtasks make the hierarchy explicit and inspectable.
    """
    task_id: str
    name: str
    description: str
    role: str
    skills: Tuple[str, ...] = ()
    subtasks: Tuple["Task", ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id or not self.name or not self.role:
            raise ValueError("task id, name, and role are required")

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "role": self.role,
            "skills": list(self.skills),
            "subtasks": [s.to_dict() for s in self.subtasks],
        }

    def walk(self) -> List["Task"]:
        """Depth-first, deterministic flattening of the subtree."""
        out = [self]
        for child in self.subtasks:
            out.extend(child.walk())
        return out


@dataclass
class TaskPlan:
    """A deterministic task tree plus its observable state.

    Orchestration metadata only: marking tasks never executes anything
    and never affects the QualityGate.
    """
    root: Task
    states: Dict[str, TaskState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for task in self.root.walk():
            self.states.setdefault(task.task_id, TaskState.PENDING)

    def tasks(self) -> List[Task]:
        return self.root.walk()

    def state_of(self, task_id: str) -> TaskState:
        return self.states[task_id]

    def mark(self, task_id: str, state: TaskState) -> None:
        """Apply a validated transition (declaration only)."""
        if task_id not in self.states:
            raise KeyError(f"unknown task: {task_id!r}")
        if not isinstance(state, TaskState):
            raise ValueError("state must be a TaskState")
        current = self.states[task_id]
        if state == current:
            return
        if state not in _TASK_TRANSITIONS[current]:
            raise InvalidTaskTransitionError(
                f"task {task_id}: {current.value} -> {state.value} "
                f"not allowed")
        self.states[task_id] = state

    def active(self) -> List[Task]:
        return [t for t in self.tasks()
                if self.states[t.task_id] is TaskState.ACTIVE]

    def pending(self) -> List[Task]:
        return [t for t in self.tasks()
                if self.states[t.task_id] is TaskState.PENDING]

    def to_dict(self) -> Dict[str, object]:
        return {
            "root": self.root.to_dict(),
            "states": {k: v.value for k, v in sorted(self.states.items())},
        }


#: The generic defensive-coding pipeline (role + candidate skills).
_PIPELINE: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("investigate",
     "Locate the relevant implementation and evidence.",
     "investigator", ("read-file", "list-dir", "search-dir")),
    ("reproduce",
     "Execute the authorized verification test.",
     "test_analyst", ("run-test",)),
    ("remediate",
     "Propose a corrective change.",
     "remediation_planner", ("write-file",)),
    ("verify",
     "Establish whether the correction satisfies the proof obligation.",
     "verifier", ("read-file", "run-test")),
    ("validate",
     "Interpret persisted evidence and reconstruct the final state.",
     "evidence_analyst", ("read-file", "list-dir")),
)


def decompose_mission(mission: Mission) -> TaskPlan:
    """Deterministically decompose a mission into a task plan.

    Descriptive only: this is orchestration metadata, not a planner.
    The same mission always yields the same tree (ids derive from the
    mission id and step names).
    """
    subtasks: List[Task] = []
    for name, description, role, skills in _PIPELINE:
        subtasks.append(Task(
            task_id=f"{mission.mission_id}::{name}",
            name=name,
            description=description,
            role=role,
            skills=skills,
        ))
    root = Task(
        task_id=f"{mission.mission_id}::mission",
        name=mission.mission_id,
        description=mission.description,
        role="evidence_analyst",
        skills=(),
        subtasks=tuple(subtasks),
    )
    return TaskPlan(root=root)


# -----------------------------------------------------------------------------
# Evidence contracts — declarations, not permissions
# -----------------------------------------------------------------------------

EVIDENCE_KINDS: Tuple[str, ...] = (
    "inspection", "test-execution", "remediation", "verification",
    "falsification", "analysis",
)


def evidence_contract(skill) -> Dict[str, object]:
    """Read a skill's declared evidence contract (read-only).

    Returns the skill's declared produced/consumed evidence kinds.
    This is documentation for the model and auditors — it does not
    create or mutate any evidence.
    """
    return {
        "skill_id": skill.id,
        "role": skill.role,
        "evidence_produced": list(skill.evidence_produced),
        "evidence_consumed": list(skill.evidence_consumed),
    }


__all__ = [
    "DEFAULT_ROLES",
    "EVIDENCE_KINDS",
    "InvalidTaskTransitionError",
    "Role",
    "RoleRegistry",
    "Task",
    "TaskPlan",
    "TaskState",
    "decompose_mission",
    "default_roles",
    "evidence_contract",
]
