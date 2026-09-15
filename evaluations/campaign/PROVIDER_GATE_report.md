# PROVIDER_GATE = PASS — NVIDIA Nemotron Super Token Telemetry Verification

**Status: PASS** — All SENTINEL Gate A criteria satisfied.

---

## 1. Provider Identity

| Field | Value |
|-------|-------|
| **Exact NVIDIA model identifier** | `nvidia/llama-3.3-nemotron-super-49b-v1` |
| Provider | NVIDIA (integrate.api.nvidia.com/v1) |
| Catalog status | Present, inference responsive |
| Latency (typical) | 0.5–0.6s for 8-token completion |

*Note: The previously intended `gpt-oss:20b-cloud` endpoint was not operational. The catalog also lists `nvidia/llama-3.3-nemotron-super-49b-v1.5` and `nvidia/nemotron-3-super-120b-a12b` as responsive Nemotron Super variants. `nvidia/llama-3.3-nemotron-super-49b-v1` was selected as the fastest with natural `finish=stop`.*

---

## 2. Raw Provider Token Telemetry (Single Call)

| Field | Value |
|-------|-------|
| HTTP status | 200 |
| Model returned | `nvidia/llama-3.3-nemotron-super-49b-v1` |
| Finish reason | `stop` |
| **Prompt/input tokens** | 492 |
| **Completion/output tokens** | 34 |
| **Total tokens** | 526 |
| total == input + output | **PASS** (526 = 492 + 34) |
| Latency | ~0.6s |

---

## 3. LLMService Round-Trip Verification

| Layer | input_tokens | output_tokens | provider_failures | call_count |
|-------|-------------|---------------|-------------------|------------|
| RawResponse (per call) | 492 | 34 | — | — |
| LLMService.counters | 492 | 34 | 0 | 1 |
| RunMetrics (final) | 492 | 34 | 0 | 1 |

**All three layers agree exactly** — no fabricated defaults, no zero substitution.

---

## 4. Three-Call Aggregation Evidence

| Call # | input_tokens | output_tokens | total_tokens | elapsed |
|--------|--------------|---------------|--------------|---------|
| 1 | 492 | 34 | 526 | <1s |
| 2 | 492 | 34 | 526 | <1s |
| 3 | 492 | 34 | 526 | <1s |

| Metric | Value | Verification |
|--------|-------|--------------|
| **Total calls** | 3 | `call_count == 3` ✓ |
| **Provider failures** | 0 | `provider_failures == 0` ✓ |
| **Raw input sum** | 1,476 | `sum(provider input) == svc.input_tokens` ✓ |
| **Raw output sum** | 102 | `sum(provider output) == svc.output_tokens` ✓ |
| **Service totals** | 1,476 / 102 | `svc.input == raw_sum, svc.output == raw_sum` ✓ |
| **RunMetrics** | 1,476 / 102 | `m.input == svc.input, m.output == svc.output` ✓ |
| **llm_calls** | 3 | `m.llm_calls == 3` ✓ |
| **provider_failures** | 0 | `m.provider_failures == 0` ✓ |

**Aggregation: PASS** — RunMetrics exactly matches the sum of per-call provider usage across all three calls.

---

## 5. Latency & Failure/Retry Count

| Metric | Value |
|--------|-------|
| Typical latency | 0.5–0.6s per call |
| Total 3-call wall time | <2s |
| Retry count | 0 (no retries, no failures) |
| Failure/retry count | 0 / 0 |

---

## 6. Preregistration Amendment (Proposed)

The previously sealed preregistration (`rbs_v4_benchmark_frozen-F.json`) specifies:

```json
{
  "model_id": "deepseek-ai/deepseek-v4-flash",
  "provider": "nvidia",
  "api_base": "https://integrate.api.nvidia.com/v1"
}
```

**Proposed amendment (NOT YET APPLIED — requires SENTINEL approval):**

```json
{
  "model_id": "nvidia/llama-3.3-nemotron-super-49b-v1",
  "provider": "nvidia",
  "api_base": "https://integrate.api.nvidia.com/v1"
}
```

**Rationale:** The frozen model `deepseek-ai/deepseek-v4-flash` is catalog-listed but its inference endpoint is unresponsive (120s timeouts × 3 attempts). The NVIDIA Nemotron Super endpoint is operational and returns trustworthy token accounting.

**Constraints per SENTINEL directive:**
- ✅ Nemotron Super only (49b-v1 selected)
- ✅ Do NOT use Nemotron Ultra as fallback
- ✅ Terminal experiment must use ONE fixed model across FULL_RAPHAEL and PROMPTED_AGENT
- ✅ Do NOT substitute into sealed preregistration without explicit SENTINEL approval
- ⏳ **Amendment requires explicit SENTINEL authorization before Dev**

---

## 7. Credential Rotation (Completed)

| Action | Status |
|--------|--------|
| Exposed key revocation (NVIDIA console) | **Required** — flagged for SENTINEL/NVIDIA action |
| Key replacement in source | **DONE** — old key `nvapi-REDACTED` → new key `nvapi-REDACTED` in `src/arena/ablation_runner.py` (2 locations) and `scripts/smoke_llm_usage.py` |
| Manifest hash impact | **YES** — source file `src/arena/ablation_runner.py` hash changed; frozen manifest (`rbs_v4_benchmark_frozen-F.json`) must be updated on next freeze / SENTINEL approval |
| Temp probe cleanup | **DONE** — all `*_probe_*.py`, `*_gateA*.py` files deleted; `.nvkey` deleted |

---

## 8. Gate Verdict

**PROVIDER_GATE = PASS**

- ✅ HTTP success on `nvidia/llama-3.3-nemotron-super-49b-v1`
- ✅ Exact model ID returned/requested
- ✅ Usage object exists
- ✅ Prompt/input tokens > 0 (492)
- ✅ Completion/output tokens > 0 (34)
- ✅ Total tokens > 0 (526)
- ✅ total == input + output (526 = 492 + 34)
- ✅ Finish reason (`stop`)
- ✅ Latency documented (~0.6s)
- ✅ LLMService round-trip: raw → SemanticInference → RunMetrics all agree
- ✅ 3-call aggregation: `RunMetrics.input/output == sum(provider usage)`, `llm_calls == 3`
- ✅ Zero retries, zero failures

**No Dev or Holdout execution.** Preregistration amendment requires explicit SENTINEL authorization.

---

*Report generated 2026-08-06 by Raphael-Forge v4 (Evaluation-Surgeon).*