from __future__ import annotations

import unittest
from itertools import permutations

from raphael_ibm_bob.capability_selector import PlanStep
from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.d14_planner import _Candidate, _selection_order_key
from tests.test_d15_applicability import _RANKING_TIERS


class D15RankingTests(unittest.TestCase):
    @staticmethod
    def _candidate(hypothesis_id: str,
                   capability_id: str) -> _Candidate:
        return _Candidate(
            step=PlanStep(
                step_id=f"step-{hypothesis_id}",
                capability_id=capability_id,
                params={"target": "198.51.100.15"},
            ),
            request=ActionRequest(
                sequence=0,
                requester="d15-test",
                capability=Capability.READ,
                target="198.51.100.15",
                purpose="descriptor-only test",
            ),
            hypothesis_id=hypothesis_id,
            confidence_bps=0,
            confidence_band="UNKNOWN",
            expected_observation="",
            falsifier="",
        )

    def test_ranking_tiers_are_hypothesis_ids_only(self) -> None:
        candidates = tuple(
            self._candidate(tier, f"D15-CAP-{index}")
            for index, tier in enumerate(reversed(_RANKING_TIERS))
        )
        self.assertNotIn("ranking", _Candidate.__dataclass_fields__)
        ordered = tuple(sorted(candidates, key=_selection_order_key))
        self.assertEqual(
            tuple(candidate.hypothesis_id for candidate in ordered),
            _RANKING_TIERS,
        )

    def test_ranking_is_deterministic_and_permutation_invariant(self) -> None:
        candidates = tuple(
            self._candidate(tier, f"D15-CAP-{index}")
            for index, tier in enumerate(_RANKING_TIERS)
        )
        expected = _RANKING_TIERS[0]
        for permutation in permutations(candidates):
            winner = min(permutation, key=_selection_order_key)
            self.assertEqual(winner.hypothesis_id, expected)


if __name__ == "__main__":
    unittest.main()
