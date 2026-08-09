"""Append Re-Audit v2 section to PROMPTED_AGENT_ANOMALY_AUDIT.md"""
import io

path = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/PROMPTED_AGENT_ANOMALY_AUDIT.md"
section = '''

---

## 11. Re-Audit v2 (2026-08-09) — Fallback Heuristic Executed, Gate NOT Met

**Directive:** SENTINEL Option A (clean patch + 10-sample re-audit; gate >= 8/10 typed predicates; halt if >= 2/10 MECHANICAL).

### Repairs Applied (all retroactively ACCEPTED by SENTINEL)
1. `src/arena/conclusion_adapters.py`: stray `try:` syntax repair; factory mapping `"PROMPTED_AGENT": LLMOnlyConclusionAdapter`; `architecture_id` from `config.config_id`; dead duplicate `_parse_fallback_heuristic` removed (single clean def at line 837).
2. `src/arena/ablation_runner.py`: `_pending_si_evidence_ids` initialized in `__init__` (was only set in the Raphael loop; LLM-only path raised AttributeError -> INFRA_FAILURE).

### Verification Gate (pre-audit)
- Tracked test suite: **127/127 PASS** (no regression).
- Untracked repair-era suite: 49 failed / 63 passed — **identical to documented baseline** (no new failures).
- `conclusion_adapters.py` compiles; fallback + structured parser callable; factory runtime-verified.

### Re-Audit Results (10 stratified PROMPTED_AGENT runs, holdout split)
Raw data: `evaluations/campaign/L028_VERIFICATION.json` (full per-sample telemetry).

| Metric | Result |
|--------|--------|
| `model_inference` evidence created | **0 across all 10 runs** |
| Fallback heuristic executions (real) | **0/10** — starved of input |
| Structured parser executions (real) | **0/10** — starved of input |
| Claims from deterministic `_evidence_to_claims` | 7/10 (predicate `service_type`, from "Apache" regex on syn_scan text) |
| L-028 typed predicates (CVE/version/patched_fix/vulnerable_host/has_service) | **0/10** |
| Scores | 0.333–0.667 (unchanged pattern; ABSTAIN_INCORRECT) |

### Root Cause (Rule 24 — First Failing Boundary)
The adapter wiring was necessary but NOT sufficient. The first failing boundary is **upstream in the data pipeline**:

- `run()` dispatches PROMPTED_AGENT to `_run_llm_only()` (baseline_type `llm_only`).
- `_run_llm_only()` creates `TracedLLM` (simulation) at line 2624 but **never creates `self._llm_service`** — `LLMService` is instantiated only in `_run_raphael()` (line 847).
- Without `LLMService`, no `SemanticInferenceSuccess` is ever produced in this path, so **no `model_inference` evidence is ever added to the evidence graph**.
- Both L-028 parsers (`_parse_structured_conclusion`, `_parse_fallback_heuristic`) filter on `evidence_type == 'model_inference'` -> empty input -> zero claims.
- The 10/10 MECHANICAL verdict in prior audits was therefore **never about model non-compliance** — the parsers never executed against real LLM output.

### Verdict
> **STOP CONDITION TRIGGERED (SENTINEL gate: halt if >= 2/10 MECHANICAL; observed 10/10 MECHANICAL for the L-028 mechanism).** The fallback heuristic is correct and unit-verified, but it is unreachable in the PROMPTED_AGENT path because the LLM-only execution path never produces `model_inference` evidence. The claim-formalization gap is a **harness data-flow defect (missing LLMService in `_run_llm_only`)**, not a model alignment limitation. Awaiting SENTINEL adjudication: either (a) authorize `_run_llm_only` to instantiate `LLMService` + semantic inference + model_inference evidence creation (mirroring `_run_raphael`), or (b) re-scope the L-028 evaluation.

*Re-audit v2 artifacts: `evaluations/campaign/L028_VERIFICATION.json` (full telemetry), `forge/verify_l028.py` (runner), `forge/diag_l028_single.py`, `forge/verify_endstate.py`*
'''

with io.open(path, "a", encoding="utf-8") as f:
    f.write(section)

with io.open(path, "r", encoding="utf-8") as f:
    content = f.read()

print("lines now:", content.count("\n"))
print("section 11 present:", "## 11. Re-Audit v2" in content)
