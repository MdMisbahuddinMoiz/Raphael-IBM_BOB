"""Deterministic, non-executing D14 capability planning."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from raphael_ibm_bob.capability_registry import CapabilityRegistry, get_registry
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    PlanStep,
    plan_to_action_requests,
)
from raphael_ibm_bob.contracts import ActionRequest, Mission, Plan
from raphael_ibm_bob.d14_hypothesis import Hypothesis
from raphael_ibm_bob.d14_world_state import WorldState
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)
from raphael_ibm_bob.d14_world_state import initial_world_state

_LIFECYCLE_PRIORITY = {
    "CONFIRMED": 0,
    "CANDIDATE": 1,
    "UNKNOWN": 2,
    "CONFLICTED": 3,
    "REFUTED": 4,
}


class _Selector(Protocol):
    def select_and_compose(
        self,
        mission_type: str,
        mission_params: dict,
        facts: TargetFacts,
    ) -> ExecutionPlan:
        ...


@dataclass(frozen=True, slots=True)
class NextAction:
    """One ordered request proposal; it contains no policy decision."""

    request: ActionRequest
    plan_id: str
    step_id: str
    capability_id: str


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    """Deterministic planner output, not an authorization or verdict."""

    decision_id: str
    mission_id: str
    world_revision: int
    execution_plan: ExecutionPlan | None
    next_action: NextAction | None
    selected_capability_id: str | None
    rejected_capability_ids: tuple[str, ...]
    rationale_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    step: PlanStep
    request: ActionRequest
    hypothesis_id: str
    confidence_bps: int
    confidence_band: str
    expected_observation: str
    falsifier: str


class Planner:
    """Compose capability requests and select one without executing it."""

    def __init__(
        self,
        selector: _Selector | None = None,
        registry: CapabilityRegistry | None = None,
        mission_type: str = "web_enum",
        hypotheses: tuple[Hypothesis, ...] = (),
    ) -> None:
        self._registry = registry if registry is not None else get_registry()
        self._selector = (
            selector
            if selector is not None
            else CapabilitySelector(registry=self._registry)
        )
        self._mission_type = mission_type
        self._hypotheses = tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id))

    def plan_a(self, mission: Mission) -> Plan:
        """Adapt the D14 selection decision to the existing Plan seam."""
        state = initial_world_state(mission, _facts_from_mission(mission))
        decision = self.plan(state)
        next_action = decision.next_action
        if next_action is None:
            raise ValueError(
                f"D14 selected no capability for mission type {self._mission_type!r}"
            )
        return Plan(
            plan_id=next_action.plan_id,
            mission_id=mission.mission_id,
            steps=[next_action.request],
        )

    def plan(self, world_state: WorldState) -> SelectionDecision:
        """Return the deterministic next request proposal for ``world_state``."""
        execution_plan = self._selector.select_and_compose(
            self._mission_type,
            {"mission_id": world_state.mission_id, "target": world_state.target_id},
            world_state.facts,
            credential_refs=world_state.facts.credential_refs,
        )
        requests = plan_to_action_requests(
            execution_plan,
            registry=self._registry,
            requester="planner",
        )
        ordered_steps = execution_plan.ordered_steps()
        hypotheses = self._hypotheses or tuple(
            sorted(
                (
                    value
                    for value in world_state.hypotheses.values()
                    if isinstance(value, Hypothesis)
                ),
                key=lambda item: item.hypothesis_id,
            ),
        )
        candidates = tuple(
            _Candidate(
                step=step,
                request=request,
                hypothesis_id=hypothesis.hypothesis_id,
                confidence_bps=hypothesis.confidence_bps,
                confidence_band=hypothesis.confidence_band,
                expected_observation=hypothesis.expected_observation,
                falsifier=hypothesis.falsifier,
            )
            for step, request, hypothesis in (
                (step, request, self._hypothesis_for(step, hypotheses))
                for step, request in zip(ordered_steps, requests, strict=True)
            )
        )
        observed_capabilities = {
            observation.capability_id.lower()
            for observation in world_state.observations
        }
        candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.step.capability_id.lower() not in observed_capabilities
        )
        if not candidates:
            return self._decision(
                world_state,
                execution_plan,
                None,
                (),
                ("NO_APPLICABLE_CAPABILITY",),
                (),
            )

        winner = min(candidates, key=_selection_order_key)
        rejected = tuple(
            sorted(
                candidate.step.capability_id
                for candidate in candidates
                if candidate is not winner
            ),
        )
        next_action = NextAction(
            request=winner.request,
            plan_id=execution_plan.plan_id,
            step_id=winner.step.step_id,
            capability_id=winner.step.capability_id,
        )
        return self._decision(
            world_state,
            execution_plan,
            next_action,
            winner,
            ("SELECTED_CAPABILITY",),
            tuple(_selection_order_key(candidate) for candidate in candidates),
        )

    def _hypothesis_for(
        self,
        step: PlanStep,
        hypotheses: tuple[Hypothesis, ...],
    ) -> Hypothesis:
        for hypothesis in hypotheses:
            if any(
                action.capability.name == step.capability_id
                for action in hypothesis.test_actions
            ):
                return hypothesis
        return Hypothesis(
            hypothesis_id=step.step_id,
            subject_ref=step.params.get("target", ""),
            predicate="capability_step",
            value=True,
            test_actions=(),
            expected_observation="",
            falsifier="",
            confidence_bps=0,
            confidence_band="UNKNOWN",
        )

    @staticmethod
    def _decision(
        world_state: WorldState,
        execution_plan: ExecutionPlan,
        next_action: NextAction | None,
        selected: _Candidate | tuple[()],
        rationale_codes: tuple[str, ...],
        candidate_keys: tuple[tuple[object, ...], ...],
    ) -> SelectionDecision:
        selected_capability_id = (
            selected.step.capability_id
            if isinstance(selected, _Candidate)
            else None
        )
        rejected_capability_ids = (
            ()
            if selected_capability_id is None
            else tuple(
                sorted(
                    step.capability_id
                    for step in execution_plan.ordered_steps()
                    if step.capability_id != selected_capability_id
                ),
            )
        )
        identity = _canonical_json(
            {
                "mission_id": world_state.mission_id,
                "world_revision": world_state.revision,
                "plan_id": execution_plan.plan_id,
                "selected": selected_capability_id,
                "rejected": rejected_capability_ids,
                "rationale": rationale_codes,
                "candidates": tuple(sorted(candidate_keys)),
            },
        )
        decision_id = f"SD-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
        return SelectionDecision(
            decision_id=decision_id,
            mission_id=world_state.mission_id,
            world_revision=world_state.revision,
            execution_plan=execution_plan,
            next_action=next_action,
            selected_capability_id=selected_capability_id,
            rejected_capability_ids=rejected_capability_ids,
            rationale_codes=rationale_codes,
        )


def _canonical_json(value: object) -> str:  # noqa: ANN401, OBJECT_OK - canonical JSON input.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _selection_order_key(candidate: _Candidate) -> tuple[object, ...]:  # noqa: ANN401, OBJECT_OK
    return (
        _LIFECYCLE_PRIORITY[candidate.confidence_band],
        candidate.confidence_bps,
        candidate.hypothesis_id,
        candidate.step.capability_id,
        _canonical_json(candidate.step.params),
        _canonical_json(candidate.expected_observation),
        _canonical_json(candidate.falsifier),
    )


def _facts_from_mission(mission: Mission) -> TargetFacts:
    """Build normalized D14 facts from the mission's declared target data."""
    problem = mission.problem
    host = str(problem.get(
        "target_host", problem.get("host", problem.get("symptom_target", "workspace")),
    ))
    protocol = str(problem.get(
        "protocol", "file" if "symptom_target" in problem else "http",
    ))
    port = int(problem.get(
        "target_port", {"http": 80, "https": 443, "telnet": 23}.get(protocol, 0),
    ))
    facts = TargetFacts(
        target_id=str(problem.get("target_id", host)),
        host=host,
        mission_id=mission.mission_id,
    )
    facts.add_service(ServiceRecord(host=host, port=port, protocol=protocol))
    if protocol != "file":
        facts.authorization = AuthorizationScope(
            target_host=host,
            authorized_protocols=frozenset({protocol}),
            authorized_ports=frozenset({port}),
            engagement_id=mission.mission_id,
            scope_document_ref=mission.scope,
        )
    return facts


__all__ = ["NextAction", "Planner", "SelectionDecision"]
