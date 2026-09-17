"""tests.test_b4_attestation — B4 Option-B attestation harness tests.

Synthetic data only. NO provider is executed.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from raphael_ibm_bob.b4_attestation import (
    ATTESTATION_SCOPE,
    EXPECTED_TOOL,
    FORBIDDEN_CLAIM,
    AttestationStatus,
    BoundaryToolCall,
    BoundaryToolResult,
    ProofSession,
    ProviderExecution,
    attest,
    canonical_path,
)

FIXTURE = canonical_path("/srv/raphael/fixtures/sink.bin")
MODULE = Path(
    __import__("raphael_ibm_bob.b4_attestation", fromlist=["x"]).__file__
)


def _proof(**over):
    base = dict(proof_session_id="PS-1", instance_id="INST-1",
                capability_id="C1A static_file_inspect", fixture_path=FIXTURE)
    base.update(over)
    return ProofSession(**base)


def _call(**over):
    base = dict(seq=1, session_id="PS-1", instance_id="INST-1", call_id="c1",
                tool=EXPECTED_TOOL, params={"path": FIXTURE})
    base.update(over)
    return BoundaryToolCall(**base)


def _result(**over):
    base = dict(seq=2, session_id="PS-1", instance_id="INST-1", call_id="c1",
                tool=EXPECTED_TOOL, ok=True, result_hash="h1")
    base.update(over)
    return BoundaryToolResult(**base)


def _execution(**over):
    base = dict(execution_id="x1", session_id="PS-1", instance_id="INST-1",
                tool=EXPECTED_TOOL, call_id="c1", path=FIXTURE,
                result_hash="h1")
    base.update(over)
    return ProviderExecution(**base)


class B4Attestation(unittest.TestCase):
    def test_1_valid_single_invocation(self):
        res = attest(_proof(), [_call()], [_result()], [_execution()])
        self.assertIs(res.status, AttestationStatus.ATTESTED)
        self.assertTrue(res.ok)
        self.assertFalse(res.quarantined)
        self.assertEqual(res.failures, [])

    def test_2_wrong_tool(self):
        res = attest(_proof(), [_call(tool="read_file")],
                     [_result(tool="read_file")], [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("tool-name-equality", res.failures)
        self.assertTrue(res.quarantined)

    def test_3_wrong_path(self):
        res = attest(_proof(),
                     [_call(params={"path": "/srv/other/evil.bin"})],
                     [_result()],
                     [_execution(path="/srv/other/evil.bin")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("exact-path-literal", res.failures)

    def test_4_extra_tool_attempt(self):
        calls = [_call(),
                 _call(seq=3, call_id="c2", tool="shell_exec",
                       params={"cmd": "id"})]
        res = attest(_proof(), calls, [_result()],
                     [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("tool-name-equality", res.failures)

    def test_5_extra_provider_execution(self):
        executions = [_execution(),
                      _execution(execution_id="x2", call_id="c2")]
        res = attest(_proof(), [_call()], [_result()], executions)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("execution-count", res.failures)
        self.assertIn("event-execution-correlation", res.failures)

    def test_6_missing_provider_execution(self):
        res = attest(_proof(), [_call()], [_result()], [])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("execution-observed", res.failures)
        self.assertIn("execution-count", res.failures)

    def test_7_result_mismatch(self):
        res = attest(_proof(), [_call()], [_result(result_hash="h1")],
                     [_execution(result_hash="hX")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("result-hash-correlation", res.failures)

    def test_8_session_mismatch(self):
        res = attest(_proof(), [_call()], [_result()],
                     [_execution(session_id="PS-2")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("single-proof-session", res.failures)

    def test_9_shared_instance_contamination(self):
        res = attest(_proof(), [_call()], [_result()],
                     [_execution(instance_id="INST-2")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("dedicated-instance", res.failures)

    def test_10_unknown_name_attempt(self):
        calls = [_call(),
                 _call(seq=5, call_id="c9", tool="unknown_tool",
                       params={"path": FIXTURE})]
        res = attest(_proof(), calls, [_result(), _result(seq=6, call_id="c9")],
                     [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("tool-name-equality", res.failures)

    def test_11_duplicate_replay_execution(self):
        executions = [_execution(), _execution()]  # same id/call_id
        res = attest(_proof(), [_call()], [_result()], executions)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("no-duplicate-execution", res.failures)

    def test_12_post_hoc_honesty(self):
        res = attest(_proof(), [_call()], [_result()], [_execution()])
        self.assertTrue(res.post_hoc)
        self.assertFalse(res.prevented)
        self.assertIn("DETECTS", res.evidence["honesty"])
        self.assertIn("does NOT PREVENT", res.evidence["honesty"])
        self.assertEqual(res.evidence["scope"], ATTESTATION_SCOPE)
        self.assertEqual(res.evidence["forbidden_claim_not_made"],
                         FORBIDDEN_CLAIM)
        # The stronger claim is never asserted.
        self.assertNotIn(FORBIDDEN_CLAIM, str(res.to_dict()["status"]))

    def test_no_boundary_events_is_invalid(self):
        res = attest(_proof(), [], [], [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("boundary-tool-call-observed", res.failures)

    def test_authority_boundary_no_gate_or_finding_imports(self):
        src = MODULE.read_text(encoding="utf-8")
        for token in ("quality_gate", "GateVerdict", "from raphael_ibm_bob."
                      "finding", "from raphael_ibm_bob.verifier",
                      "from raphael_ibm_bob.broker",
                      "from raphael_ibm_bob.policy"):
            self.assertNotIn(token, src)
        res = attest(_proof(), [_call()], [_result()], [_execution()])
        for forbidden_key in ("authorization", "verified", "refuted",
                              "gate", "verdict", "complete"):
            self.assertNotIn(forbidden_key, res.to_dict())


    # --- B4 corrective closure: H1/H2/H3/H4 adversarial cases ---

    def test_13_double_valid_one_execution(self):
        # Attack A / Muse case 1: 2 calls + 2 results + 1 execution.
        calls = [_call(), _call(seq=3, call_id="c2")]
        results = [_result(), _result(seq=4, call_id="c2")]
        res = attest(_proof(), calls, results, [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("call-count", res.failures)
        self.assertIn("call-execution-correlation", res.failures)

    def test_14_double_valid_two_executions(self):
        # Attack B / Muse case 2: exactly-one semantics for the first proof.
        calls = [_call(), _call(seq=3, call_id="c2")]
        results = [_result(), _result(seq=4, call_id="c2")]
        executions = [_execution(),
                      _execution(execution_id="x2", call_id="c2")]
        res = attest(_proof(), calls, results, executions)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("call-count", res.failures)

    def test_15_duplicate_call_id_divergence(self):
        # Attack H / Muse case 3: same call_id reused with divergent payload.
        calls = [_call(), _call(seq=3, call_id="c1")]
        res = attest(_proof(), calls, [_result()], [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("no-duplicate-execution", res.failures)
        self.assertIn("call-result-correlation", res.failures)

    def test_16_empty_proof_session_id(self):
        # Attack F / Muse case 4.
        res = attest(_proof(proof_session_id=""),
                     [_call(session_id="")], [_result(session_id="")],
                     [_execution(session_id="")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("proof-session-id-nonempty", res.failures)

    def test_17_empty_instance_id(self):
        # Attack G / Muse case 5 (whitespace-only).
        res = attest(_proof(instance_id="   "),
                     [_call(instance_id="   ")], [_result(instance_id="   ")],
                     [_execution(instance_id="   ")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("instance-id-nonempty", res.failures)

    def test_18_one_sided_hash_execution_only(self):
        # Muse case 6: execution hash present, result hash absent.
        res = attest(_proof(), [_call()], [_result(result_hash=None)],
                     [_execution(result_hash="h1")])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("result-hash-correlation", res.failures)

    def test_19_one_sided_hash_result_only(self):
        # Muse case 7: result hash present, execution hash absent.
        res = attest(_proof(), [_call()], [_result(result_hash="h1")],
                     [_execution(result_hash=None)])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("result-hash-correlation", res.failures)

    def test_20_non_canonical_fixture_path(self):
        # Muse case 8: fixture literal must already be canonical.
        bad = "/srv/raphael/../raphael/fixtures/sink.bin"
        res = attest(_proof(fixture_path=bad),
                     [_call(params={"path": bad})], [_result()],
                     [_execution(path=bad)])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("fixture-path-canonical-absolute", res.failures)

    def test_21_path_none_execution(self):
        # Attack E / Muse case 9: a None path must not bypass exact match.
        res = attest(_proof(), [_call()], [_result()],
                     [_execution(path=None)])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("exact-path-literal", res.failures)

    def test_22_extra_result(self):
        # Attack C: 1 call + 2 results + 1 execution.
        results = [_result(), _result(seq=4, call_id="c2")]
        res = attest(_proof(), [_call()], results, [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("result-count", res.failures)

    def test_23_extra_execution(self):
        # Attack D: 1 call + 1 result + 2 executions.
        executions = [_execution(),
                      _execution(execution_id="x2", call_id="c2")]
        res = attest(_proof(), [_call()], [_result()], executions)
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("execution-count", res.failures)

    def test_24_missing_boundary_result(self):
        res = attest(_proof(), [_call()], [], [_execution()])
        self.assertIs(res.status, AttestationStatus.INVALID)
        self.assertIn("tool-result-observed", res.failures)

    def test_25_capability_declared_wording(self):
        res = attest(_proof(), [_call()], [_result()], [_execution()])
        names = [c.name for c in res.checks]
        self.assertIn("capability-declared", names)
        self.assertNotIn("single-capability", names)


if __name__ == "__main__":
    unittest.main()
