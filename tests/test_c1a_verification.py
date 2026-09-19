"""tests.test_c1a_verification — independent C1A reproduction."""
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
from raphael_ibm_bob.c1a_verification import (  # noqa: E402
    C1AVerifier,
    VerificationOutcome,
)
from raphael_ibm_bob.contracts import (  # noqa: E402
    Finding,
    FindingState,
)
from raphael_ibm_bob.finding import FindingStore  # noqa: E402


def _finding(stack):
    return Finding(
        finding_id="F-c1a",
        state=FindingState.UNVERIFIED,
        summary="c1a candidate",
        target=str(stack.fixture),
        evidence_ids=[],
    )


class Verification(unittest.TestCase):
    def _stack(self, provider=None, with_ledger=True):
        stack = make_stack(provider=provider or CountingInertProvider(),
                           with_ledger=with_ledger)
        self.addCleanup(cleanup, stack.root)
        return stack

    def test_matching_reproduction_verifies(self):
        stack = self._stack()
        store = FindingStore(stack.ledger)
        finding = store.register(_finding(stack))
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify(finding, stack.mission,
                                 expected_result_hash="test-hash")
        self.assertIs(result.outcome, VerificationOutcome.VERIFIED)
        self.assertTrue(result.transition_applied)
        self.assertIs(store.get("F-c1a").state, FindingState.VERIFIED)

    def test_hash_mismatch_is_inconclusive(self):
        stack = self._stack()
        store = FindingStore(stack.ledger)
        finding = store.register(_finding(stack))
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify(finding, stack.mission,
                                 expected_result_hash="other-hash")
        self.assertIs(result.outcome, VerificationOutcome.INCONCLUSIVE)
        self.assertFalse(result.transition_applied)
        self.assertIs(store.get("F-c1a").state, FindingState.UNVERIFIED)

    def test_no_expectation_is_inconclusive(self):
        stack = self._stack()
        store = FindingStore(stack.ledger)
        finding = store.register(_finding(stack))
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify(finding, stack.mission)
        self.assertIs(result.outcome, VerificationOutcome.INCONCLUSIVE)

    def test_provider_unavailable_is_inconclusive(self):
        # No c1a_provider -> default fail-closed T3MP3STAdapter.
        stack = make_stack(provider=None, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        store = FindingStore(stack.ledger)
        finding = store.register(_finding(stack))
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify(finding, stack.mission,
                                 expected_result_hash="test-hash")
        self.assertIs(result.outcome, VerificationOutcome.INCONCLUSIVE)
        self.assertIs(store.get("F-c1a").state, FindingState.UNVERIFIED)

    def test_verification_is_finding_linked(self):
        stack = self._stack()
        store = FindingStore(stack.ledger)
        finding = store.register(_finding(stack))
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        verifier.verify(finding, stack.mission,
                        expected_result_hash="test-hash")
        linked = stack.ledger.records_for_finding("F-c1a")
        self.assertTrue(any(r.get("producer") == "verifier" for r in linked))


if __name__ == "__main__":
    unittest.main()
