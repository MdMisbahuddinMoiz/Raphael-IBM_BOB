"""tests.test_d12_2_trust_boundary — G16 fabricated-evidence refusal.

Proves QualityGate conditions C/D cannot be satisfied by a caller-injected
probe/regression record that is not causally bound to a real ALLOWed,
successful execution.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    ExecutionResult,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    create_run_dir,
    digest_id,
)
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.target_profile import TargetStore


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d122_tb_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _rid, run_dir = create_run_dir(self.tmp)
        self.ledger = EvidenceLedger(run_dir)
        self.addCleanup(self.ledger.close)
        self.gate = BOBQualityGate(self.ledger, target_store=TargetStore())
        self.mission = Mission(
            mission_id="M", description="d", scope="", criteria=["c"],
            problem={})

    def _evaluate(self):
        return self.gate.evaluate(GateInputs(
            mission=self.mission, findings=[], regression_ok=True,
            behavior_probe_ok=True))

    def _append(self, producer, payload):
        self.ledger.append_evidence(
            evidence_id=digest_id(payload, prefix=producer[:1].upper()),
            producer=producer, request_seq=payload.get("request_seq", 0),
            decision_seq=0, result_seq=payload.get("result_seq"),
            payload=payload)


class FabricatedEvidenceFails(_Base):
    def test_fake_probe_without_execution_fails_D(self):
        self._append("probe", {"kind": "probe", "allowed": True,
                               "request_seq": 0, "result_seq": None})
        self.assertIn("D:independent-behavior-probe",
                      list(self._evaluate().failed))

    def test_fake_regression_without_execution_fails_C(self):
        self._append("regression", {"kind": "regression", "result": "passed",
                                    "request_seq": 0, "result_seq": None})
        self.assertIn("C:regression", list(self._evaluate().failed))

    def test_probe_bound_to_nonexistent_request_fails_D(self):
        self._append("probe", {"kind": "probe", "allowed": True,
                               "request_seq": 999, "result_seq": 999})
        self.assertIn("D:independent-behavior-probe",
                      list(self._evaluate().failed))


class BoundEvidencePasses(_Base):
    def _allow_execution(self):
        req = ActionRequest(
            sequence=1, requester="t",
            capability=Capability.NETWORK_HTTP_REQUEST,
            target="http://127.0.0.1/flag", purpose="p")
        rseq = self.ledger.append_request(req)
        decision = PolicyDecision(
            sequence=1, decision=Decision.ALLOW, reason="ok",
            capability=req.capability, target=req.target)
        dseq = self.ledger.append_decision(rseq, decision)
        res = ExecutionResult(sequence=1, success=True, output="ok",
                              evidence={})
        resseq = self.ledger.append_result(
            request_seq=rseq, decision_seq=dseq, result=res)
        return rseq, dseq, resseq

    def test_real_probe_bound_to_allowed_execution_passes_D(self):
        rseq, _dseq, resseq = self._allow_execution()
        self._append("probe", {"kind": "probe", "allowed": True,
                               "request_seq": rseq, "result_seq": resseq})
        self.assertNotIn("D:independent-behavior-probe",
                         list(self._evaluate().failed))

    def test_real_regression_bound_to_allowed_execution_passes_C(self):
        rseq, _dseq, resseq = self._allow_execution()
        req2 = ActionRequest(
            sequence=2, requester="t", capability=Capability.RUN_TEST,
            target="test_x.py", purpose="p")
        rseq2 = self.ledger.append_request(req2)
        d2 = PolicyDecision(
            sequence=2, decision=Decision.ALLOW, reason="ok",
            capability=req2.capability, target=req2.target)
        self.ledger.append_decision(rseq2, d2)
        self._append("regression", {"kind": "regression", "result": "passed",
                                    "request_seq": rseq, "result_seq": resseq})
        self.assertNotIn("C:regression", list(self._evaluate().failed))

    def test_probe_bound_to_deny_fails_D(self):
        req = ActionRequest(
            sequence=1, requester="t",
            capability=Capability.NETWORK_HTTP_REQUEST,
            target="http://127.0.0.1/flag", purpose="p")
        rseq = self.ledger.append_request(req)
        decision = PolicyDecision(
            sequence=1, decision=Decision.DENY, reason="no",
            capability=req.capability, target=req.target)
        self.ledger.append_decision(rseq, decision)
        self._append("probe", {"kind": "probe", "allowed": True,
                               "request_seq": rseq, "result_seq": None})
        self.assertIn("D:independent-behavior-probe",
                      list(self._evaluate().failed))


if __name__ == "__main__":
    unittest.main()
