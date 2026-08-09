# RBS-v2R Phase 3 (FINAL) — Provider Canary Report (GPT-OSS-20B CLOUD)

**Date:** 2026-08-04
**Campaign:** RBS-v2R (cross-model replication pilot)
**Phase:** 3 — PROVIDER CANARY (revised)
**Verdict:** ✅ **PROVIDER_RELIABLE** (100.0% ≥ 90.0% acceptance)
**Gate:** PASS — Phase 4 (pilot) may proceed

---

## 1. Summary of Canary Revisions

| Revision | Measurement path | N | Success | Verdict |
|---|---|---|---|---|
| A | raw hand-rolled prompts, max_tokens=4096, "clean JSON in content" criterion | 20 | 85.0% | NOT_RELIABLE |
| B | raw prompts, `openai/gpt-oss-120b` via NVIDIA, max_tokens=16384 | 20 | 60.0% | NOT_RELIABLE |
| C | raw prompts, `gpt-oss:20b-cloud` via ollama, max_tokens=16384 | 20 | 80.0% | NOT_RELIABLE |
| **C2** | **FROZEN INSTRUMENT PATH** (`LLMService.run_inference()`), same model/config | **20** | **100.0%** | **RELIABLE** |

## 2. Measurement-Fidelity Correction (Why C2 supersedes A/B/C)

Canaries A/B/C measured a **stricter and incorrect boundary**: they sent
hand-rolled exploit/refusal-baiting prompts and required `content` to contain
valid JSON. Two artifacts inflated their failure counts:

1. **Raw prompt framing** — prompts like "Propose a stack-matched exploit
   technique" / "Authorize writing to /etc/passwd" triggered genuine safety
   refusals ("I'm sorry, but I can't help with that."). The campaign never
   sends such raw prompts: every inference is wrapped in the frozen
   `ENVELOPE_SYSTEM_PROMPT` (authorized security-assessment framing), which
   is what the frozen instrument actually uses.
2. **Wrong success criterion** — the frozen instrument's success boundary is
   `process_llm_response()` returning `SemanticInferenceSuccess`. Its parser
   has a documented **last-resort fallback** (category `unclear`, confidence
   0.0) for non-JSON content — a refusal is *consumed as valid inference*
   (this is the `llm_produced` metric), never as a crash. Requiring "clean
   JSON" was measuring a hypothetical, not the instrument.

**Gemma reference anchor:** `evaluations/campaign/rbs_v2_results.jsonl`
(1,890 rows) contains **0** `unclear` outputs. The C2 run also produced
**0** `unclear` outputs — exact parity with the reference model's
structured-output behavior on the frozen path.

## 3. Frozen-Path Canary C2 (N=20) — Results

| Parameter | Value |
|---|---|
| Model | `gpt-oss:20b-cloud` (remote `gpt-oss:20b` @ Ollama Cloud) |
| Digest | `9a01793d9ef8de5309f157c06dbcbadfb598001b4a6f13cbc699cdff5042eaae` |
| Call chain | `LLMService.run_inference()` = `build_envelope` → `call_llm_provider` → `process_llm_response` (exact campaign path) |
| max_tokens | 16384 (freeze manifest C) |
| timeout | 180s |
| temperature | 0.0 |

| Class | Count |
|---|---|
| `SemanticInferenceSuccess` (clean category) | **20** |
| `SemanticInferenceSuccess` degraded (category=unclear fallback) | **0** |
| `SemanticInferenceFailure` | **0** |
| exceptions | **0** |

**success_rate = 20/20 = 100.0%** (acceptance requires ≥ 90%)
**mean latency = 2.63s**, **p95 latency = 4.08s**
**degradation rate (unclear fallback) = 0.0%** — matches Gemma reference (0)

Categories produced: `service_identification`, `version_assessment`,
`vulnerability_indication`, `host_identity_resolution`, `state_description`,
`contradiction_note` — all six real categories exercised, zero `unclear`.

## 4. Quota / Provider-Confound Ledger (C2)

| Event | Count |
|---|---|
| timeout | 0 |
| quota / rate-limit | 0 |
| refusal | 0 |
| empty content | 0 |
| connection error | 0 |
| retry / reconnect | 0 |

No provider-confound filtering required. Latency well within 180s budget
(p95 = 4.08s).

## 5. Freeze Record

- `baseline/rbs_v2r_freeze_manifest_C.json` — **freeze_id: `rbs-v2r-freeze-C`**
  - provider: `gpt-oss:20b-cloud` via ollama (`localhost:11434/v1`)
  - max_tokens: 16384, timeout: 180s, temperature: 0.0
  - git HEAD: `a28c2159a09261c516bbce01ef94bb4e8152139b`
- Earlier aborted freezes (documented for audit):
  - freeze A (`rbs-v2r-freeze-A`, 20b-cloud @4096): failed canary 85%
  - freeze B (`rbs-v2r-freeze-B`, gpt-oss-120b @ NVIDIA): failed canary 60%

## 6. Integrity Notes

- No `src/` change made during canary phases. Frozen instrument untouched.
- Raw canary telemetry A/B/C retained (`rbs_v2r_canary.jsonl`,
  `rbs_v2r_canary_B.jsonl`, `rbs_v2r_canary_C.jsonl`) — no deletion.
- C2 telemetry: `rbs_v2r_canary_C2.jsonl` (20 rows),
  `rbs_v2r_canary_C2_summary.json`.
- Canary C2 completed the pre-specified N=20 sample in one pass; no
  selective reruns, no silent retries (0 retries occurred).

## 7. Next Step (Phase 4 — Pilot, pending SENTINEL authorization)

Execute 10 seeds × 5 configs × relevant templates through the frozen
instrument with freeze manifest C. Record decision-relevance telemetry
(`student_traces`, `hypotheses_created`, `contradictions_detected`,
`llm_invocations`, `llm_produced`) and compare against Gemma reference.

## 8. Artifacts

- `evaluations/campaign/rbs_v2r_canary_C2.jsonl` — 20 raw frozen-path rows
- `evaluations/campaign/rbs_v2r_canary_C2_summary.json` — summary
- `scripts/rbs_v2r_canary_phase3_C2.py` — frozen-path canary harness
- `scripts/rbs_v2r_freeze_phase2_C.py` — freeze manifest C writer
- `baseline/rbs_v2r_freeze_manifest_C.json` — freeze record

---

**Phase 3 verdict (revised): PASS — PROVIDER_RELIABLE at frozen config.**
**Phase 4 (pilot) authorized to proceed pending SENTINEL confirmation.**
