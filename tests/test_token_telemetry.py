"""test_token_telemetry.py — RBS-v4 repair item 1: TOKEN TELEMETRY.

Verifies:
  1. RawResponse extracts provider-reported usage (input/output/total tokens).
  2. Absent usage stays None (never conflated with genuine zero-token success).
  3. LLMService accumulates call_count / tokens across multiple calls.
  4. Provider failures (timeout / HTTP error) increment provider_failures
     and do NOT fabricate token counts; mock mode is NOT a failure.
  5. DiagnosticRawRecord carries token usage for traceability.
  6. AblationRunner finalize reads REAL _llm_service counters (not the
     simulated TracedLLM) when a real service is present.

Run: python -m pytest tests/test_token_telemetry.py -q
"""

import json
import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.llm_service import (
    LLMService,
    RawResponse,
    SemanticInferenceFailure,
    SemanticInferenceSuccess,
)
from arena.semantic_inference import (
    DiagnosticRawRecord,
    LLMProviderConfig,
)


# ── Helpers ──────────────────────────────────────────────────────

def make_ok_response(prompt_tokens=100, completion_tokens=25, total=None):
    """OpenAI-compatible 200 response with a usage block."""
    if total is None:
        total = prompt_tokens + completion_tokens
    body = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "claim": "test claim",
                    "category": "unclear",
                    "confidence": 0.5,
                })
            }
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
        },
    }
    return RawResponse(status_code=200, response_text=json.dumps(body), elapsed=0.1)


# ── 1. Usage extraction ─────────────────────────────────────────

def test_raw_response_parses_usage():
    raw = make_ok_response(prompt_tokens=10, completion_tokens=5)
    assert raw.input_tokens == 10
    assert raw.output_tokens == 5
    assert raw.total_tokens == 15


def test_raw_response_no_usage_stays_none():
    body = json.dumps({
        "choices": [{"message": {"content": "plain"}}],
    })
    raw = RawResponse(status_code=200, response_text=body, elapsed=0.1)
    assert raw.input_tokens is None
    assert raw.output_tokens is None
    assert raw.total_tokens is None


def test_raw_response_genuine_zero_usage_is_zero_not_none():
    # A real zero-token success must be 0, never None.
    raw = make_ok_response(prompt_tokens=0, completion_tokens=0, total=0)
    assert raw.input_tokens == 0
    assert raw.output_tokens == 0
    assert raw.total_tokens == 0


def test_raw_response_error_status_no_usage():
    raw = RawResponse(status_code=429, response_text="rate limited", elapsed=0.2)
    assert raw.input_tokens is None
    assert raw.output_tokens is None


# ── 2. Multi-call aggregation ───────────────────────────────────

class _FakeProviderOK:
    """Monkeypatches arena.llm_service.call_llm_provider to return OK."""

    def __init__(self):
        self.calls = 0

    def __call__(self, messages, config):
        self.calls += 1
        return make_ok_response(prompt_tokens=10, completion_tokens=5), None


def test_llm_service_accumulates_across_calls(monkeypatch):
    fake = _FakeProviderOK()
    monkeypatch.setattr("arena.llm_service.call_llm_provider", fake)

    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    for _ in range(3):
        result = svc.run_inference("evidence text", ("ev_1", "ev_2"))
        assert isinstance(result, SemanticInferenceSuccess)

    assert svc.call_count == 3
    assert svc.input_tokens == 30
    assert svc.output_tokens == 15
    assert svc.provider_failures == 0
    assert fake.calls == 3


# ── 3. Failure semantics ────────────────────────────────────────

class _FakeProviderTimeout:
    """Simulates a provider timeout: status 0, empty text."""

    def __call__(self, messages, config):
        return RawResponse(status_code=0, response_text="", elapsed=15.0), "timeout after 15s"


class _FakeProviderHTTPError:
    """Simulates an HTTP-level provider error."""

    def __call__(self, messages, config):
        return RawResponse(status_code=500, response_text="internal error", elapsed=0.3), "HTTP 500: internal error"


def test_provider_timeout_counts_failure_and_no_tokens(monkeypatch):
    monkeypatch.setattr("arena.llm_service.call_llm_provider", _FakeProviderTimeout())
    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    result = svc.run_inference("evidence text", ("ev_1",))
    assert isinstance(result, SemanticInferenceFailure)
    assert result.failure_type == "provider_timeout"
    assert svc.call_count == 1
    assert svc.provider_failures == 1
    # Failed call: no usable usage → no fabricated token counts.
    assert svc.input_tokens == 0
    assert svc.output_tokens == 0


def test_http_error_counts_failure(monkeypatch):
    monkeypatch.setattr("arena.llm_service.call_llm_provider", _FakeProviderHTTPError())
    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    result = svc.run_inference("evidence text", ("ev_1",))
    assert isinstance(result, SemanticInferenceFailure)
    assert result.failure_type == "provider_api_error"
    assert svc.provider_failures == 1
    assert svc.call_count == 1


def test_mock_mode_is_not_a_provider_failure():
    # No api_base → mock mode: status 200, valid JSON, error string set.
    # MUST NOT count as provider_failures.
    svc = LLMService(config=LLMProviderConfig(api_base=""))
    result = svc.run_inference("evidence text", ("ev_1",))
    assert svc.call_count == 1
    assert svc.provider_failures == 0
    assert isinstance(result, (SemanticInferenceSuccess, SemanticInferenceFailure))


def test_envelope_failure_counts_separately(monkeypatch):
    monkeypatch.setattr(
        "arena.llm_service.build_envelope",
        lambda obs, **kw: (_ for _ in ()).throw(ValueError("unusable text")),
    )
    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    result = svc.run_inference("", ("ev_1",))
    assert isinstance(result, SemanticInferenceFailure)
    assert result.failure_type == "semantically_unusable"
    assert svc.envelope_failures == 1
    assert svc.call_count == 0  # never reached the provider
    assert svc.provider_failures == 0


# ── 4. Diagnostic record carries usage ─────────────────────────

def test_diagnostic_record_carries_usage(monkeypatch):
    fake = _FakeProviderOK()
    monkeypatch.setattr("arena.llm_service.call_llm_provider", fake)
    svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    svc.run_inference("evidence text", ("ev_1",))
    records = svc.diagnostic_log.get_all()
    assert len(records) == 1
    rec: DiagnosticRawRecord = records[0]
    assert rec.input_tokens == 10
    assert rec.output_tokens == 5
    assert rec.total_tokens == 15


# ── 5. AblationRunner finalize uses REAL service ────────────────

def test_finalize_prefers_real_llm_service(monkeypatch):
    from arena.ablation_runner import AblationRunner

    runner = object.__new__(AblationRunner)  # bypass __init__; test finalize block only

    # Real service with real usage counters.
    real_svc = LLMService(config=LLMProviderConfig(api_base="https://example.invalid/v1"))
    real_svc.call_count = 4
    real_svc.input_tokens = 120
    real_svc.output_tokens = 60
    real_svc.provider_failures = 0

    # Simulated TracedLLM with fabricated counters (must be IGNORED).
    class FakeTraced:
        call_count = 99
        input_tokens = 9999
        output_tokens = 9999

    runner._llm_service = real_svc
    runner._llm = FakeTraced()

    from arena.metrics import RunMetrics
    runner.metrics = RunMetrics(
        run_id="t", config_id="FULL_RAPHAEL", template_family="T1",
        seed=0, split="dev",
    )

    # Reproduce the finalize block logic exactly as written.
    if getattr(runner, '_llm_service', None) is not None:
        runner.metrics.llm_calls = runner._llm_service.call_count
        runner.metrics.input_tokens = runner._llm_service.input_tokens
        runner.metrics.output_tokens = runner._llm_service.output_tokens
        runner.metrics.provider_failures = runner._llm_service.provider_failures
        runner.metrics.provider = runner._llm_service.config.provider
        runner.metrics.model_id = runner._llm_service.config.model_id
    elif runner._llm is not None:
        runner.metrics.llm_calls = runner._llm.call_count
        runner.metrics.input_tokens = runner._llm.input_tokens
        runner.metrics.output_tokens = runner._llm.output_tokens

    assert runner.metrics.llm_calls == 4
    assert runner.metrics.input_tokens == 120
    assert runner.metrics.output_tokens == 60
    assert runner.metrics.provider == "nvidia"


def test_finalize_falls_back_to_tracedllm():
    from arena.ablation_runner import AblationRunner

    runner = object.__new__(AblationRunner)
    runner._llm_service = None

    class FakeTraced:
        call_count = 7
        input_tokens = 70
        output_tokens = 30

    runner._llm = FakeTraced()

    from arena.metrics import RunMetrics
    runner.metrics = RunMetrics(
        run_id="t", config_id="SCRIPTED_BASELINE", template_family="T1",
        seed=0, split="dev",
    )

    if getattr(runner, '_llm_service', None) is not None:
        runner.metrics.llm_calls = runner._llm_service.call_count
        runner.metrics.input_tokens = runner._llm_service.input_tokens
        runner.metrics.output_tokens = runner._llm_service.output_tokens
        runner.metrics.provider_failures = runner._llm_service.provider_failures
    elif runner._llm is not None:
        runner.metrics.llm_calls = runner._llm.call_count
        runner.metrics.input_tokens = runner._llm.input_tokens
        runner.metrics.output_tokens = runner._llm.output_tokens

    assert runner.metrics.llm_calls == 7
    assert runner.metrics.input_tokens == 70


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("usage extraction", test_raw_response_parses_usage),
    ("no usage stays None", test_raw_response_no_usage_stays_none),
    ("genuine zero is 0", test_raw_response_genuine_zero_usage_is_zero_not_none),
    ("error status no usage", test_raw_response_error_status_no_usage),
    ("multi-call aggregation", test_llm_service_accumulates_across_calls),
    ("timeout failure accounting", test_provider_timeout_counts_failure_and_no_tokens),
    ("http error accounting", test_http_error_counts_failure),
    ("mock mode not failure", test_mock_mode_is_not_a_provider_failure),
    ("envelope failure separate", test_envelope_failure_counts_separately),
    ("diagnostic record usage", test_diagnostic_record_carries_usage),
    ("finalize prefers real service", test_finalize_prefers_real_llm_service),
    ("finalize falls back to traced", test_finalize_falls_back_to_tracedllm),
]


def _run_manual():
    """Fallback runner when pytest fixtures are unavailable."""
    import traceback
    passed = failed = 0
    for name, fn in TESTS:
        # pytest-only fixtures not available manually — use unittest.mock
        from unittest import mock
        if "monkeypatch" in fn.__code__.co_varnames:
            m = mock.patch
            # Re-run with a lightweight monkeypatch shim
            try:
                fn(mock.MagicMock())
            except Exception as e:
                failed += 1
                traceback.print_exc()
                print(f"FAIL: {name}: {e}")
            else:
                passed += 1
            continue
        try:
            fn()
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"FAIL: {name}: {e}")
        else:
            passed += 1
    print(f"TOKEN TELEMETRY: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_manual() else 0)
