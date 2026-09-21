"""tests.test_provider_runtime — Phase 2C ProviderRuntime + adapter tests.

Synthetic only. NO provider execution. The pinned T3MP3ST provider is
absent; `T3MP3STAdapter` must fail closed (unavailable).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from raphael_ibm_bob.adapters.t3mp3st_adapter import (
    EXPOSED_TOOLS,
    InertProviderDouble,
    OutOfContractToolError,
    ProviderUnavailableError,
    T3MP3STAdapter,
)
from raphael_ibm_bob.b4_attestation import (
    AttestationStatus,
    BoundaryToolCall,
    BoundaryToolResult,
    ProviderExecution,
)
from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.provider_runtime import (
    C1A_CAPABILITY_ID,
    C1A_PROVIDER_ID,
    C1A_TOOL,
    ProviderState,
    ScopeHandoff,
    ScopeViolation,
    attest_result,
    fixture_digest,
    fixture_integrity_ok,
    invoke_governed,
    normalize_result,
    validate_scope,
)


def _tree(tc):
    base = Path(tempfile.mkdtemp(prefix="p2c_"))
    tc.addCleanup(shutil.rmtree, base, True)
    root = base / "fixture_root"
    root.mkdir()
    fx = root / "sink.bin"
    fx.write_bytes(b"RAPHAEL-FIXTURE-001\n")
    return base, root, fx


def _handoff(root, fx, **over):
    data = dict(run_id="run-1", proof_session_id="PS-1",
                mission_id="M-1", action_request_id="AR-1",
                invocation_id="INV-1",
                fixture_root=str(root), fixture_path=str(fx),
                capability_id=C1A_CAPABILITY_ID, provider_id=C1A_PROVIDER_ID,
                network_denied=True, timeout_seconds=5.0)
    data.update(over)
    return ScopeHandoff(**data)


def _request(target):
    return ActionRequest(sequence=0, requester="c1a",
                         capability=Capability.C1A_STATIC_FILE_INSPECT,
                         target=target,
                         purpose="c1a-proof")


class _SlowRuntime:
    provider_id = C1A_PROVIDER_ID

    def __init__(self, delay=0.2):
        self.delay = delay

    def invoke(self, handoff, request):
        time.sleep(self.delay)
        from raphael_ibm_bob.provider_runtime import normalize_result
        payload = {"results": [{"path": handoff.fixture_path,
                                "kind": "binary_sink_match"}],
                   "operation_id": "op"}
        return normalize_result(handoff, json.dumps(payload).encode())


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base, self.root, self.fx = _tree(self)
        self.handoff = _handoff(self.root, self.fx)
        self.request = _request(str(self.fx))

    # 1
    def test_1_allowed_c1a_success(self):
        result = invoke_governed(InertProviderDouble(),
                                 self.handoff, self.request)
        self.assertIs(result.state, ProviderState.SUCCESS)
        self.assertTrue(result.success)

    # 2
    def test_2_wrong_capability(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(_handoff(self.root, self.fx,
                                    capability_id="C9 other"), self.request)

    # 3
    def test_3_wrong_path(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(self.handoff, _request("/etc/hostname"))

    # 4
    def test_4_missing_scope(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(_handoff(self.root, self.fx, run_id=""),
                           self.request)

    # 5
    def test_5_directory_path(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(_handoff(self.root, self.fx, allow_directory=True),
                           self.request)
        with self.assertRaises(ScopeViolation):
            validate_scope(
                _handoff(self.root, self.fx, fixture_path=str(self.root)),
                _request(str(self.root)))

    # 6
    def test_6_network_enabled(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(_handoff(self.root, self.fx, network_denied=False),
                           self.request)

    # 7
    def test_7_output_overflow(self):
        many = [{"path": str(self.fx), "kind": "x"} for _ in range(3)]
        h = _handoff(self.root, self.fx, max_results=2)
        result = invoke_governed(InertProviderDouble(extra={"results": many}),
                                 h, self.request)
        self.assertIs(result.state, ProviderState.PARTIAL)
        self.assertFalse(result.success)
        # Byte cap -> failure, never success.
        small = _handoff(self.root, self.fx, max_response_bytes=8)
        result2 = normalize_result(small, b"x" * 64)
        self.assertIs(result2.state, ProviderState.FAILURE)

    # 8
    def test_8_timeout(self):
        h = _handoff(self.root, self.fx, timeout_seconds=0.05)
        result = invoke_governed(_SlowRuntime(delay=0.2), h, self.request)
        self.assertIs(result.state, ProviderState.TIMEOUT)
        self.assertFalse(result.success)
        self.assertFalse(result.cancellation_acknowledged)

    # 9
    def test_9_provider_unavailable(self):
        result = invoke_governed(T3MP3STAdapter(), self.handoff, self.request)
        self.assertIs(result.state, ProviderState.UNAVAILABLE)
        self.assertFalse(result.success)
        with self.assertRaises(ProviderUnavailableError):
            T3MP3STAdapter().invoke(self.handoff, self.request)
        self.assertEqual(EXPOSED_TOOLS, (C1A_TOOL,))
        with self.assertRaises(OutOfContractToolError):
            T3MP3STAdapter()._assert_in_contract("nmap_scan")

    # 10
    def test_10_malformed_provider_result(self):
        result = normalize_result(self.handoff, b"{not json")
        self.assertIs(result.state, ProviderState.FAILURE)

    # 11
    def test_11_authority_field_injection(self):
        for key in ("severity", "cwe", "verified", "COMPLETE", "approved",
                    "confidence", "verdict"):
            result = invoke_governed(
                InertProviderDouble(extra={key: "x"}), self.handoff,
                self.request)
            self.assertIs(result.state, ProviderState.FAILURE,
                          f"authority field {key!r} not rejected")
        result = normalize_result(self.handoff, b'{"a":1,"a":2}')
        self.assertIs(result.state, ProviderState.FAILURE)

    # 12
    def test_12_provenance_mismatch(self):
        result = invoke_governed(
            InertProviderDouble(extra={"operation_id": 123}),
            self.handoff, self.request)
        self.assertIs(result.state, ProviderState.DENIED)

    # 13
    def test_13_b4_mismatch(self):
        att = self._attest(path="/srv/other/evil.bin")
        self.assertIs(att.status, AttestationStatus.INVALID)

    # 14
    def test_14_extra_tool_attempt(self):
        calls = [self._call(), self._call(seq=3, call_id="c2", tool="shell")]
        att = attest_result(self.handoff, calls, [self._result()],
                            [self._exec()])
        self.assertIs(att.status, AttestationStatus.INVALID)

    # 15
    def test_15_extra_execution(self):
        att = attest_result(self.handoff, [self._call()],
                            [self._result()],
                            [self._exec(), self._exec(execution_id="x2",
                                                      call_id="c2")])
        self.assertIs(att.status, AttestationStatus.INVALID)

    # 16/17
    def test_16_fixture_integrity(self):
        pre = fixture_digest(str(self.fx))
        self.assertTrue(fixture_integrity_ok(pre, pre))
        self.fx.write_bytes(b"tampered")
        post = fixture_digest(str(self.fx))
        self.assertFalse(fixture_integrity_ok(pre, post))

    # 18
    def test_18_artifact_quarantine(self):
        ok = invoke_governed(
            InertProviderDouble(extra={"artifacts": ["ref://a"]}),
            self.handoff, self.request)
        self.assertEqual(ok.artifacts, ("ref://a",))  # refs only
        over = _handoff(self.root, self.fx, max_artifacts=1)
        bad = invoke_governed(
            InertProviderDouble(extra={"artifacts": ["a", "b"]}), over,
            self.request)
        self.assertIs(bad.state, ProviderState.FAILURE)

    # 19
    def test_19_session_mismatch(self):
        att = attest_result(self.handoff, [self._call()],
                            [self._result()],
                            [self._exec(session_id="PS-2")])
        self.assertIs(att.status, AttestationStatus.INVALID)

    # 20
    def test_20_provider_result_missing_path(self):
        result = invoke_governed(
            InertProviderDouble(extra={"results": [{"kind": "x"}]}),
            self.handoff, self.request)
        self.assertIs(result.state, ProviderState.DENIED)

    def test_valid_b4_attests(self):
        att = attest_result(self.handoff, [self._call()],
                            [self._result()], [self._exec()])
        self.assertIs(att.status, AttestationStatus.ATTESTED)

    def test_authority_boundary_no_gate_outputs(self):
        result = invoke_governed(InertProviderDouble(), self.handoff,
                                 self.request)
        for key in ("verified", "refuted", "complete", "verdict", "gate",
                    "authorized"):
            self.assertNotIn(key, result.to_dict())

    # --- Phase 2C hardening: J1-J6 ---

    def test_22_wrong_provider_id(self):
        with self.assertRaises(ScopeViolation):
            validate_scope(
                _handoff(self.root, self.fx, provider_id="decepticon"),
                self.request)

    def test_23_nested_authority_in_results(self):
        # J5: a nested object inside an ALLOWED result key must be rejected.
        result = invoke_governed(
            InertProviderDouble(extra={"results": [
                {"path": str(self.fx), "kind": {"severity": "critical"}}]}),
            self.handoff, self.request)
        self.assertIs(result.state, ProviderState.FAILURE)

    def test_24_artifact_value_and_byte_limit(self):
        # non-string artifact ref -> rejected
        bad = invoke_governed(
            InertProviderDouble(extra={"artifacts": [123]}),
            self.handoff, self.request)
        self.assertIs(bad.state, ProviderState.FAILURE)
        # J1: artifact byte budget exceeded -> non-success
        over = _handoff(self.root, self.fx, max_artifact_bytes=4)
        big = invoke_governed(
            InertProviderDouble(extra={"artifacts": ["ref://0123456789"]}),
            over, self.request)
        self.assertIs(big.state, ProviderState.FAILURE)

    def test_25_explicit_truncated_flag(self):
        result = invoke_governed(
            InertProviderDouble(extra={"truncated": True}),
            self.handoff, self.request)
        self.assertIs(result.state, ProviderState.PARTIAL)
        self.assertFalse(result.success)

    def test_26_normalized_authority_key(self):
        for key in ("Severity", "SEVERITY", "gate-pass", "veri fied",
                    "authorization"):
            result = invoke_governed(
                InertProviderDouble(extra={key: "x"}), self.handoff,
                self.request)
            self.assertIs(result.state, ProviderState.FAILURE,
                          f"normalized authority key {key!r} not rejected")

    def test_27_nan_invalid_limits(self):
        for bad in (float("nan"), float("inf"), float("-inf"), 0.0, -1.0,
                    "5"):
            with self.assertRaises(ScopeViolation):
                validate_scope(_handoff(self.root, self.fx,
                                        timeout_seconds=bad), self.request)
        for field in ("max_response_bytes", "max_results", "max_artifacts",
                      "max_artifact_bytes"):
            with self.assertRaises(ScopeViolation):
                validate_scope(_handoff(self.root, self.fx,
                                        **{field: float("nan")}),
                               self.request)

    def test_timeout_marks_orphan_possible(self):
        h = _handoff(self.root, self.fx, timeout_seconds=0.05)
        result = invoke_governed(_SlowRuntime(delay=0.2), h, self.request)
        self.assertTrue(result.orphan_possible)
        self.assertFalse(result.cancellation_acknowledged)
        self.assertFalse(result.success)

    def test_28_bool_numeric_bounds_rejected(self):
        # bools are not valid numeric limits (True/False must be rejected)
        for bad in (True, False):
            with self.assertRaises(ScopeViolation):
                validate_scope(_handoff(self.root, self.fx,
                                        timeout_seconds=bad), self.request)
            with self.assertRaises(ScopeViolation):
                validate_scope(_handoff(self.root, self.fx,
                                        max_results=bad), self.request)

    def test_29_orphan_possible_only_on_timeout(self):
        ok = invoke_governed(InertProviderDouble(), self.handoff,
                             self.request)
        self.assertFalse(ok.orphan_possible)
        failure = invoke_governed(
            InertProviderDouble(extra={"severity": "x"}), self.handoff,
            self.request)
        self.assertIs(failure.state, ProviderState.FAILURE)
        self.assertFalse(failure.orphan_possible)
        unavailable = invoke_governed(T3MP3STAdapter(), self.handoff,
                                      self.request)
        self.assertIs(unavailable.state, ProviderState.UNAVAILABLE)
        self.assertFalse(unavailable.orphan_possible)
        timed = invoke_governed(_SlowRuntime(delay=0.2),
                                _handoff(self.root, self.fx,
                                         timeout_seconds=0.05),
                                self.request)
        self.assertTrue(timed.orphan_possible)

    # --- builders -------------------------------------------------------

    def _call(self, **over):
        base = dict(seq=1, session_id="PS-1", instance_id="INV-1",
                    call_id="c1", tool=C1A_TOOL,
                    params={"path": str(self.fx)})
        base.update(over)
        return BoundaryToolCall(**base)

    def _result(self, **over):
        base = dict(seq=2, session_id="PS-1", instance_id="INV-1",
                    call_id="c1", tool=C1A_TOOL, ok=True, result_hash="h1")
        base.update(over)
        return BoundaryToolResult(**base)

    def _exec(self, **over):
        base = dict(execution_id="x1", session_id="PS-1", instance_id="INV-1",
                    tool=C1A_TOOL, call_id="c1", path=str(self.fx),
                    result_hash="h1")
        base.update(over)
        return ProviderExecution(**base)

    def _attest(self, path):
        return attest_result(self.handoff, [self._call()],
                             [self._result()],
                             [self._exec(path=path)])


if __name__ == "__main__":
    unittest.main()
