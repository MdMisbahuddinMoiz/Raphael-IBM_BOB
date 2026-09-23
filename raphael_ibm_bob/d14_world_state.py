# noqa: SIZE_OK — the frozen D14 reducer and additive D16 transition gate share one fold.
"""D14's canonical, deterministic world-state fold.

The reducer binds the existing ``TargetFacts`` and ``ServiceRecord`` models
from ``raphael_ibm_bob/target_service_model.py:22-80`` to the existing
``ObservationRecord`` contract from
``raphael_ibm_bob/observation_model.py:21-45``.  Mission identity is bound
from ``raphael_ibm_bob/contracts.py:297-325``; this module does not execute
capabilities or write evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Final

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.d14_state_codec import (
    canonical_state_payload,
    EvidenceBinding,
    ExecutionBinding,
    endpoint_key,
    next_band,
    ReadOnlyLedgerView,
    service_from_observation,
)
from raphael_ibm_bob.observation_model import ObservationRecord, ProvenanceValidator
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts


class EndpointBand(str, Enum):
    """Closed endpoint evidence bands used by the canonical state."""

    UNKNOWN = "unknown"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """Deterministic hypothesis record carried by ``WorldState``."""

    hypothesis_id: str
    statement: str
    status: str = "open"
    observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservationUpdate:
    """One normalized observation and its monotonic source sequence.

    The observation shape is the existing contract at
    ``raphael_ibm_bob/observation_model.py:21-45``.  ``evidence_id`` is
    required so ingestion can bind the observation to an ALLOWed, successful
    execution before deriving trust.
    """

    observation: ObservationRecord
    source_seq: int
    evidence_id: str | None
    replan_requested: bool = False
    service: ServiceRecord | None = None
    execution_binding: ExecutionBinding | None = None


@dataclass(frozen=True, slots=True)
class WorldState:
    """Immutable D14 snapshot bound to existing target facts.

    ``facts`` is the existing mutable ``TargetFacts`` model from
    ``raphael_ibm_bob/target_service_model.py:49-80``.  The reducer deep-copies
    it before calling its existing ``add_service`` method, so a prior snapshot
    is never mutated.  ``mission_id`` is the existing Mission identity from
    ``raphael_ibm_bob/contracts.py:297-325``.
    """

    mission_id: str
    target_id: str
    revision: int
    facts: TargetFacts
    endpoints: dict[str, EndpointBand]
    hypotheses: dict[str, Hypothesis]
    observations: tuple[ObservationRecord, ...]
    applied_observation_ids: frozenset[str]
    last_source_seq: int
    step_count: int
    replan_count: int
    failure_count: int
    progress_token: str
    world_state_hash: str


class StateTransitionError(ValueError):
    """Raised when a D16 observation cannot enter the transition fold."""


class StaleObservationError(StateTransitionError):
    """Raised when an observation is not newer than the folded state."""


@dataclass(frozen=True, slots=True)
class StateTransition:
    """Immutable D16 result carrying the exact state used for replanning."""

    previous: WorldState
    current: WorldState
    observation_id: str
    source_seq: int
    accepted: bool
    changed: bool
    reason: str


class _ObservationKind(str, Enum):
    REACHABLE = "reachable"
    HTTP_RESPONSE = "http_response"
    FAILURE = "failure"
    UNKNOWN = "unknown"


_REACHABLE_TYPES: Final = frozenset({"reachable", "port_open", "port_reachable", "tcp_open", "tcp_reachable"})
_FAILURE_TYPES: Final = frozenset({"connection_refused", "denied", "failed", "failure", "http_failed", "http_refused", "network_failure", "refusal", "refused", "request_failed", "tcp_failed", "tcp_refused", "timeout", "unavailable"})


def initial_world_state(mission: Mission, facts: TargetFacts) -> WorldState:
    """Create revision zero from a Mission and existing TargetFacts.

    The Mission contract is defined at ``raphael_ibm_bob/contracts.py:297-325``
    and the bound facts/service model at
    ``raphael_ibm_bob/target_service_model.py:49-80``.  Existing service facts
    start as confirmed endpoints; no observation timestamp participates in the
    derived hash or progress token.
    """
    copied_facts = copy.deepcopy(facts)
    copied_facts.mission_id = mission.mission_id
    endpoints = {
        endpoint_key(service.host, service.port): EndpointBand.CONFIRMED
        for service in copied_facts.services
    }
    return _build_state(
        mission_id=mission.mission_id,
        target_id=copied_facts.target_id,
        revision=0,
        facts=copied_facts,
        endpoints=endpoints,
        hypotheses={},
        observations=(),
        applied_observation_ids=frozenset(),
        last_source_seq=0,
        step_count=0,
        replan_count=0,
        failure_count=0,
    )


def reduce_world_state(
    state: WorldState,
    update: ObservationUpdate,
    ledger_view: ReadOnlyLedgerView,
) -> WorldState:
    """Fold one ObservationUpdate into a new deterministic WorldState.

    ``ObservationRecord`` is reused without duplication from
    ``raphael_ibm_bob/observation_model.py:21-45``.  Service insertion uses
    the existing ``TargetFacts.add_service`` seam at
    ``raphael_ibm_bob/target_service_model.py:76-80``.  Duplicate observation
    IDs return the prior snapshot unchanged.
    """
    binding = _validate_ingestion(update, ledger_view)
    observation_id = update.observation.observation_id
    if observation_id in state.applied_observation_ids:
        return state

    kind = _observation_kind(update)
    endpoint = endpoint_key(
        update.observation.target_host,
        update.observation.target_port,
    )
    current_band = state.endpoints.get(endpoint, EndpointBand.UNKNOWN)
    next_endpoint_band = EndpointBand(next_band(current_band, kind.value))
    copied_facts = copy.deepcopy(state.facts)
    if kind is _ObservationKind.HTTP_RESPONSE and binding.result_success:
        service = update.service or service_from_observation(update.observation)
        if service is not None:
            copied_facts.add_service(service)

    next_endpoints = dict(state.endpoints)
    next_endpoints[endpoint] = next_endpoint_band
    next_observations = (*state.observations, update.observation)
    next_applied_ids = frozenset((*state.applied_observation_ids, observation_id))
    prior_revision = max(0, state.revision)
    prior_step_count = max(0, state.step_count)
    prior_replan_count = max(0, state.replan_count)
    prior_failure_count = max(0, state.failure_count)
    source_seq = max(0, update.source_seq)
    next_failure_count = prior_failure_count + int(kind is _ObservationKind.FAILURE)
    next_replan_count = prior_replan_count + int(update.replan_requested)
    return _build_state(
        mission_id=state.mission_id,
        target_id=state.target_id,
        revision=prior_revision + 1,
        facts=copied_facts,
        endpoints=next_endpoints,
        hypotheses=dict(state.hypotheses),
        observations=next_observations,
        applied_observation_ids=next_applied_ids,
        last_source_seq=max(state.last_source_seq, source_seq, 0),
        step_count=prior_step_count + 1,
        replan_count=next_replan_count,
        failure_count=next_failure_count,
    )


def reduce_state_transition(
    state: WorldState,
    update: ObservationUpdate,
    ledger_view: ReadOnlyLedgerView,
) -> StateTransition:
    """Validate D16 association, then delegate to ``reduce_world_state``."""
    execution_binding = update.execution_binding
    if execution_binding is None:
        raise StateTransitionError("D16 execution binding is required")
    ledger_binding = _validate_ingestion(update, ledger_view)
    if update.evidence_id != execution_binding.observation_evidence_id:
        raise StateTransitionError("observation evidence_id does not match execution binding")
    if update.source_seq != execution_binding.result_seq:
        raise StateTransitionError("observation source sequence does not match execution result")
    if ledger_binding.request_seq != execution_binding.request_seq:
        raise StateTransitionError("observation evidence is bound to a different request")
    if (
        ledger_binding.decision_seq is not None
        and ledger_binding.decision_seq != execution_binding.decision_seq
    ):
        raise StateTransitionError("observation evidence is bound to a different decision")
    if (
        ledger_binding.result_seq is not None
        and ledger_binding.result_seq != execution_binding.result_seq
    ):
        raise StateTransitionError("observation evidence is bound to a different result")
    if ledger_binding.session_id != execution_binding.session_binding.session_id:
        raise StateTransitionError("observation evidence session differs from runtime binding")
    if update.observation.capability_id.casefold() != execution_binding.capability_id.casefold():
        raise StateTransitionError("observation capability does not match execution binding")
    if update.observation.observation_id in state.applied_observation_ids:
        return StateTransition(
            previous=state,
            current=state,
            observation_id=update.observation.observation_id,
            source_seq=update.source_seq,
            accepted=False,
            changed=False,
            reason="duplicate-observation",
        )
    if update.source_seq <= state.last_source_seq:
        raise StaleObservationError(
            f"observation source sequence {update.source_seq} is not newer than "
            f"state sequence {state.last_source_seq}",
        )
    changed_state = reduce_world_state(state, update, ledger_view)
    return StateTransition(
        previous=state,
        current=changed_state,
        observation_id=update.observation.observation_id,
        source_seq=update.source_seq,
        accepted=True,
        changed=changed_state.world_state_hash != state.world_state_hash,
        reason="observation-applied",
    )


def _validate_ingestion(
    update: ObservationUpdate,
    ledger_view: ReadOnlyLedgerView,
) -> EvidenceBinding:
    evidence_id = update.evidence_id
    if not evidence_id:
        raise StateTransitionError("observation evidence_id is required")
    binding = ledger_view.resolve_evidence(evidence_id)
    if binding is None:
        raise StateTransitionError(f"unresolvable observation evidence_id: {evidence_id}")
    if binding.evidence_id != evidence_id:
        raise StateTransitionError("ledger evidence binding id mismatch")
    if binding.policy_decision.lower() != "allow":
        raise StateTransitionError("observation evidence is not bound to Policy ALLOW")
    if not binding.result_success:
        raise StateTransitionError("observation evidence is not bound to a successful result")
    if not binding.session_id:
        raise StateTransitionError("observation evidence has no session binding")
    fresh, reason = ProvenanceValidator.validate_fresh(
        update.observation,
        binding.session_id,
    )
    if not fresh:
        raise StateTransitionError(f"invalid observation provenance: {reason}")
    return binding


def _observation_kind(update: ObservationUpdate) -> _ObservationKind:
    observation_type = update.observation.observation_type.strip().lower()
    if observation_type in _REACHABLE_TYPES:
        return _ObservationKind.REACHABLE
    if observation_type in {"http_response", "http_get", "network_response"}:
        return (
            _ObservationKind.HTTP_RESPONSE
        )
    if observation_type in _FAILURE_TYPES:
        return _ObservationKind.FAILURE
    return _ObservationKind.UNKNOWN


def _build_state(
    *,
    mission_id: str,
    target_id: str,
    revision: int,
    facts: TargetFacts,
    endpoints: dict[str, EndpointBand],
    hypotheses: dict[str, Hypothesis],
    observations: tuple[ObservationRecord, ...],
    applied_observation_ids: frozenset[str],
    last_source_seq: int,
    step_count: int,
    replan_count: int,
    failure_count: int,
) -> WorldState:
    payload = canonical_state_payload(
        mission_id=mission_id,
        target_id=target_id,
        revision=revision,
        facts=facts,
        endpoints=endpoints,
        hypotheses=hypotheses,
        observations=observations,
        applied_observation_ids=applied_observation_ids,
        last_source_seq=last_source_seq,
        step_count=step_count,
        replan_count=replan_count,
        failure_count=failure_count,
    )
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    world_state_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    progress_token = hashlib.sha256(
        ("progress:" + canonical).encode("utf-8"),
    ).hexdigest()
    return WorldState(
        mission_id=mission_id,
        target_id=target_id,
        revision=revision,
        facts=facts,
        endpoints=dict(endpoints),
        hypotheses=dict(hypotheses),
        observations=tuple(observations),
        applied_observation_ids=frozenset(applied_observation_ids),
        last_source_seq=last_source_seq,
        step_count=step_count,
        replan_count=replan_count,
        failure_count=failure_count,
        progress_token=progress_token,
        world_state_hash=world_state_hash,
    )


__all__ = [
    "EndpointBand",
    "EvidenceBinding",
    "ExecutionBinding",
    "Hypothesis",
    "ObservationUpdate",
    "ReadOnlyLedgerView",
    "StaleObservationError",
    "StateTransition",
    "StateTransitionError",
    "WorldState",
    "initial_world_state",
    "reduce_state_transition",
    "reduce_world_state",
]
