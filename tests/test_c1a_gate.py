"""tests.test_c1a_gate — C1A evidence cannot complete a mission."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    CountingInertProvider,
    c1a_request,
    cleanup,
    make_stack,
)
from raphael_ibm_bob.contracts import GateVerdict  # noqa: E402
from raphael_ibm_bob.quality_gate import (  # noqa: E402
    BOBQualityGate,
    GateInputs,
)


class C1AEvidenceCannotComplete(unittest.TestCase):
    def _run_c1a(self):
        stack = make_stack(provider=CountingInertProvider(), with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.runtime.submit(c1a_request(stack.fixture), stack.mission)
        return stack

    def test_provider_evidence_alone_refuses(self):
        stack = self._run_c1a()
        gate = BOBQualityGate(stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[],
            regression_ok=True, behavior_probe_ok=True))
        self.assertIs(evaluation.verdict, GateVerdict.REFUSE)
        self.assertIn("B:required-tests", evaluation.failed)
        self.assertIn("D:independent-behavior-probe", evaluation.failed)

    def test_provider_evidence_is_not_a_test(self):
        stack = self._run_c1a()
        gate = BOBQualityGate(stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[],
            regression_ok=False, behavior_probe_ok=False))
        self.assertIn("B:required-tests", evaluation.failed)

    def test_gate_decision_is_recorded(self):
        stack = self._run_c1a()
        gate = BOBQualityGate(stack.ledger)
        gate.evaluate(GateInputs(
            mission=stack.mission, findings=[],
            regression_ok=True, behavior_probe_ok=True))
        gates = stack.ledger.gate_decisions()
        self.assertTrue(gates)
        self.assertEqual(gates[-1]["decision"], GateVerdict.REFUSE.value)

    def test_no_authority_in_provider_evidence(self):
        stack = self._run_c1a()
        for record in stack.ledger.all_records():
            if record.get("producer") == "provider":
                payload = record.get("payload", {})
                for key in ("verdict", "verified", "complete", "authorized",
                            "gate"):
                    self.assertNotIn(key, payload)


if __name__ == "__main__":
    unittest.main()
