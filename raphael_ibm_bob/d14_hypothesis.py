"""Canonical D14 hypotheses as descriptive, non-authoritative records."""
from __future__ import annotations

from dataclasses import dataclass

from raphael_ibm_bob.contracts import ActionRequest
from raphael_ibm_bob.d14_world_state import (
    ObservationUpdate,
    ReadOnlyLedgerView,
    WorldState,
    reduce_world_state,
)
from raphael_ibm_bob.observation_model import ObservationRecord

_CONFIDENCE_BANDS = frozenset(
    {"UNKNOWN", "CANDIDATE", "CONFIRMED", "REFUTED", "CONFLICTED"},
)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """Descriptive claim metadata; it grants no authority to any subsystem."""

    hypothesis_id: str
    subject_ref: str
    predicate: str
    value: object  # noqa: ANN401, OBJECT_OK - canonical interface uses object.
    test_actions: tuple[ActionRequest, ...]
    expected_observation: str
    falsifier: str
    confidence_bps: int
    confidence_band: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_bps <= 10000:
            raise ValueError("confidence_bps must be between 0 and 10000")
        if self.confidence_band not in _CONFIDENCE_BANDS:
            raise ValueError("confidence_band is not a canonical D14 band")


class HypothesisStore:
    """In-memory descriptive hypothesis index with no authority side effects."""

    def __init__(self, hypotheses: tuple[Hypothesis, ...] = ()) -> None:
        by_id = {hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses}
        if len(by_id) != len(hypotheses):
            raise ValueError("hypothesis_id values must be unique")
        self._hypotheses = by_id

    def snapshot(self) -> tuple[Hypothesis, ...]:
        """Return hypotheses in canonical identifier order."""
        return tuple(self._hypotheses[key] for key in sorted(self._hypotheses))

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        """Return one descriptive hypothesis, if present."""
        return self._hypotheses.get(hypothesis_id)

    def apply_observation(
        self,
        world_state: WorldState,
        observation: ObservationUpdate | ObservationRecord,
        ledger_view: ReadOnlyLedgerView,
    ) -> WorldState:
        """Fold an observation through the existing world-state reducer only."""
        update = (
            observation
            if isinstance(observation, ObservationUpdate)
            else ObservationUpdate(
                observation=observation,
                source_seq=0,
                evidence_id=None,
            )
        )
        return reduce_world_state(world_state, update, ledger_view)


__all__ = ["Hypothesis", "HypothesisStore"]
