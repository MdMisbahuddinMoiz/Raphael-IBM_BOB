"""tests.test_c1a_falsification — active contradiction search."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    CountingInertProvider,
    cleanup,
    make_stack,
)
from raphael_ibm_bob.c1a_falsification import (  # noqa: E402
    C1AFalsifier,
    FalsificationOutcome,
    contradiction_from_records,
    detect_contradiction,
)
from raphael_ibm_bob.c1a_verification import C1AVerifier  # noqa: E402
from raphael_ibm_bob.contracts import Finding, FindingState  # noqa: E402
from raphael_ibm_bob.finding import FindingStore  # noqa: E402


class ContradictionDetector(unittest.TestCase):
    def test_detect_contradiction(self):
        self.assertTrue(detect_contradiction("a", "b"))
        self.assertFalse(detect_contradiction("a", "a"))
        self.assertFalse(detect_contradiction(None, "a"))
        self.assertFalse(detect_contradiction("a", None))
        self.assertFalse(detect_contradiction(None, None))

    def test_contradiction_from_records(self):
        records = [
            {"payload": {"result_hash": "a"}},
            {"payload": {"result_hash": "a"}},
        ]
        self.assertIsNone(contradiction_from_records(records))
        records.append({"payload": {"result_hash": "b"}})
        self.assertIsNotNone(contradiction_from_records(records))


class Falsification(unittest.TestCase):
    def _verified_finding(self, stack):
        store = FindingStore(stack.ledger)
        finding = store.register(Finding(
            finding_id="F-c1a", state=FindingState.UNVERIFIED,
            summary="c1a", target=str(stack.fixture), evidence_ids=[]))
        C1AVerifier(stack.runtime, stack.ledger, store).verify(
            finding, stack.mission, expected_result_hash="test-hash")
        return store, store.get("F-c1a")

    def test_contradiction_refutes(self):
        provider = CountingInertProvider()
        stack = make_stack(provider=provider, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        store, finding = self._verified_finding(stack)
        provider._result_hash = "different-hash"
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge(
            finding, stack.mission, alternate_target=str(stack.other))
        self.assertIs(result.outcome, FalsificationOutcome.REFUTED)
        self.assertTrue(result.transition_applied)
        self.assertIs(store.get("F-c1a").state, FindingState.REFUTED)

    def test_no_contradiction_keeps_verified(self):
        stack = make_stack(provider=CountingInertProvider(), with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        store, finding = self._verified_finding(stack)
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge(
            finding, stack.mission, alternate_target=str(stack.other),
            expected_result_hash="test-hash")
        self.assertIs(result.outcome, FalsificationOutcome.NO_COUNTEREXAMPLE)
        self.assertIs(store.get("F-c1a").state, FindingState.VERIFIED)

    def test_provider_unavailable_is_inconclusive(self):
        stack = make_stack(provider=None, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        store = FindingStore(stack.ledger)
        finding = store.register(Finding(
            finding_id="F-c1a", state=FindingState.UNVERIFIED,
            summary="c1a", target=str(stack.fixture), evidence_ids=[]))
        store.transition("F-c1a", FindingState.VERIFIED)
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge(
            store.get("F-c1a"), stack.mission, expected_result_hash="x")
        self.assertIs(result.outcome, FalsificationOutcome.INCONCLUSIVE)

    def test_unverified_finding_not_challenged(self):
        stack = make_stack(provider=CountingInertProvider(), with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        store = FindingStore(stack.ledger)
        finding = store.register(Finding(
            finding_id="F-c1a", state=FindingState.UNVERIFIED,
            summary="c1a", target=str(stack.fixture), evidence_ids=[]))
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge(finding, stack.mission)
        self.assertIs(result.outcome, FalsificationOutcome.NO_COUNTEREXAMPLE)


if __name__ == "__main__":
    unittest.main()
