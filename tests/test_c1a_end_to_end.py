"""tests.test_c1a_end_to_end — inert-provider governed C1A path.

CORRECTION 4/5: the inert provider double is test infrastructure. No real
T3MP3ST provider is executed and no M1/M2/M5 claim is made.
"""
from __future__ import annotations

import sys
import textwrap
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
from raphael_ibm_bob.contracts import (  # noqa: E402
    ActionRequest,
    Capability,
    Decision,
    GateVerdict,
)
from raphael_ibm_bob.evidence_ledger import digest_id  # noqa: E402
from raphael_ibm_bob.quality_gate import (  # noqa: E402
    BOBQualityGate,
    GateInputs,
)

_PASSING_TEST = textwrap.dedent('''
    import unittest


    class T(unittest.TestCase):
        def test_true(self):
            self.assertTrue(True)
''').strip() + "\n"


def _persist_probe(ledger, ok: bool):
    payload = {"kind": "probe", "result": "passed" if ok else "failed",
               "allowed": ok}
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix="PB"), producer="probe",
        request_seq=0, decision_seq=0, result_seq=None, payload=payload)


def _persist_regression(ledger, ok: bool):
    payload = {"kind": "regression", "result": "passed" if ok else "failed"}
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix="RG"), producer="regression",
        request_seq=0, decision_seq=0, result_seq=None, payload=payload)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(provider=CountingInertProvider(),
                                with_ledger=True)
        self.addCleanup(cleanup, self.stack.root)
        self.stack.mission = self.stack.mission.__class__(
            mission_id="M-c1a", description="c1a",
            scope=str(self.stack.root), criteria=["c1a criterion"])
        src = self.stack.root / "src"
        src.mkdir()
        self.test_file = src / "test_pass.py"
        self.test_file.write_text(_PASSING_TEST, encoding="utf-8")

    def _run_test(self):
        return self.stack.runtime.submit(ActionRequest(
            sequence=0, requester="runner", capability=Capability.RUN_TEST,
            target=str(self.test_file), purpose="required-test"),
            self.stack.mission)

    def _run_c1a(self):
        return self.stack.runtime.submit(
            c1a_request(self.stack.fixture, timeout=10.0),
            self.stack.mission)

    def test_full_governed_path_completes_via_gate(self):
        test_result = self._run_test()
        self.assertTrue(test_result.execution.success)
        c1a_result = self._run_c1a()
        self.assertIs(c1a_result.broker_result.decision.decision,
                      Decision.ALLOW)
        self.assertTrue(c1a_result.execution.success)

        _persist_probe(self.stack.ledger, ok=True)
        _persist_regression(self.stack.ledger, ok=True)
        gate = BOBQualityGate(self.stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=self.stack.mission, findings=[],
            regression_ok=True, behavior_probe_ok=True))
        self.assertIs(evaluation.verdict, GateVerdict.COMPLETE,
                      msg=f"failed={evaluation.failed} "
                          f"reasons={evaluation.reasons}")

    def test_unauthorized_c1a_is_denied(self):
        provider = self.stack.broker.c1a_provider
        result = self.stack.runtime.submit(
            c1a_request("/etc/hostname"), self.stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertEqual(provider.calls, 0)

    def test_provider_unavailable_refuses(self):
        # Default provider is the fail-closed T3MP3STAdapter.
        stack = make_stack(provider=None, with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        result = stack.runtime.submit(
            c1a_request(stack.fixture), stack.mission)
        self.assertIs(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertFalse(result.execution.success)
        # Gate cannot complete on an unsuccessful C1A attempt.
        gate = BOBQualityGate(stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[],
            regression_ok=False, behavior_probe_ok=False))
        self.assertIs(evaluation.verdict, GateVerdict.REFUSE)

    def test_c1a_evidence_is_present_and_untrusted(self):
        self._run_c1a()
        records = [r for r in self.stack.ledger.all_records()
                   if r.get("producer") == "provider"]
        self.assertTrue(records)
        self.assertTrue(all(r["payload"]["provider_untrusted"]
                            for r in records))


if __name__ == "__main__":
    unittest.main()
