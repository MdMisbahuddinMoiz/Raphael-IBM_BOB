# L-028 Option A — STATUS REPORT TO SENTINEL (2026-08-09)

**Subject:** Option A implementation complete; re-audit gate FAILED 0/10 with
measured root-cause decomposition; one EOL-provider discovery; three proposed
minimal fixes awaiting authorization.

---

## 1. Option A Implementation — COMPLETE, VERIFIED

Wired `LLMService` into `_run_llm_only()` in `src/arena/ablation_runner.py`
mirroring `_run_raphael` (lines 843-853 / 960-978 / 1105-1131):
- **(A)** LLMService creation with `PROMPTED_AGENT_SYSTEM_PROMPT` (respects
  `llm_config_override`; same pattern as D7-R1 Gemma re-test precedent).
- **(B)** Semantic inference each iteration → `model_inference` Evidence →
  EvidenceGraph (unconditional on `SemanticInferenceSuccess`; NOT gated on
  `hypothesis_enabled` — PROMPTED_AGENT has it False).
- **(C)** LLMService telemetry capture; fixed `run()` finalize clobber
  (`self.metrics.llm_calls = self._llm.call_count` was overwriting the merge —
  now scoped via `_llm_service_llm_only` flag).
- **Regression:** tracked suite **127/127 PASS** (identical baseline).
- **Single-sample diagnostic:** `model_inference` evidence = 4, `provider_failures` = 0,
  conclusion claim `service_type | target | http` present.

## 2. CRITICAL DISCOVERY — FROZEN LLM MODEL IS END-OF-LIFE

```
HTTP 410 Gone: The model 'deepseek-ai/deepseek-v4-flash' has reached its end of
life on 2026-08-07T09:00:00Z and is no longer available.
```

- Frozen default `deepseek-ai/deepseek-v4-flash` **returns 410 since 2026-08-07**.
  Today is 2026-08-09. **Every run against the frozen default is guaranteed to
  fail** (this includes the 08-08 re-audit v1/v2 runs).
- Frozen hardcoded API key (`nvapi-g7Gp...`) **cannot access catalog models**
  ("Function not found for account ...") — the account is unsubscribed.
- **LIVE verified:** `deepseek-ai/deepseek-v4-flash-0731` (same family, newer
  snapshot) + `.env` keys `NVIDIA_API_KEY_A`/`B` (both respond OK).
- **Zero src change made:** override supplied at driver level via
  `llm_config_override` (same mechanism as the documented Gemma re-test).
- **Governance question for SENTINEL:** the frozen default model + key are
  inert. Recommend updating the frozen `LLMProviderConfig` default
  (`semantic_inference.py:281`, `ablation_runner.py:844-852`) to the live
  snapshot, or declaring the frozen default as superseded by driver overrides.

## 3. Re-Audit v3 (LIVE LLM) — GATE FAILED 0/10 (fallback-sourced), 0/10 MECHANICAL

10 stratified samples, PROMPTED_AGENT, live `-0731` model, key rotation A/B.
Full telemetry: `evaluations/campaign/L028_VERIFICATION.json`.

| metric | result |
|---|---|
| model_inference evidence flow | 10/10 samples (mi 1-5 each; 2 samples partially starved by transient NVIDIA 503 ResourceExhausted — provider rate limit, not architecture) |
| zero-claim (MECHANICAL) runs | 0/10 |
| INFRA_FAILURE runs | 0/10 |
| fallback-sourced typed L-028 predicates | **0/10** |
| deterministic claims (regex `_evidence_to_claims`) | 10/10 (service_type via "Apache"→http; provenance: derivation_type None, model_inference_ids None) |
| scores | 0.333 / 0.667, all ABSTAIN_INCORRECT |

## 4. Root-Cause Decomposition (all measured, not inferred)

The L-028 parser chain is wired and invoked (structured parse at
`conclusion_adapters.py:1563`, fallback at `:1570`). It extracts nothing
because of three stacked input gaps:

- **(a) Evidence lacks version/CVE strings.** The evidence fed to the LLM is:
  `initial_briefing: "known services: apache"`, `scope`, and 5× identical
  `syn_scan: "10.0.248.10:80/tcp open apache"` — no version, no CVE, no
  Server header. The environment only injects version strings on
  `method == "all"` (`environment.py:397-416`), which the llm_only arm never
  uses. The contradiction template's evaluator expects the agent to identify
  `Apache/2.4.50` — **impossible from this evidence content, regardless of
  parser quality**.
- **(b) Model returns `structured_conclusion: {}`.** Full payload:
  `{"claim": "Host 10.0.248.10 runs an Apache service on port 80.", "category":
  "service_identification", "confidence": 0.95, "structured_conclusion": {}}`
  — the prompt's own escape hatch ("If you cannot determine any structured
  conclusion, use {}") is taken; nothing to fill given (a).
- **(c) Parser phrasing gap — PROVEN.** The free-text claim "runs an Apache
  service on port 80" matches NO fallback pattern (has_service requires
  `port N open`; version requires `X.Y.Z`). Probe result:
  - real `_parse_fallback_heuristic` on real model phrasing → **0 claims**
  - proposed pattern `runs?\s+an?\s+([\w-]+)\s+service\s+on\s+port\s+(\d+)`
    → **('Apache', '80')** — one-line completion of the L-028 mandate.

## 5. Proposed Minimal Fixes (each is a frozen-src change → awaiting SENTINEL authorization)

| # | Change | Blast radius | Evidence |
|---|---|---|---|
| **Fix 1** | Extend `_parse_fallback_heuristic` with `runs an <svc> service on port <n>` → `has_service` (and generic `on port N`) | Low — parser only, completes L-028 | Proven above; unit test extends `verify_l028_fix.py` |
| **Fix 2** | `PROMPTED_AGENT_SYSTEM_PROMPT`: service_identification REQUIRES `has_service`; version in evidence REQUIRES `version`; remove the `{}` escape hatch | Low-medium — prompt only; model compliance on `-0731` snapshot unknown | Retest on 10 samples |
| **Fix 3** | llm_only candidate syn_scan uses `method="all"` (version detection) so evidence carries versions | Medium — candidate generation; changes evidence content for ALL llm_only templates | Enables version/CVE predicates; retest |

Recommendation: authorize **Fix 1 + Fix 2** (parser completion + prompt
tightening), re-run 10-sample gate, and separately adjudicate Fix 3 + the
frozen EOL model default. If Fix 1+2 gate passes (≥8/10), proceed to the
1,200-row holdout per the Option A directive.

## 6. Artifacts

- `evaluations/campaign/L028_VERIFICATION.json` — v3 full telemetry (10 samples)
- `evaluations/campaign/L028_SINGLE_DIAG.json` — single-sample diag (live LLM)
- `forge/prove_parser_gap.py` — parser gap proof (real fallback vs real phrasing)
- `forge/dump_mi_payload.py` — full model_inference payload capture
- `src/` modified (retroactively accepted): `ablation_runner.py` (Option A
  wiring A/B/C + clobber fix + `_pending_si_evidence_ids`), `conclusion_adapters.py`
  (syntax + factory mapping + dedupe). All compile; 127/127 tracked tests pass.
