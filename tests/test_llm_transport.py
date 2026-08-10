"""test_llm_transport.py — REPAIR-VAL-01 dual-key failover transport tests.

Verifies:
   1. KEY_A succeeds immediately (no retries, no failover).
   2. KEY_A fails -> KEY_A retry succeeds (same-key retry).
   3. KEY_A fails -> KEY_B succeeds (failover, no cycle reuse).
   4. Transient failures (429/5xx/timeout) -> later success.
   5. All attempts fail -> exhausted, INFRA failure_class preserved.
   6. HTTP 429 classified rate_limit (retryable).
   7. Transport timeout classified timeout (retryable).
   8. HTTP 5xx classified server_error (retryable).
   9. Connection failure recreates the HTTP client (requirement 9).
  10. HTTP 200 with malformed body is NOT retried (semantic failure downstream).
  11. Client errors (4xx) are NOT retried.
  12. Retries repeat the EXACT SAME payload bytes (byte-equivalence).
  13. Telemetry/errors NEVER contain credential material.
  14. LLMService accumulates transport telemetry (logical-call INFRA unit).
  15. FULL_RAPHAEL and PROMPTED_AGENT share the SAME transport seam.
  16. Frozen default: bare LLMProviderConfig() resolves to Nemotron, no key.

Run: python -m pytest tests/test_llm_transport.py -q
"""

import json
import os
import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

import arena.llm_transport as t
from arena.llm_service import (
    LLMService,
    RawResponse,
    SemanticInferenceFailure,
    SemanticInferenceSuccess,
)
from arena.semantic_inference import LLMProviderConfig

# C9 (W0.8): model identity reverted to the frozen-tree default. 550B failed
# gate (6/10) and NEVER shipped in src/ (commit 1b6c24933: "gate passed on
# 49B, holdout launched"); 49B gate-passed (8/10) and is the canonical frozen
# model for the completed RBS-v4 campaign. Mirrors test_prompted_agent_repair.
AMENDED_MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
AMENDED_PROVIDER = "nvidia"

URL = "https://integrate.api.nvidia.com/v1/chat/completions"
PAYLOAD = {"model": AMENDED_MODEL_ID, "messages": [{"role": "user", "content": "x"}]}
PAYLOAD_BYTES = json.dumps(PAYLOAD, ensure_ascii=False).encode("utf-8")
HEADERS = {"Content-Type": "application/json"}

KEYS = {t.KEY_ALIAS_A: "key-a-value", t.KEY_ALIAS_B: "key-b-value"}


# ── Fake sender helpers ─────────────────────────────────────────────

class ScriptedSender:
    """Returns scripted TransportResponses in order; records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []          # list of dict(url, payload_bytes, headers, client)
        self._i = 0

    def __call__(self, url, payload_bytes, headers, timeout_seconds, client):
        self.calls.append({
            "url": url,
            "payload_bytes": payload_bytes,
            "headers": dict(headers),
            "client": client,
            "timeout_seconds": timeout_seconds,
        })
        resp = self.responses[min(self._i, len(self.responses) - 1)]
        self._i += 1
        return resp


def ok(status=200, text='{"ok": true}'):
    return t.TransportResponse(status, text, 0.1, None)


def fail(status, error=None):
    return t.TransportResponse(status, "", 0.1, error)


def _no_sleep(_):
    pass


# ── 1. Immediate success ────────────────────────────────────────────

def test_A_succeeds_immediately():
    sender = ScriptedSender([ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert out.status_code == 200
    assert out.failure_class is None
    assert out.final_key_alias == t.KEY_ALIAS_A
    assert out.provider_attempts == 1
    assert out.failover_count == 0
    assert out.retries_by_key_alias == {t.KEY_ALIAS_A: 0, t.KEY_ALIAS_B: 0}
    assert len(sender.calls) == 1


# ── 2. Same-key retry ───────────────────────────────────────────────

def test_A_fails_then_A_retry_succeeds():
    sender = ScriptedSender([fail(500), ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert out.provider_attempts == 2
    assert out.final_key_alias == t.KEY_ALIAS_A
    assert out.retries_by_key_alias[t.KEY_ALIAS_A] == 1
    assert out.failover_count == 0
    # Both attempts used KEY_A -> no Authorization header change to KEY_B.
    assert len(sender.calls) == 2
    assert all("Bearer key-a-value" in c["headers"]["Authorization"] for c in sender.calls)


# ── 3. Failover to KEY_B ────────────────────────────────────────────

def test_A_fails_then_B_succeeds():
    sender = ScriptedSender([fail(500), fail(503), ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert out.final_key_alias == t.KEY_ALIAS_B
    assert out.provider_attempts == 3
    assert out.failover_count == 1
    assert out.retries_by_key_alias[t.KEY_ALIAS_A] == 2
    assert out.retries_by_key_alias[t.KEY_ALIAS_B] == 0
    # Last attempt must have used KEY_B credential.
    assert "Bearer key-b-value" in sender.calls[-1]["headers"]["Authorization"]


# ── 4. Transient then later success ─────────────────────────────────

def test_transient_failures_then_success():
    # Per-cycle order: KEY_A x2, KEY_B x2. Sequence:
    #   cycle0: A1=429 (retry), A2=500 (retry), B1=timeout (retry), B2=200 -> SUCCESS
    sender = ScriptedSender([fail(429), fail(500), fail(0, "timeout after 15s"), ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert out.provider_attempts == 4
    assert out.failure_class is None
    assert out.retries_by_key_alias[t.KEY_ALIAS_A] == 2
    assert out.retries_by_key_alias[t.KEY_ALIAS_B] == 1
    assert out.failover_count == 1
    assert out.final_key_alias == t.KEY_ALIAS_B


# ── 5. All attempts exhausted ───────────────────────────────────────

def test_all_attempts_fail_exhausted():
    # 2 keys x 2 attempts x 2 cycles = 8 raw attempts, all 5xx.
    sender = ScriptedSender([fail(503)] * 8)
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is False
    assert out.failure_class == t.FAILURE_CLASS_SERVER
    assert out.provider_attempts == 8
    assert len(sender.calls) == 8
    assert out.retries_by_key_alias[t.KEY_ALIAS_A] == 4
    assert out.retries_by_key_alias[t.KEY_ALIAS_B] == 4
    # INFRA unit per REPAIR-VAL-01: final outcome is server_error -> 1.
    telem = out.to_telemetry_dict()
    assert telem["provider_failures"] == 1
    assert telem["logical_llm_calls"] == 1


# ── 6. Rate limit classification ────────────────────────────────────

def test_rate_limit_429_classified():
    assert t.classify_failure(429, None) == t.FAILURE_CLASS_RATE_LIMIT
    assert t.FAILURE_CLASS_RATE_LIMIT in t.RETRYABLE_CLASSES


# ── 7. Timeout classification ───────────────────────────────────────

def test_timeout_classified():
    assert t.classify_failure(0, "timeout after 15s") == t.FAILURE_CLASS_TIMEOUT
    assert t.classify_failure(0, "connection timeout") == t.FAILURE_CLASS_TIMEOUT
    assert t.FAILURE_CLASS_TIMEOUT in t.RETRYABLE_CLASSES


# ── 8. Server error classification ──────────────────────────────────

def test_server_error_5xx_classified():
    assert t.classify_failure(500, None) == t.FAILURE_CLASS_SERVER
    assert t.classify_failure(502, None) == t.FAILURE_CLASS_SERVER
    assert t.classify_failure(503, None) == t.FAILURE_CLASS_SERVER
    assert t.FAILURE_CLASS_SERVER in t.RETRYABLE_CLASSES


# ── 9. Client recreation after connection failure ───────────────────

def test_connection_failure_recreates_client():
    created = []

    def client_factory():
        c = object()
        created.append(c)
        return c

    # Attempt 1: connection failure. Attempt 2: success.
    sender = ScriptedSender([
        t.TransportResponse(0, "", 0.0, "connection error: reset"),
        ok(),
    ])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
        client_factory=client_factory,
    )
    assert out.success is True
    assert out.client_recreated is True
    # client_factory must have produced >= 2 clients (initial + after reset).
    assert len(created) >= 2
    # The two sender calls must have observed different client objects.
    c0 = sender.calls[0]["client"]
    c1 = sender.calls[1]["client"]
    assert c0 is not c1


def test_connection_failure_classified():
    assert t.classify_failure(0, "connection error: reset") == t.FAILURE_CLASS_CONNECTION
    assert t.classify_failure(0, "request failed") == t.FAILURE_CLASS_CONNECTION


# ── 10. HTTP 200 malformed body NOT retried ─────────────────────────

def test_malformed_200_not_retried():
    # HTTP 200 with garbage body: transport treats as SUCCESS (never retried).
    sender = ScriptedSender([ok(status=200, text="<html>not json</html>")])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert out.provider_attempts == 1
    assert len(sender.calls) == 1  # NO retry on 200
    telem = out.to_telemetry_dict()
    assert telem["provider_failures"] == 0  # semantic failure, NOT infra


# ── 11. Client errors NOT retried ───────────────────────────────────

def test_client_error_4xx_not_retried():
    sender = ScriptedSender([fail(401)])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is False
    assert out.failure_class == t.FAILURE_CLASS_CLIENT
    assert out.provider_attempts == 1
    assert len(sender.calls) == 1  # NOT retried, NOT failed over
    assert out.failover_count == 0
    telem = out.to_telemetry_dict()
    assert telem["provider_failures"] == 0  # client_error is NOT infra


# ── 12. Payload byte-equivalence ────────────────────────────────────

def test_payload_byte_equivalence():
    sender = ScriptedSender([fail(500), fail(503), ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    assert out.success is True
    assert len(sender.calls) == 3
    bodies = [c["payload_bytes"] for c in sender.calls]
    assert all(b == PAYLOAD_BYTES for b in bodies)
    assert all(b == bodies[0] for b in bodies)  # byte-identical retries


# ── 13. Secrets never in telemetry ──────────────────────────────────

def test_telemetry_contains_no_secrets():
    sender = ScriptedSender([fail(500), fail(503), ok()])
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys=KEYS, sender=sender, sleep=_no_sleep,
    )
    telem = out.to_telemetry_dict()
    # Transport's OWN outputs must never contain credential material.
    blob = json.dumps(telem) + repr(out) + (out.error or "")
    assert "key-a-value" not in blob
    assert "key-b-value" not in blob
    assert "nvapi" not in blob
    # Aliases only, never values.
    assert telem["final_key_alias"] in (t.KEY_ALIAS_A, t.KEY_ALIAS_B)
    assert set(telem["retries_by_key_alias"]) <= {t.KEY_ALIAS_A, t.KEY_ALIAS_B}


def test_resolve_keys_env_only(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY_A", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY_B", raising=False)
    # Legacy config fallback -> KEY_A only.
    keys = t.resolve_keys(config_api_key="legacy-key")
    assert keys == {t.KEY_ALIAS_A: "legacy-key"}
    # Env overrides config fallback.
    monkeypatch.setenv("NVIDIA_API_KEY_A", "env-a")
    monkeypatch.setenv("NVIDIA_API_KEY_B", "env-b")
    keys = t.resolve_keys(config_api_key="legacy-key")
    assert keys[t.KEY_ALIAS_A] == "env-a"
    assert keys[t.KEY_ALIAS_B] == "env-b"
    assert "legacy-key" not in keys.values()


def test_no_keys_degrades_gracefully():
    out = t.execute_with_failover(
        url=URL, payload_bytes=PAYLOAD_BYTES, headers_template=HEADERS,
        timeout_seconds=15, keys={}, sender=ScriptedSender([ok()]), sleep=_no_sleep,
    )
    assert out.success is False
    assert out.provider_attempts == 0
    assert out.final_key_alias is None


# ── 14. LLMService telemetry accumulation ───────────────────────────

def _make_success_raw(transport_telem, text=None):
    body = text or json.dumps({
        "choices": [{"message": {"content": json.dumps({
            "claim": "test", "category": "unclear", "confidence": 0.5,
        })}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })
    raw = RawResponse(status_code=200, response_text=body, elapsed=0.1)
    raw.transport_telemetry = transport_telem
    return raw


class _FakeProviderWithTelemetry:
    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def __call__(self, messages, config):
        self.calls += 1
        return self.raw, None


def test_llm_service_accumulates_transport_telemetry(monkeypatch):
    telem = {
        "logical_llm_calls": 1,
        "provider_attempts": 3,
        "provider_failures": 0,       # final outcome was success
        "failover_count": 1,
        "retries_by_key_alias": {t.KEY_ALIAS_A: 2, t.KEY_ALIAS_B: 0},
        "final_key_alias": t.KEY_ALIAS_B,
        "failure_class": None,
        "final_provider_status": 200,
    }
    fake = _FakeProviderWithTelemetry(_make_success_raw(telem))
    monkeypatch.setattr("arena.llm_service.call_llm_provider", fake)

    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    result = svc.run_inference("evidence text", ("ev_1",))
    assert isinstance(result, SemanticInferenceSuccess)
    assert svc.logical_llm_calls == 1
    assert svc.provider_attempts == 3
    assert svc.failover_count == 1
    assert svc.retries_by_key_alias[t.KEY_ALIAS_A] == 2
    assert svc.final_key_alias == t.KEY_ALIAS_B
    assert svc.provider_failures == 0
    assert svc.input_tokens == 10 and svc.output_tokens == 5


def test_llm_service_infra_failure_telemetry(monkeypatch):
    telem = {
        "logical_llm_calls": 1,
        "provider_attempts": 8,
        "provider_failures": 1,       # final outcome exhausted server_error
        "failover_count": 2,
        "retries_by_key_alias": {t.KEY_ALIAS_A: 4, t.KEY_ALIAS_B: 4},
        "final_key_alias": t.KEY_ALIAS_B,
        "failure_class": t.FAILURE_CLASS_SERVER,
        "final_provider_status": 503,
    }
    raw = RawResponse(status_code=503, response_text="", elapsed=0.1)
    raw.transport_telemetry = telem
    fake = _FakeProviderWithTelemetry(raw)
    monkeypatch.setattr("arena.llm_service.call_llm_provider", fake)

    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    result = svc.run_inference("evidence text", ("ev_1",))
    assert isinstance(result, SemanticInferenceFailure)
    assert svc.provider_failures == 1
    assert svc.provider_attempts == 8
    assert svc.failure_class == t.FAILURE_CLASS_SERVER


# ── 15. FULL/PROMPTED share the transport seam ──────────────────────

def test_full_and_prompted_share_transport_seam():
    from arena.ablation import ABLATION_PRESETS
    from arena.ablation_runner import AblationRunner

    # Both arms construct LLMService with the frozen default config whose
    # api_key is EMPTY (credentials env-resolved by the transport).
    for config_id in ("FULL_RAPHAEL", "PROMPTED_AGENT"):
        cfg = ABLATION_PRESETS[config_id]
        assert cfg.llm_enabled is True, f"{config_id} must be LLM-enabled"
        svc = LLMService()
        assert svc.config.api_key == "", f"{config_id} default carries a key"
        assert svc.config.model_id == AMENDED_MODEL_ID
        assert svc.config.provider == AMENDED_PROVIDER

    # The seam: arena.llm_service.call_llm_provider routes through the
    # transport for BOTH arms (single entry point).
    import arena.llm_service as ls
    seam = ls.call_llm_provider
    import inspect
    src = inspect.getsource(seam)
    assert "arena.llm_transport" in src or "call_chat_completion" in src
    assert "nvapi" not in src


# ── 16. Frozen default regression ───────────────────────────────────

def test_frozen_default_model_regression():
    cfg = LLMProviderConfig()  # bare construction
    assert cfg.model_id == AMENDED_MODEL_ID, \
        "Bare LLMProviderConfig() must resolve to the frozen Nemotron model"
    assert cfg.api_key == ""
    assert cfg.provider == AMENDED_PROVIDER


# ── Runner ──────────────────────────────────────────────────────────

TESTS = [
    ("A succeeds immediately", test_A_succeeds_immediately),
    ("A retry succeeds", test_A_fails_then_A_retry_succeeds),
    ("A fails -> B succeeds", test_A_fails_then_B_succeeds),
    ("transient then success", test_transient_failures_then_success),
    ("all attempts exhausted", test_all_attempts_fail_exhausted),
    ("429 rate_limit", test_rate_limit_429_classified),
    ("timeout", test_timeout_classified),
    ("5xx server_error", test_server_error_5xx_classified),
    ("connection recreates client", test_connection_failure_recreates_client),
    ("connection classified", test_connection_failure_classified),
    ("malformed 200 not retried", test_malformed_200_not_retried),
    ("client error not retried", test_client_error_4xx_not_retried),
    ("payload byte-equivalence", test_payload_byte_equivalence),
    ("no secrets in telemetry", test_telemetry_contains_no_secrets),
    ("resolve_keys env only", test_resolve_keys_env_only),
    ("no keys degrades", test_no_keys_degrades_gracefully),
    ("llm_service telemetry success", test_llm_service_accumulates_transport_telemetry),
    ("llm_service infra failure", test_llm_service_infra_failure_telemetry),
    ("FULL/PROMPTED share seam", test_full_and_prompted_share_transport_seam),
    ("frozen default regression", test_frozen_default_model_regression),
]


def _run_manual():
    """Fallback runner when pytest fixtures are unavailable."""
    import traceback
    passed = failed = 0
    for name, fn in TESTS:
        try:
            fn()
        except TypeError:
            # monkeypatch-dependent tests: use unittest.mock patch shim
            from unittest import mock
            try:
                fn(mock.MagicMock())
            except Exception as e:
                failed += 1
                traceback.print_exc()
                print(f"FAIL: {name}: {e}")
            else:
                passed += 1
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"FAIL: {name}: {e}")
        else:
            passed += 1
    print(f"LLM TRANSPORT: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)
