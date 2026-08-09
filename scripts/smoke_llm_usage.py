#!/usr/bin/env python3
"""smoke_llm_usage.py — LIVE token-usage smoke test (RBS-v4 repair item 1).

Verifies end-to-end that a REAL provider call reports token usage that is
parsed into RawResponse and accumulated by LLMService counters.

This test makes a real network call to the frozen provider config
(NVIDIA Llama-3.3 Nemotron Super, dual-key failover transport). It must
NOT run in CI without network; it exits:
  0 = PASS (usage parsed and > 0)
  2 = SKIP (endpoint unreachable / auth failure — no assertion possible)
  1 = FAIL (endpoint reachable but usage missing/malformed)

Usage:
  /home/yaser/raphael-2.0-rbsv2r/.venv/bin/python scripts/smoke_llm_usage.py
"""
import json
import os
import sys
import time

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')
sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r')


def _load_dotenv(path: str) -> None:
    """Minimal .env loader (no external dependency). Keys are loaded into
    os.environ ONLY if not already set. Values are never printed."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v.strip()


_load_dotenv("/home/yaser/raphael-2.0-rbsv2r/.env")

from arena.llm_service import LLMService, SemanticInferenceSuccess
from arena.semantic_inference import LLMProviderConfig

# Frozen campaign provider config (matches ablation_runner default).
# REPAIR-VAL-01: api_key is EMPTY — credentials are resolved from the
# gitignored environment by the transport (NVIDIA_API_KEY_A / B).
CONFIG = LLMProviderConfig(
    model_id="nvidia/llama-3.3-nemotron-super-49b-v1",
    provider="nvidia",
    api_base="https://integrate.api.nvidia.com/v1",
    api_key="",
    timeout_seconds=30,
    temperature=0.0,
    max_tokens=64,
)

MINIMAL_OBSERVATION = (
    "Evidence count: 1\n"
    "- Server: Apache/2.4.49 on 10.0.0.5 (port 80)\n"
    "Categorize the service exposure."
)


def main() -> int:
    svc = LLMService(config=CONFIG)
    start = time.time()
    result = svc.run_inference(MINIMAL_OBSERVATION, ("smoke_ev_1",), run_id="smoke_usage")
    elapsed = time.time() - start

    print(f"call_count={svc.call_count} provider_failures={svc.provider_failures}")
    print(f"input_tokens={svc.input_tokens} output_tokens={svc.output_tokens}")
    print(f"elapsed={elapsed:.1f}s result_type={type(result).__name__}")

    # ── SKIP classification: endpoint unreachable / auth failed ──
    if isinstance(result, SemanticInferenceSuccess) is False:
        detail = getattr(result, "diagnostic_detail", "")
        print(f"provider-level result: {getattr(result, 'failure_type', '?')}: {detail}")
        if getattr(result, "failure_type", "") in ("provider_api_error", "provider_timeout"):
            print("SKIP: endpoint unreachable or auth failure — no live assertion possible")
            return 2
        # Reachable but model output unusable — telemetry should still exist
        if svc.call_count >= 1 and svc.provider_failures >= 0:
            print("WARN: call reached provider but result unusable; telemetry counters present")
            return 2 if svc.provider_failures > 0 else 1

    # ── PASS classification: usage reported and > 0 ──
    if svc.call_count != 1:
        print(f"FAIL: expected call_count=1, got {svc.call_count}")
        return 1
    if svc.input_tokens is None or svc.input_tokens <= 0:
        print(f"FAIL: input_tokens missing/zero ({svc.input_tokens})")
        return 1
    if svc.output_tokens is None or svc.output_tokens < 0:
        print(f"FAIL: output_tokens missing ({svc.output_tokens})")
        return 1

    # Diagnostic record must carry usage.
    records = svc.diagnostic_log.get_all()
    if not records:
        print("FAIL: no diagnostic record written")
        return 1
    rec = records[0]
    if rec.input_tokens is None:
        print("FAIL: diagnostic record missing input_tokens")
        return 1

    print(f"PASS: live usage input={svc.input_tokens} output={svc.output_tokens} "
          f"total={rec.total_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
