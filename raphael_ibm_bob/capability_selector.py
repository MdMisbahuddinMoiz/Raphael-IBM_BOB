"""raphael_ibm_bob.capability_selector — D13 target-agnostic selection/composition.

Given a mission type (or explicit mission params) and ``TargetFacts``,
selects the matching capabilities, evaluates their prerequisites, and
composes an ordered ``ExecutionPlan``. ZERO target-specific branches —
the registry and the facts drive everything.

Authority boundary: the produced ``ExecutionPlan`` is a *proposal of
steps*. It grants nothing. To execute, each step is converted into an
ordinary ``ActionRequest`` by ``plan_to_action_requests`` (which routes
through the existing ``capability_fabric`` declaration seam) and then
submitted to Runtime -> Broker -> Policy. This module never executes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import CapabilityRegistry, get_registry
from raphael_ibm_bob.target_service_model import TargetFacts


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


@dataclass
class PlanStep:
    """One step in a composed plan (a proposal, not a request)."""
    step_id: str
    capability_id: str
    params: dict
    depends_on: list = field(default_factory=list)
    purpose: str = ""


@dataclass
class ExecutionPlan:
    """A composed plan of capability steps for a specific mission."""
    plan_id: str
    mission_id: str
    target_id: str
    mission_type: str = ""
    steps: list = field(default_factory=list)

    def add_step(self, capability_id: str, params: dict,
                 depends_on: Optional[list] = None, purpose: str = "") -> PlanStep:
        step = PlanStep(
            step_id=f"step_{len(self.steps) + 1}",
            capability_id=capability_id,
            params=params,
            depends_on=list(depends_on or []),
            purpose=purpose or capability_id,
        )
        self.steps.append(step)
        return step

    def ordered_steps(self) -> list:
        """Stable topological order by declared dependencies (deterministic)."""
        done: set = set()
        ordered: list = []
        remaining = list(self.steps)
        while remaining:
            progressed = False
            for step in list(remaining):
                if all(dep in done for dep in step.depends_on):
                    ordered.append(step)
                    done.add(step.step_id)
                    remaining.remove(step)
                    progressed = True
            if not progressed:
                # Cycle: fail deterministically rather than loop forever.
                raise ValueError("execution plan has a dependency cycle")
        return ordered


class CapabilitySelector:
    """Selects and composes capabilities from the registry and target facts."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None,
                 prerequisite_engine: Optional[PrerequisiteEngine] = None):
        self.registry = registry or get_registry()
        self.prerequisites = prerequisite_engine or PrerequisiteEngine()

    def select_and_compose(self, mission_type: str, mission_params: dict,
                           facts: TargetFacts,
                           credential_refs: Optional[list] = None
                           ) -> ExecutionPlan:
        """Produce an ExecutionPlan from facts. No target-specific logic."""
        mission_id = mission_params.get("mission_id", facts.mission_id or "")
        discovered = self.registry.discover_for_target(facts.to_facts())
        mission_relevant = [d for d in discovered
                            if mission_type in d.mission_types]

        capability_ids = sorted(d.capability_id for d in mission_relevant)

        plan = ExecutionPlan(
            plan_id=_derive_plan_id(mission_id, facts.target_id,
                                    mission_type, capability_ids),
            mission_id=mission_id,
            target_id=facts.target_id,
            mission_type=mission_type,
        )
        if not mission_relevant:
            return plan

        results = self.prerequisites.batch_evaluate(
            mission_relevant, facts, credential_refs or [])

        ready = [(d, r) for d, r in zip(mission_relevant, results) if r.satisfied]
        pending = [(d, r) for d, r in zip(mission_relevant, results)
                   if not r.satisfied]

        for descriptor, _result in ready:
            plan.add_step(
                capability_id=descriptor.capability_id,
                params=self._derive_params(descriptor, facts, mission_params),
                purpose=descriptor.description,
            )

        for descriptor, result in pending:
            self._add_prerequisite_steps(plan, descriptor, result, facts,
                                         mission_params)
        return plan

    def _derive_params(self, descriptor, facts: TargetFacts,
                       mission_params: dict) -> dict:
        service = facts.get_service(descriptor.protocol)
        params: dict = {"host": facts.host, "protocol": descriptor.protocol}
        if service:
            params["port"] = service.port
            if service.version:
                params["service_version"] = service.version
        # A concrete target wins if supplied by the mission/caller.
        if mission_params.get("target"):
            params["target"] = mission_params["target"]
        elif descriptor.protocol in ("http", "https"):
            scheme = descriptor.protocol
            port = params.get("port") or (443 if scheme == "https" else 80)
            path = mission_params.get("path", "")
            params["target"] = f"{scheme}://{facts.host}:{port}{path}"
        elif descriptor.protocol == "telnet":
            port = params.get("port") or 23
            params["target"] = f"telnet://{facts.host}:{port}"
        else:
            params["target"] = facts.host
        for key, value in mission_params.items():
            if key not in ("mission_id", "target"):
                params.setdefault(key, value)
        return params

    def _add_prerequisite_steps(self, plan: ExecutionPlan, descriptor,
                                result, facts: TargetFacts,
                                mission_params: dict) -> None:
        """For a capability that is not ready, add prerequisite-gathering
        steps using another registered capability when one exists."""
        for missing in result.missing:
            if not missing.startswith("credential"):
                continue
            for candidate in self.registry.all_capabilities():
                if candidate.capability_id == descriptor.capability_id:
                    continue
                if "credential" not in (
                        candidate.protocol + " "
                        + candidate.description).lower():
                    continue
                prereq = self.prerequisites.evaluate(candidate, facts)
                if prereq.satisfied:
                    plan.add_step(
                        capability_id=candidate.capability_id,
                        params=self._derive_params(candidate, facts,
                                                   mission_params),
                        depends_on=[s.step_id for s in plan.steps],
                        purpose=(f"Prerequisite for "
                                 f"{descriptor.capability_id}: {missing}"),
                    )
                    break

    def replan(self, existing_plan: ExecutionPlan, facts: TargetFacts,
               new_observations: list,
               credential_refs: Optional[list] = None) -> ExecutionPlan:
        """Recompose when observations change (new service/credential)."""
        from raphael_ibm_bob.target_service_model import ServiceRecord
        for obs in new_observations:
            if obs.get("type") == "service_discovery":
                facts.add_service(ServiceRecord(
                    host=obs.get("host", facts.host),
                    port=int(obs.get("port", 0)),
                    protocol=obs.get("protocol", ""),
                    state=obs.get("state", "open"),
                    source="prior_observation",
                ))
        mission_type = existing_plan.mission_type or "unknown"
        return self.select_and_compose(
            mission_type=mission_type,
            mission_params={"mission_id": existing_plan.mission_id},
            facts=facts,
            credential_refs=credential_refs,
        )


def _derive_plan_id(mission_id: str, target_id: str, mission_type: str,
                    capability_ids: list) -> str:
    """Deterministic plan id — same inputs => same id (repo convention)."""
    digest = hashlib.sha256(_canonical({
        "mission_id": mission_id,
        "target_id": target_id,
        "mission_type": mission_type,
        "capabilities": list(capability_ids),
    }).encode("utf-8")).hexdigest()
    return f"DP-{digest[:12]}"


def plan_to_action_requests(plan: ExecutionPlan, *, fabric=None,
                            registry=None,
                            requester: str = "selector") -> list:
    """Convert a plan's steps into ordinary ActionRequests.

    This is the governed bridge. It resolves each step's capability through
    the EXISTING ``capability_fabric`` (declaration seam) and asks the
    provider to prepare the request. The requests carry no authority; they
    must still be submitted to Runtime -> Broker -> Policy. A capability
    with no corresponding governed enum (e.g. SSH before it is implemented)
    fails closed rather than being executed.

    When a D13 ``registry`` is supplied, every step's capability must be one
    the registry actually knows about; a plan step naming an unregistered
    capability fails closed instead of being translated. This binds the
    bridge to the fabric's own capability set rather than to the whole
    ``Capability`` enum.
    """
    from raphael_ibm_bob.capability_fabric import default_fabric
    from raphael_ibm_bob.contracts import Capability

    fabric = fabric or default_fabric()
    requests = []
    for step in plan.ordered_steps():
        try:
            capability = Capability[step.capability_id]
        except KeyError:
            raise ValueError(
                f"capability {step.capability_id!r} has no governed "
                f"Capability enum binding; refusing to build a request "
                f"(fail closed)")
        if registry is not None and not registry.has(step.capability_id):
            raise ValueError(
                f"plan step {step.step_id} names capability "
                f"{step.capability_id!r}, which is not registered in the "
                f"D13 capability registry; refusing to build a request "
                f"(fail closed)")
        target = step.params.get("target")
        if not target:
            raise ValueError(
                f"plan step {step.step_id} ({step.capability_id}) has no "
                f"concrete target; refusing to build an ambiguous request")
        provider = fabric.resolve(capability)
        requests.append(provider.build_action_request(
            capability,
            target,
            purpose=step.purpose,
            requester=requester,
            plan_id=plan.plan_id,
        ))
    return requests


__all__ = [
    "CapabilitySelector",
    "ExecutionPlan",
    "PlanStep",
    "plan_to_action_requests",
]
