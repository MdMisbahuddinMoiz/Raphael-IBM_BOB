"""llm_service.py — D-4: LLM provider wrapper, parser, and tracing.

Orchestrates: envelope → provider call → parse/validate → trace → result.

Design invariants:
  - Provider metadata (model_id, provider) comes from config, never model output.
  - Raw response is stored ONLY in DiagnosticEpisodeLog, never in cognitive state.
  - INVOKED trace is recorded before the provider call.
  - PRODUCED trace is recorded only for SemanticInferenceSuccess.
  - Failures produce SemanticInferenceFailure but never count as PRODUCED.
  - Transport: REPAIR-VAL-01 dual-key NVIDIA failover with bounded retry
    (AMENDMENT-MODEL-550B-2026-08-09). call_llm_provider routes through
    llm_transport.call_chat_completion (byte-identical payload retries,
    KEY_A -> KEY_B failover, backoff base 1s cap 8s, 2 attempts/key/cycle,
    2 cycles). NEVER retried: 2xx (semantic failures downstream), 4xx/3xx
    client errors, cognitive failures.
"""

import json
import logging
import time
from typing import Optional

import requests

from arena.ablation import ComponentTrace
from arena.llm_transport import call_chat_completion, TransportOutcome
from arena.semantic_inference import (
    ENVELOPE_VERSION,
    ENVELOPE_SYSTEM_PROMPT,
    DiagnosticEpisodeLog,
    DiagnosticRawRecord,
    LLMProviderConfig,
    SemanticInferenceFailure,
    SemanticInferenceResult,
    SemanticInferenceSuccess,
    build_envelope,
    validate_semantic_inference,
)

logger = logging.getLogger("llm_service")


# ── Raw Response Parsing ───────────────────────────────────────────────

class RawResponse:
    """Parsed raw response from the LLM provider.

    This is the ONLY point where raw provider text is parsed.
    After parsing, only the typed SemanticInferenceResult enters cognition.
    """

    def __init__(self, status_code: int, response_text: str, elapsed: float,
                 input_tokens: Optional[int] = None,
                 output_tokens: Optional[int] = None):
        self.status_code = status_code
        self.response_text = response_text
        self.elapsed = elapsed
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens: Optional[int] = None
        self.transport_telemetry: Optional[dict] = None
        self._parsed_json: Optional[dict] = None
        self._parse_error: Optional[str] = None
        self._parse()

    def _parse(self) -> None:
        """Attempt to parse response_text as JSON + extract usage tokens."""
        if not self.response_text or not self.response_text.strip():
            self._parse_error = "empty response"
            return
        try:
            self._parsed_json = json.loads(self.response_text)
        except json.JSONDecodeError as e:
            self._parse_error = f"JSON parse error: {e}"
            return
        # Usage extraction: present -> real counts (0 is genuine zero);
        # absent -> None (never conflated with zero-token success).
        if isinstance(self._parsed_json, dict):
            usage = self._parsed_json.get("usage")
            if isinstance(usage, dict):
                pt = usage.get("prompt_tokens")
                ct = usage.get("completion_tokens")
                tt = usage.get("total_tokens")
                if pt is not None:
                    self.input_tokens = pt
                if ct is not None:
                    self.output_tokens = ct
                if tt is None and pt is not None and ct is not None:
                    tt = pt + ct
                if tt is not None:
                    self.total_tokens = tt

    @property
    def is_valid_json(self) -> bool:
        return self._parsed_json is not None and self._parse_error is None

    def extract_semantic_fields(self) -> Optional[dict]:
        """Extract claim, category, confidence from parsed JSON.

        Tries multiple possible response formats:
        1. Direct: {"claim": ..., "category": ..., "confidence": ...}
        2. Nested in choices[0].message.content (OpenAI/DeepSeek API format)
        3. Content field contains JSON

        Returns dict with keys 'claim', 'category', 'confidence', or None.
        """
        if not self.is_valid_json:
            return None

        data = self._parsed_json

        # Format 1: Direct response
        if "claim" in data and "category" in data:
            return {
                "claim": data.get("claim", ""),
                "category": data.get("category", ""),
                "confidence": data.get("confidence"),
            }

        # Format 2: OpenAI/DeepSeek chat completions format
        # {"choices": [{"message": {"content": "..."}}]}
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if content:
                # Content might itself be JSON
                try:
                    inner = json.loads(content)
                    if "claim" in inner and "category" in inner:
                        return {
                            "claim": inner.get("claim", ""),
                            "category": inner.get("category", ""),
                            "confidence": inner.get("confidence"),
                        }
                except json.JSONDecodeError:
                    pass
                # Content is plain text — try to find JSON in it
                # (some models wrap JSON in markdown code blocks)
                import re
                json_match = re.search(r'\{[^{}]*"claim"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    try:
                        inner = json.loads(json_match.group(0))
                        if "claim" in inner and "category" in inner:
                            return {
                                "claim": inner.get("claim", ""),
                                "category": inner.get("category", ""),
                                "confidence": inner.get("confidence"),
                            }
                    except json.JSONDecodeError:
                        pass
                # Last resort: treat entire content as the claim
                return {
                    "claim": content.strip()[:500],
                    "category": "unclear",
                    "confidence": 0.0,
                }

        return None


# ── Provider Call ──────────────────────────────────────────────────────

def call_llm_provider(
    messages: list[dict],
    config: LLMProviderConfig,
) -> tuple[RawResponse, Optional[str]]:
    """Make a synchronous HTTP call to the LLM provider.

    Args:
        messages: The prompt messages (system + user).
        config: Provider configuration.

    Returns:
        Tuple of (RawResponse, error_message_or_None).
        If the call succeeds, error is None.
        If the call fails, error is a diagnostic string.
    """
    if config.api_base:
        url = f"{config.api_base.rstrip('/')}/chat/completions"
    else:
        logger.warning(
            "No api_base configured. Using mock mode for diagnostic."
        )
        # Return a mock response for testing when no API is configured
        return RawResponse(
            status_code=200,
            response_text=json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "claim": "Mock inference: no API configured",
                            "category": "unclear",
                            "confidence": 0.0,
                        })
                    }
                }]
            }),
            elapsed=0.0,
        ), "no_api_configured_mock_mode"

    headers = {
        "Content-Type": "application/json",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "model": config.model_id,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    # REPAIR-VAL-01 transport seam (AMENDMENT-MODEL-550B-2026-08-09):
    # serialized payload bytes reused verbatim across every attempt;
    # KEY_A -> KEY_B failover; retry only on mechanical classes
    # (rate_limit/server_error/timeout/connection); backoff base 1s cap 8s;
    # 2 attempts/key/cycle, 2 cycles. Credentials env-resolved, never logged.
    try:
        start = time.time()
        outcome: TransportOutcome = call_chat_completion(
            url=url,
            payload=payload,
            headers_template=headers,
            timeout_seconds=config.timeout_seconds,
            config_api_key=config.api_key or "",
        )
        elapsed = time.time() - start

        raw = RawResponse(
            status_code=outcome.status_code,
            response_text=outcome.response_text,
            elapsed=outcome.elapsed,
        )
        # Attach transport telemetry for LLMService accumulation.
        raw.transport_telemetry = outcome.to_telemetry_dict()

        if not outcome.success:
            error_detail = (
                f"HTTP {outcome.status_code}: {outcome.response_text[:200]}"
                if outcome.status_code else
                (outcome.error or "provider call failed")
            )
            return raw, error_detail

        return raw, None

    except Exception as e:  # transport-level / unexpected
        elapsed = config.timeout_seconds
        raw = RawResponse(
            status_code=0,
            response_text="",
            elapsed=elapsed,
        )
        raw.transport_telemetry = {
            "logical_llm_calls": 1,
            "provider_attempts": 1,
            "provider_failures": 1,
            "failover_count": 0,
            "retries_by_key_alias": {},
            "final_key_alias": None,
            "failure_class": "connection",
            "final_provider_status": 0,
        }
        return raw, f"transport failure: {e}"


# ── Response Processing ────────────────────────────────────────────────

def process_llm_response(
    raw: RawResponse,
    *,
    source_evidence_ids: tuple[str, ...],
    model_id: str,
    provider: str,
    raw_response_text: str,
) -> SemanticInferenceResult:
    """Process a raw LLM response into a SemanticInferenceResult.

    This is the validation pipeline: parse → extract → validate → result.
    There is no alternative raw-text path into cognition.

    Args:
        raw: The parsed RawResponse.
        source_evidence_ids: Evidence IDs passed to the LLM.
        model_id: From config (not model output).
        provider: From config (not model output).
        raw_response_text: The complete raw response text.

    Returns:
        SemanticInferenceSuccess if valid, SemanticInferenceFailure otherwise.
    """
    # ── Check for HTTP-level failure ──
    if raw.status_code != 200 and raw.status_code != 0:
        status = raw.status_code
        detail = raw.response_text[:200] if raw.response_text else "unknown"
        return SemanticInferenceFailure(
            attempt_id=f"si_fail_{hash(raw_response_text) & 0xFFFFFFFF:08x}",
            source_evidence_ids=source_evidence_ids,
            failure_type="provider_api_error",
            diagnostic_detail=f"HTTP {status}: {detail}",
            provider=provider,
            model_id=model_id,
            timestamp=time.time(),
            raw_response_hash=hash(raw_response_text) & 0xFFFFFFFF,
        )

    # ── Check for timeout ──
    if raw.status_code == 0 and not raw.response_text:
        return SemanticInferenceFailure(
            attempt_id=f"si_fail_{hash(str(raw.elapsed)) & 0xFFFFFFFF:08x}",
            source_evidence_ids=source_evidence_ids,
            failure_type="provider_timeout",
            diagnostic_detail=f"timeout after {raw.elapsed:.1f}s",
            provider=provider,
            model_id=model_id,
            timestamp=time.time(),
        )

    # ── Check for malformed JSON ──
    if not raw.is_valid_json:
        parse_err = raw._parse_error or "unknown parse error"
        return SemanticInferenceFailure(
            attempt_id=f"si_fail_{hash(raw_response_text) & 0xFFFFFFFF:08x}",
            source_evidence_ids=source_evidence_ids,
            failure_type="malformed_output",
            diagnostic_detail=f"JSON parse failure: {parse_err}",
            provider=provider,
            model_id=model_id,
            timestamp=time.time(),
            raw_response_hash=hash(raw_response_text) & 0xFFFFFFFF,
        )

    # ── Extract semantic fields ──
    fields = raw.extract_semantic_fields()
    if fields is None:
        return SemanticInferenceFailure(
            attempt_id=f"si_fail_{hash(raw_response_text) & 0xFFFFFFFF:08x}",
            source_evidence_ids=source_evidence_ids,
            failure_type="malformed_output",
            diagnostic_detail="response does not contain expected semantic fields (claim, category)",
            provider=provider,
            model_id=model_id,
            timestamp=time.time(),
            raw_response_hash=hash(raw_response_text) & 0xFFFFFFFF,
        )

    # ── Validate semantic fields ──
    return validate_semantic_inference(
        claim=fields.get("claim", ""),
        category_raw=fields.get("category", ""),
        confidence=fields.get("confidence"),
        source_evidence_ids=source_evidence_ids,
        model_id=model_id,
        provider=provider,
        raw_response=raw_response_text,
    )


# ── LLM Service (Orchestrator) ─────────────────────────────────────────

class LLMService:
    """Orchestrates LLM inference: envelope → call → parse → trace.

    This is the primary entry point for the D-4 cognitive loop.
    It combines the envelope builder, provider call, response parsing,
    validation, and tracing into a single operation.

    Usage:
        service = LLMService(config=LLMProviderConfig(...))
        result = service.run_inference(
            observation_text="Server: Apache/2.4.50",
            source_evidence_ids=("ev_17",),
            run_id="run_001",
        )
        # result is SemanticInferenceSuccess or SemanticInferenceFailure
    """

    def __init__(
        self,
        config: Optional[LLMProviderConfig] = None,
        tracer: Optional['TraceCollector'] = None,
        diagnostic_log: Optional[DiagnosticEpisodeLog] = None,
        system_prompt: str = None,
    ):
        self.config = config or LLMProviderConfig()
        self.tracer = tracer
        self.diagnostic_log = diagnostic_log or DiagnosticEpisodeLog()
        self.system_prompt = system_prompt
        # Telemetry counters (for RunMetrics integration)
        self.call_count: int = 0
        self.provider_failures: int = 0
        self.logical_llm_calls: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.envelope_failures: int = 0
        # Transport telemetry (REPAIR-VAL-01 / AMENDMENT-MODEL-550B-2026-08-09)
        self.provider_attempts: int = 0
        self.failover_count: int = 0
        self.retries_by_key_alias: dict = {}
        self.final_key_alias: Optional[str] = None
        self.failure_class: Optional[str] = None
        self.final_provider_status: int = 0

    def run_inference(
        self,
        observation_text: str,
        source_evidence_ids: tuple[str, ...],
        run_id: str = "",
    ) -> SemanticInferenceResult:
        """Execute a single LLM inference: envelope → call → parse → trace.

        Args:
            observation_text: The raw target-controlled observation.
            source_evidence_ids: Evidence IDs for provenance.
            run_id: Current run ID for tracing.

        Returns:
            SemanticInferenceSuccess or SemanticInferenceFailure.
        """
        # Increment logical call counter
        self.logical_llm_calls += 1
        
        # ── Stage 1: Build envelope ──
        try:
            messages = build_envelope(observation_text, system_prompt=self.system_prompt)
        except ValueError as e:
            self.envelope_failures += 1
            result = SemanticInferenceFailure(
                attempt_id=f"si_fail_{hash(observation_text) & 0xFFFFFFFF:08x}",
                source_evidence_ids=source_evidence_ids,
                failure_type="semantically_unusable",
                diagnostic_detail=f"envelope build failed: {e}",
                provider=self.config.provider,
                model_id=self.config.model_id,
                timestamp=time.time(),
            )
            self._trace_invoked(source_evidence_ids, run_id)
            # No PRODUCED trace for envelope failures
            return result

        # ── Stage 2: Trace INVOKED ──
        self._trace_invoked(source_evidence_ids, run_id)

        # ── Stage 3: Call provider ──
        self.call_count += 1
        raw_response, error = call_llm_provider(messages, self.config)

        # ── Stage 3b: Accumulate transport telemetry (REPAIR-VAL-01) ──
        telem = getattr(raw_response, "transport_telemetry", None)
        if isinstance(telem, dict):
            self.provider_attempts += int(telem.get("provider_attempts", 0) or 0)
            self.failover_count += int(telem.get("failover_count", 0) or 0)
            rk = telem.get("retries_by_key_alias") or {}
            for alias, n in rk.items():
                self.retries_by_key_alias[alias] = self.retries_by_key_alias.get(alias, 0) + int(n or 0)
            if telem.get("final_key_alias") is not None:
                self.final_key_alias = telem["final_key_alias"]
            self.failure_class = telem.get("failure_class")
            self.final_provider_status = int(telem.get("final_provider_status", 0) or 0)
            if not telem.get("logical_llm_calls"):
                self.logical_llm_calls += 1
        else:
            # No transport telemetry (mock mode / legacy callers): the
            # envelope path already counted logical calls above.
            pass
        if raw_response.input_tokens is not None:
            self.input_tokens += int(raw_response.input_tokens or 0)
        if raw_response.output_tokens is not None:
            self.output_tokens += int(raw_response.output_tokens or 0)

        # ── Stage 4: Process response ──
        result = process_llm_response(
            raw_response,
            source_evidence_ids=source_evidence_ids,
            model_id=self.config.model_id,
            provider=self.config.provider,
            raw_response_text=raw_response.response_text,
        )

        # Track provider failures: only INFRA-class final outcomes count
        # (FREEZE-02 taxonomy). Envelope failures are counted separately.
        # Mock mode (empty api_base) returns status 200 + an informational
        # error string — a 2xx is NEVER a provider failure.
        if telem is not None:
            self.provider_failures += int(telem.get("provider_failures", 0) or 0)
        elif error and raw_response.status_code != 200:
            self.provider_failures += 1

        # ── Stage 5: Record diagnostic ──
        self._record_diagnostic(result, raw_response)

        # ── Stage 6: Trace PRODUCED (only for Success) ──
        if isinstance(result, SemanticInferenceSuccess):
            self._trace_produced(result, run_id)

        return result

    def _trace_invoked(
        self,
        source_evidence_ids: tuple[str, ...],
        run_id: str,
    ) -> None:
        """Record INVOKED trace: inference attempted."""
        if self.tracer is None:
            return
        self.tracer.trace(
            component="llm_service",
            operation="llm_inference",
            input_ids=list(source_evidence_ids),
            output_ids=[],
        )

    def _trace_produced(
        self,
        success: SemanticInferenceSuccess,
        run_id: str,
    ) -> None:
        """Record PRODUCED trace: valid SemanticInferenceSuccess created."""
        if self.tracer is None:
            return
        self.tracer.trace(
            component="llm_service",
            operation="produced_semantic_inference",
            input_ids=list(success.source_evidence_ids),
            output_ids=[success.inference_id],
        )

    def _record_diagnostic(
        self,
        result: SemanticInferenceResult,
        raw_response: 'RawResponse',
    ) -> None:
        """Record raw provider response in diagnostic log only."""
        if isinstance(result, SemanticInferenceSuccess):
            id_or_attempt = result.inference_id
            result_type = "success"
        else:
            id_or_attempt = result.attempt_id
            result_type = "failure"

        record = DiagnosticRawRecord(
            inference_id_or_attempt=id_or_attempt,
            source_evidence_ids=(
                result.source_evidence_ids
                if hasattr(result, 'source_evidence_ids')
                else ()
            ),
            model_id=self.config.model_id,
            provider=self.config.provider,
            timestamp=time.time(),
            raw_response_text=raw_response.response_text,
            response_hash=str(hash(raw_response.response_text) & 0xFFFFFFFF),
            envelope_version=ENVELOPE_VERSION,
            result_type=result_type,
            input_tokens=raw_response.input_tokens,
            output_tokens=raw_response.output_tokens,
            total_tokens=raw_response.total_tokens,
        )
        self.diagnostic_log.record(record)
