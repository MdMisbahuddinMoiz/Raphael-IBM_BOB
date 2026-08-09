"""llm_transport.py — REPAIR-VAL-01 dual-key NVIDIA failover transport.

Deterministic failover KEY_A -> KEY_B with bounded retry, mechanical
failure classification, client recreation, and full telemetry.

Design invariants (REPAIR-VAL-01, SENTINEL-authorized):
  - Credentials NEVER hardcoded, printed, persisted, or committed.
    Keys are resolved ONLY from environment variables at call time
    (NVIDIA_API_KEY_A / NVIDIA_API_KEY_B), with the legacy single-key
    fallback (config.api_key -> KEY_A) preserved for existing callers.
  - A retry repeats the EXACT SAME inference request: payload is
    serialized to bytes ONCE and reused byte-identically across every
    attempt. Only the Authorization header changes (per key).
  - Retry ONLY on mechanical infrastructure classes:
      rate_limit  (HTTP 429)
      server_error (HTTP 5xx)
      timeout      (transport-level, no response)
      connection   (transport-level, connection/network failure)
    NEVER retried: HTTP 200 (malformed output is a semantic failure,
    handled downstream), other 4xx/3xx (client/auth errors), and all
    cognitive failures (bad reasoning, wrong action, refusal, broker
    denial, loop, budget exhaustion) — none of which are transport
    events.
  - Policy: 2 attempts/key/cycle, maximum 2 cycles, bounded exponential
    backoff (base 1s, cap 8s).
  - After a connection failure the HTTP client is recreated before the
    next attempt. Raphael/episode state is NEVER restarted.
  - Telemetry (never credentials):
      logical_llm_calls, provider_attempts, provider_failures,
      failover_count, retries_by_key_alias, final_key_alias,
      failure_class, final_provider_status
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

import requests

logger = logging.getLogger("llm_transport")

# ── Key aliases ────────────────────────────────────────────────────────

KEY_ALIAS_A = "KEY_A"
KEY_ALIAS_B = "KEY_B"
KEY_ORDER = (KEY_ALIAS_A, KEY_ALIAS_B)

ENV_KEY_A = "NVIDIA_API_KEY_A"
ENV_KEY_B = "NVIDIA_API_KEY_B"

# ── Failure classes (mechanical, never reclassified) ───────────────────

FAILURE_CLASS_RATE_LIMIT = "rate_limit"
FAILURE_CLASS_SERVER = "server_error"
FAILURE_CLASS_TIMEOUT = "timeout"
FAILURE_CLASS_CONNECTION = "connection"
FAILURE_CLASS_CLIENT = "client_error"  # 3xx / 4xx except 429 — NOT retried

RETRYABLE_CLASSES = frozenset({
    FAILURE_CLASS_RATE_LIMIT,
    FAILURE_CLASS_SERVER,
    FAILURE_CLASS_TIMEOUT,
    FAILURE_CLASS_CONNECTION,
})

# INFRA classes per FREEZE-02 taxonomy (amended to logical-call unit by
# REPAIR-VAL-01): a logical call whose FINAL outcome is one of these is an
# infrastructure event. Absorbed transient failures are NOT infra events.
INFRA_FINAL_CLASSES = frozenset({
    FAILURE_CLASS_RATE_LIMIT,
    FAILURE_CLASS_SERVER,
    FAILURE_CLASS_TIMEOUT,
    FAILURE_CLASS_CONNECTION,
})

# ── Retry policy ───────────────────────────────────────────────────────

ATTEMPTS_PER_KEY_PER_CYCLE = 2
MAX_CYCLES = 2
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 8.0


# ── Failure classification ─────────────────────────────────────────────

def classify_failure(status_code: int, error: Optional[str]) -> Optional[str]:
    """Mechanical classification of a provider attempt.

    Returns:
        None  -> HTTP 200 (success at transport level; NEVER retried)
        str   -> one of the FAILURE_CLASS_* constants
    """
    if 200 <= status_code < 300:
        # Any 2xx is a transport success — NEVER retried, even if the
        # body is malformed (that is a semantic failure).
        return None
    if status_code == 429:
        return FAILURE_CLASS_RATE_LIMIT
    if 500 <= status_code < 600:
        return FAILURE_CLASS_SERVER
    if status_code == 0:
        # Transport-level failure: no HTTP status received.
        if error and "timeout" in error.lower():
            return FAILURE_CLASS_TIMEOUT
        if error and "connection" in error.lower():
            return FAILURE_CLASS_CONNECTION
        # Generic request failure (no response) — treat as connection.
        return FAILURE_CLASS_CONNECTION
    # 3xx / 4xx (except 429): client/auth errors — NEVER retried.
    return FAILURE_CLASS_CLIENT


# ── Transport response ─────────────────────────────────────────────────

@dataclass
class TransportResponse:
    """Raw result of a single HTTP attempt."""
    status_code: int
    text: str
    elapsed: float
    error: Optional[str] = None


def default_requests_sender(
    url: str,
    payload_bytes: bytes,
    headers: Dict[str, str],
    timeout_seconds: float,
    client: Optional["requests.Session"],
) -> TransportResponse:
    """Send one HTTP POST with the EXACT payload bytes provided."""
    try:
        start = time.time()
        if client is not None:
            resp = client.post(
                url, headers=headers, data=payload_bytes, timeout=timeout_seconds
            )
        else:
            resp = requests.post(
                url, headers=headers, data=payload_bytes, timeout=timeout_seconds
            )
        elapsed = time.time() - start
        return TransportResponse(resp.status_code, resp.text, elapsed, None)
    except requests.exceptions.Timeout:
        return TransportResponse(0, "", float(timeout_seconds),
                                 f"timeout after {timeout_seconds}s")
    except requests.exceptions.ConnectionError as e:
        return TransportResponse(0, "", 0.0, f"connection error: {e}")
    except requests.exceptions.RequestException as e:
        return TransportResponse(0, "", 0.0, f"request failed: {e}")


# ── Transport outcome (telemetry carrier) ──────────────────────────────

@dataclass
class TransportOutcome:
    """Final outcome of one LOGICAL LLM call, including retry telemetry.

    Credentials are never present in this object.
    """
    success: bool = False
    status_code: int = 0
    response_text: str = ""
    elapsed: float = 0.0
    error: Optional[str] = None
    failure_class: Optional[str] = None   # None on success
    final_key_alias: Optional[str] = None
    final_provider_status: int = 0        # HTTP status of final attempt (0 = transport)
    provider_attempts: int = 0            # total raw HTTP attempts
    retries_by_key_alias: Dict[str, int] = field(default_factory=dict)
    failover_count: int = 0               # number of KEY_A -> KEY_B transitions
    client_recreated: bool = False

    def to_telemetry_dict(self) -> Dict:
        """Telemetry dict — contains NO credential material."""
        return {
            "logical_llm_calls": 1,
            "provider_attempts": self.provider_attempts,
            "provider_failures": 1 if (not self.success
                                       and self.failure_class in INFRA_FINAL_CLASSES) else 0,
            "failover_count": self.failover_count,
            "retries_by_key_alias": dict(self.retries_by_key_alias),
            "final_key_alias": self.final_key_alias,
            "failure_class": self.failure_class,
            "final_provider_status": self.final_provider_status,
        }


# ── Key resolution (env only, never persisted/logged) ──────────────────

def resolve_keys(config_api_key: str = "") -> Dict[str, str]:
    """Resolve key alias -> credential from the environment.

    Priority:
      KEY_A <- NVIDIA_API_KEY_A (env) OR legacy config.api_key fallback
      KEY_B <- NVIDIA_API_KEY_B (env)

    Missing keys are simply absent from the dict; the transport skips
    absent aliases (single-key mode degrades gracefully).
    """
    keys: Dict[str, str] = {}
    a = os.environ.get(ENV_KEY_A) or ""
    b = os.environ.get(ENV_KEY_B) or ""
    if a:
        keys[KEY_ALIAS_A] = a
    elif config_api_key:
        keys[KEY_ALIAS_A] = config_api_key
    if b:
        keys[KEY_ALIAS_B] = b
    return keys


def _redact(value: str) -> str:
    """Never log credential material."""
    return "<redacted>" if value else ""


# ── Failover executor ──────────────────────────────────────────────────

def execute_with_failover(
    *,
    url: str,
    payload_bytes: bytes,
    headers_template: Dict[str, str],
    timeout_seconds: float,
    keys: Dict[str, str],
    key_order: tuple = KEY_ORDER,
    attempts_per_key: int = ATTEMPTS_PER_KEY_PER_CYCLE,
    max_cycles: int = MAX_CYCLES,
    backoff_base: float = BACKOFF_BASE_SECONDS,
    backoff_cap: float = BACKOFF_CAP_SECONDS,
    sender: Callable = default_requests_sender,
    sleep: Callable = time.sleep,
    client_factory: Optional[Callable] = None,
) -> TransportOutcome:
    """Execute one logical LLM call with deterministic failover + retry.

    A retry repeats the EXACT SAME payload bytes. Only the Authorization
    header changes (per key alias). After a connection failure the HTTP
    client is recreated before the next attempt.
    """
    outcome = TransportOutcome()
    retries_by_key: Dict[str, int] = {a: 0 for a in key_order}
    client = client_factory() if client_factory is not None else None
    last_failure_class: Optional[str] = None
    last_resp: Optional[TransportResponse] = None
    final_key: Optional[str] = None
    failover = 0

    for cycle in range(max_cycles):
        for idx, alias in enumerate(key_order):
            key = keys.get(alias)
            if not key:
                continue  # absent alias -> skip (single-key mode)
            if idx > 0 and last_failure_class is not None:
                # Moving to KEY_B after a retryable failure: one failover.
                failover += 1
            for _attempt in range(attempts_per_key):
                final_key = alias
                headers = dict(headers_template)
                headers["Authorization"] = f"Bearer {key}"

                # Recreate client after a connection failure (req 9).
                if last_failure_class == FAILURE_CLASS_CONNECTION:
                    if client_factory is not None:
                        client = client_factory()
                    outcome.client_recreated = True

                resp = sender(url, payload_bytes, headers, timeout_seconds, client)
                last_resp = resp
                cls = classify_failure(resp.status_code, resp.error)

                if cls is None:
                    # HTTP 200 — transport success. NEVER retried, even if
                    # the body is malformed (that is a semantic failure).
                    return TransportOutcome(
                        success=True,
                        status_code=resp.status_code,
                        response_text=resp.text,
                        elapsed=resp.elapsed,
                        error=None,
                        failure_class=None,
                        final_key_alias=final_key,
                        final_provider_status=resp.status_code,
                        provider_attempts=sum(retries_by_key.values()) + 1,
                        retries_by_key_alias=dict(retries_by_key),
                        failover_count=failover,
                        client_recreated=outcome.client_recreated,
                    )

                if cls not in RETRYABLE_CLASSES:
                    # Non-retryable client error — return immediately.
                    return TransportOutcome(
                        success=False,
                        status_code=resp.status_code,
                        response_text=resp.text,
                        elapsed=resp.elapsed,
                        error=resp.error,
                        failure_class=cls,
                        final_key_alias=final_key,
                        final_provider_status=resp.status_code,
                        provider_attempts=sum(retries_by_key.values()) + 1,
                        retries_by_key_alias=dict(retries_by_key),
                        failover_count=failover,
                        client_recreated=outcome.client_recreated,
                    )

                # Retryable failure: record and back off.
                retries_by_key[alias] += 1
                last_failure_class = cls
                is_last_attempt = (
                    cycle == max_cycles - 1
                    and idx == len(key_order) - 1
                    and _attempt == attempts_per_key - 1
                )
                if not is_last_attempt:
                    n = sum(retries_by_key.values())  # total retries so far
                    delay = min(backoff_base * (2 ** max(0, n - 1)), backoff_cap)
                    if delay > 0:
                        sleep(delay)

    # All attempts exhausted.
    return TransportOutcome(
        success=False,
        status_code=last_resp.status_code if last_resp else 0,
        response_text=last_resp.text if last_resp else "",
        elapsed=last_resp.elapsed if last_resp else 0.0,
        error=last_resp.error if last_resp else "all attempts exhausted",
        failure_class=last_failure_class,
        final_key_alias=final_key,
        final_provider_status=last_resp.status_code if last_resp else 0,
        provider_attempts=sum(retries_by_key.values()),
        retries_by_key_alias=dict(retries_by_key),
        failover_count=failover,
        client_recreated=outcome.client_recreated,
    )


# ── HTTP helper (public, used by llm_service) ──────────────────────────

def call_chat_completion(
    *,
    url: str,
    payload: dict,
    headers_template: Dict[str, str],
    timeout_seconds: float,
    config_api_key: str = "",
    attempts_per_key: int = ATTEMPTS_PER_KEY_PER_CYCLE,
    max_cycles: int = MAX_CYCLES,
    backoff_base: float = BACKOFF_BASE_SECONDS,
    backoff_cap: float = BACKOFF_CAP_SECONDS,
    sender: Callable = default_requests_sender,
    sleep: Callable = time.sleep,
    client_factory: Optional[Callable] = None,
) -> TransportOutcome:
    """Public entry: serialize payload ONCE, resolve keys, run failover.

    The payload dict is serialized to bytes exactly once; those bytes are
    reused for every attempt (byte-equivalent retries).
    """
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    keys = resolve_keys(config_api_key)
    outcome = execute_with_failover(
        url=url,
        payload_bytes=payload_bytes,
        headers_template=headers_template,
        timeout_seconds=timeout_seconds,
        keys=keys,
        attempts_per_key=attempts_per_key,
        max_cycles=max_cycles,
        backoff_base=backoff_base,
        backoff_cap=backoff_cap,
        sender=sender,
        sleep=sleep,
        client_factory=client_factory,
    )
    return outcome
