"""tests.test_c1a_evidence — provider receipt -> governed evidence."""
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
from raphael_ibm_bob.c1a_evidence import (  # noqa: E402
    C1AEvidenceError,
    C1AEvidenceWriter,
    PROVIDER_UNTRUSTED,
    assert_no_authority,
    evidence_implies_complete,
    evidence_implies_verified,
    provider_result_to_execution,
)
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    ProviderState,
    invoke_governed,
)


class EvidenceConversion(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(provider=CountingInertProvider(),
                                with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        request = c1a_request(self.stack.fixture)
        decision = self.stack.policy.consult(request, self.stack.mission)
        self.binding = self.stack.auth.create_binding(
            decision=decision, request=request, run_id="r",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.request = request

    def _provider_result(self):
        return invoke_governed(CountingInertProvider(), self.binding.handoff,
                               self.request)

    def test_success_maps_to_success_execution(self):
        execution = provider_result_to_execution(
            self._provider_result(), sequence=7)
        self.assertTrue(execution.success)
        self.assertEqual(execution.output, ProviderState.SUCCESS.value)
        self.assertEqual(execution.sequence, 7)

    def test_evidence_is_marked_untrusted(self):
        execution = provider_result_to_execution(
            self._provider_result(), sequence=1)
        self.assertTrue(execution.evidence[PROVIDER_UNTRUSTED])

    def test_no_authority_implied(self):
        execution = provider_result_to_execution(
            self._provider_result(), sequence=1)
        self.assertFalse(evidence_implies_verified(execution.evidence))
        self.assertFalse(evidence_implies_complete(execution.evidence))

    def test_authority_keys_rejected(self):
        for key in ("verified", "COMPLETE", "verdict", "approved", "gate-pass",
                    "Severity", "confidence"):
            with self.assertRaises(C1AEvidenceError):
                assert_no_authority({"nested": {key: True}})

    def test_nested_authority_rejected(self):
        with self.assertRaises(C1AEvidenceError):
            assert_no_authority({"a": [{"b": {"verdict": "COMPLETE"}}]})


class EvidenceWriter(unittest.TestCase):
    def test_writer_appends_finding_linked_evidence(self):
        stack = make_stack(provider=CountingInertProvider(), with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        request = c1a_request(stack.fixture, finding_id="F-1")
        decision = stack.policy.consult(request, stack.mission)
        binding = stack.auth.create_binding(
            decision=decision, request=request, run_id="r",
            mission_id=stack.mission.mission_id,
            workspace_root=str(stack.root), timeout_seconds=10.0)
        result = invoke_governed(CountingInertProvider(), binding.handoff,
                                 request)
        writer = C1AEvidenceWriter(stack.ledger)
        evidence_id = writer.record(
            result, request_seq=1, decision_seq=2, result_seq=3,
            finding_id="F-1")
        self.assertTrue(evidence_id.startswith("X-"))
        linked = stack.ledger.records_for_finding("F-1")
        self.assertTrue(any(r.get("evidence_id") == evidence_id
                            for r in linked))
        rec = [r for r in linked if r.get("evidence_id") == evidence_id][0]
        self.assertEqual(rec["producer"], "provider")
        self.assertTrue(rec["payload"][PROVIDER_UNTRUSTED])


if __name__ == "__main__":
    unittest.main()
