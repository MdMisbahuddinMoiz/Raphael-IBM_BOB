from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.d14_world_state import (
    EndpointBand,
    EvidenceBinding,
    ObservationUpdate,
    WorldState,
    initial_world_state,
    reduce_world_state,
)
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.target_service_model import TargetFacts


def _state() -> WorldState:
    mission = Mission(mission_id="M-1", description="d", scope="s")
    facts = TargetFacts(target_id="T-1", host="198.51.100.10")
    return initial_world_state(mission, facts)


@dataclass(frozen=True, slots=True)
class _LedgerView:
    bindings: dict[str, EvidenceBinding]

    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        return self.bindings.get(evidence_id)


def _ledger_view(
    evidence_id: str = "evidence-1",
    *,
    policy_decision: str = "allow",
    result_success: bool = True,
    session_id: str | None = "session-1",
) -> _LedgerView:
    return _LedgerView({
        evidence_id: EvidenceBinding(
            evidence_id=evidence_id,
            request_seq=1,
            policy_decision=policy_decision,
            result_success=result_success,
            session_id=session_id,
        ),
    })


def _update(
    observation_id: str,
    observation_type: str,
    source_seq: int,
    *,
    evidence_id: str | None = "evidence-1",
    timestamp: float | None = None,
    session_id: str | None = "session-1",
    replan_requested: bool = False,
) -> ObservationUpdate:
    observation = ObservationRecord(
        observation_id=observation_id,
        capability_id="network_http_request",
        observation_type=observation_type,
        target_host="198.51.100.10",
        target_port=80,
        timestamp=time.time() if timestamp is None else timestamp,
        content_hash=f"hash-{observation_id}",
        provenance={} if session_id is None else {"session_id": session_id},
    )
    return ObservationUpdate(
        observation=observation,
        source_seq=source_seq,
        evidence_id=evidence_id,
        replan_requested=replan_requested,
    )


class D14WorldStateReducerTests(unittest.TestCase):
    def test_reachable_endpoint_is_candidate_without_service_fact(self) -> None:
        state = _state()

        updated = reduce_world_state(
            state, _update("obs-1", "tcp_reachable", source_seq=4), _ledger_view())

        self.assertEqual(updated.endpoints["198.51.100.10:80"], EndpointBand.CANDIDATE)
        self.assertEqual(updated.facts.services, [])

    def test_validated_http_response_confirms_and_adds_service(self) -> None:
        state = _state()

        updated = reduce_world_state(
            state, _update("obs-1", "http_response", source_seq=4), _ledger_view())

        self.assertEqual(updated.endpoints["198.51.100.10:80"], EndpointBand.CONFIRMED)
        self.assertEqual(len(updated.facts.services), 1)
        self.assertEqual(updated.facts.services[0].protocol, "http")
        self.assertEqual(updated.facts.services[0].port, 80)

    def test_refusal_without_prior_positive_evidence_is_refuted(self) -> None:
        updated = reduce_world_state(
            _state(), _update("obs-1", "connection_refused", source_seq=4), _ledger_view())

        self.assertEqual(updated.endpoints["198.51.100.10:80"], EndpointBand.REFUTED)
        self.assertEqual(updated.failure_count, 1)

    def test_refusal_after_reachability_is_conflicted(self) -> None:
        candidate = reduce_world_state(
            _state(), _update("obs-1", "tcp_reachable", source_seq=4), _ledger_view())

        conflicted = reduce_world_state(
            candidate,
            _update("obs-2", "connection_refused", source_seq=5),
            _ledger_view(),
        )

        self.assertEqual(
            conflicted.endpoints["198.51.100.10:80"],
            EndpointBand.CONFLICTED,
        )

    def test_duplicate_observation_id_is_ignored(self) -> None:
        state = reduce_world_state(
            _state(), _update("obs-1", "tcp_reachable", source_seq=4), _ledger_view())

        duplicate = reduce_world_state(
            state, _update("obs-1", "http_response", source_seq=5), _ledger_view())

        self.assertIs(duplicate, state)
        self.assertEqual(duplicate.revision, 1)
        self.assertEqual(duplicate.step_count, 1)
        self.assertEqual(duplicate.last_source_seq, 4)

    def test_hash_and_progress_token_ignore_observation_wall_clock(self) -> None:
        first = reduce_world_state(
            _state(), _update("obs-1", "http_response", source_seq=4, timestamp=time.time()), _ledger_view())
        second = reduce_world_state(
            _state(), _update("obs-1", "http_response", source_seq=4, timestamp=time.time() + 1.0), _ledger_view())

        self.assertEqual(first.world_state_hash, second.world_state_hash)
        self.assertEqual(first.progress_token, second.progress_token)

    def test_counters_never_become_negative(self) -> None:
        updated = reduce_world_state(
            _state(),
            _update(
                "obs-1",
                "failed",
                source_seq=-10,
                replan_requested=True,
            ),
            _ledger_view(),
        )

        self.assertGreaterEqual(updated.revision, 0)
        self.assertGreaterEqual(updated.last_source_seq, 0)
        self.assertGreaterEqual(updated.step_count, 0)
        self.assertGreaterEqual(updated.replan_count, 0)
        self.assertGreaterEqual(updated.failure_count, 0)

    def test_reducer_does_not_mutate_prior_snapshot_or_input_facts(self) -> None:
        state = _state()
        before_hash = state.world_state_hash
        before_services = list(state.facts.services)

        updated = reduce_world_state(
            state, _update("obs-1", "http_response", source_seq=4), _ledger_view())

        self.assertEqual(state.world_state_hash, before_hash)
        self.assertEqual(state.facts.services, before_services)
        self.assertEqual(state.endpoints, {})
        self.assertEqual(state.observations, ())
        self.assertEqual(len(updated.facts.services), 1)
        self.assertIsNot(updated.facts, state.facts)

    def test_missing_evidence_id_is_rejected_without_state_change(self) -> None:
        state = _state()

        with self.assertRaises(ValueError):
            reduce_world_state(
                state,
                _update("obs-missing", "http_response", source_seq=4, evidence_id=None),
                _ledger_view(),
            )

        self.assertEqual(state.revision, 0)
        self.assertEqual(state.facts.services, [])
        self.assertEqual(state.endpoints, {})

    def test_unresolvable_evidence_id_is_rejected_without_state_change(self) -> None:
        state = _state()

        with self.assertRaises(ValueError):
            reduce_world_state(
                state,
                _update("obs-unknown", "http_response", source_seq=4),
                _LedgerView({}),
            )

        self.assertEqual(state.revision, 0)
        self.assertEqual(state.facts.services, [])
        self.assertEqual(state.endpoints, {})

    def test_stale_observation_is_rejected_without_state_change(self) -> None:
        state = _state()

        with self.assertRaises(ValueError):
            reduce_world_state(
                state,
                _update("obs-stale", "http_response", source_seq=4, timestamp=1.0),
                _ledger_view(),
            )

        self.assertEqual(state.revision, 0)
        self.assertEqual(state.facts.services, [])
        self.assertEqual(state.endpoints, {})


if __name__ == "__main__":
    unittest.main()
