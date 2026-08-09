# SENTINEL REPORT — D1-D: SCRIPTED_BASELINE & NWM STRUCTURAL DEFECT CHECK

**Status:** COMPLETE
**Date (UTC):** 2026-08-08
**Author:** RBS-v1 EVALUATION CAMPAIGN (Raphael-Forge v4)

---

## 1. MANDATE

SENTINEL D1-D directive: "SCRIPTED_BASELINE sits at 2.3% pass — much closer to PROMPTED's 0% than to NWM's 15.7%. Before ruling PROMPTED the *only* structurally broken arm, run the D1-C-1 check on SCRIPTED_BASELINE: does its code path ever elicit a final verdict, or is it also action-loop-only? If it's the same defect, the FULL-vs-SCRIPTED comparison needs the identical disclosure treatment. Confirm NWM's claim channel while you're in there too: NWM's `has_service` claims — do they come through the world-model path that's disabled for NWM by definition, or a separate channel?"

---

## 2. SCRIPTED_BASELINE — D1-C-1 CHECK (VERDICT CHANNEL)

**Code path examined:** `src/arena/ablation_runner.py::_run_scripted()` (lines 2999–3150) + `ScriptedConclusionAdapter` (`conclusion_adapters.py:1054–1095`)

**Findings:**

1. **No verdict channel exists.** The `_run_scripted()` loop runs a deterministic round-robin policy for 5 iterations. There is NO LLM call, no prompt, and no final-verdict prompt at loop termination. The only output is the deterministic action selection.

2. **Hardcoded decision outcome.** `ScriptedConclusionAdapter.build()` (line 1088) explicitly sets:
   ```python
   decision=DecisionOutcome.STOP_BUDGET_EXHAUSTED,
   ```
   This is a constant — not derived from any model belief or loop state.

3. **Claims production:** Only `_evidence_to_claims()` is called (line 1079). No hypothesis, world-model, LLM, or planner channels. Only evidence-regex claims fire → 1 claim/run (service_type: http).

4. **Episodes confirm:** SCRIPTED runs 5 iterations, dispatches actions, creates evidence, but never elicits a conclusion from any cognitive component.

**Conclusion:** SCRIPTED_BASELINE has the **exact same structural defect** as PROMPTED_AGENT — no verdict channel, only action-loop, hardcoded terminal decision, claims limited to evidence-regex. Its 2.3% pass rate (7/300) is a structural floor, not a reasoning floor.

---

## 3. NO_WORLD_MODEL — CLAIM CHANNEL ANALYSIS

**Code path examined:** `NoWorldModelConclusionAdapter` (`conclusion_adapters.py:840–882`) + run data (300 runs)

**Adapter calls:**
1. `_hypothesis_to_claims()` — hypothesis claims (enabled)
2. `_evidence_to_claims()` — evidence-derived claims (enabled)
3. `_evidence_to_llm_claims()` — LLM claims (enabled)

**Does NOT call:**
- `_world_model_to_claims()` — world model disabled
- `_semantic_inference_to_claims()` — requires hypothesis_manager (not called)

**Run data (300 runs):**
- `has_service` claims: **120 total** (0.4/run) vs FULL's 300 (1.0/run)
- Derivation type: ALL `direct_observation` (from `_evidence_to_claims` port regex `port\s+(\d+)\s+(\w+)`)
- `hypothesis_inference` claims: 0 observed in sampled runs (adapter calls `_hypothesis_to_claims` but produces 0 such claims in practice)
- `service_type` claims: 2,992 total
- `same_entity_as`: 2

**FULL_RAPHAEL comparison:** FULL has 300 `has_service` claims (1.0/run), produced by world-model `add_service_entity` trace path + `_semantic_inference_to_claims` (hypothesis-attached semantic claims).

**Conclusion:** NWM's `has_service` claims come from the **evidence-regex channel** (`_evidence_to_claims` port regex on literal "port NNN word" text), NOT from world-model (disabled) or hypothesis. NWM produces 0.4 `has_service` claims/run vs FULL's 1.0 — a 60% reduction directly attributable to the missing world-model claim channel. NWM's 15.7% pass rate (47/300) is **structurally capped** by this missing claim channel, not purely by the world-model reasoning ablation.

---

## 4. SYNTHESIS

| Arm | Verdict Channel? | Decision | Claims/Run | Pass Rate | Defect Type |
|-----|------------------|----------|------------|-----------|-------------|
| FULL_RAPHAEL | Yes (STOP_OBJECTIVE_REACHED from planner) | Dynamic | 42.0 | 50.3% | — |
| PROMPTED_AGENT | **NO** (action-envelope only) | Hardcoded STOP_OBJECTIVE_REACHED | 0.72 | 0.0% | INSTRUMENT_DEFECT |
| SCRIPTED_BASELINE | **NO** (deterministic policy) | Hardcoded STOP_BUDGET_EXHAUSTED | 1.34 | 2.3% | INSTRUMENT_DEFECT |
| NO_WORLD_MODEL | Partial (ACT/STOP_OBJECTIVE_REACHED) | Dynamic | 10.4 | 15.7% | CONFOUNDED (claim channel) |

---

## 5. IMPLICATION FOR VERDICT

1. **PROMPTED_AGENT is NOT the only structurally broken arm.** SCRIPTED_BASELINE shares the identical defect (no verdict channel, hardcoded decision, evidence-regex claims only). The FULL-vs-SCRIPTED comparison requires identical disclosure treatment.

2. **NWM's 15.7% pass rate is structurally capped** by the missing world-model claim channel. Its `has_service` claims come from evidence-regex only (0.4/run vs FULL's 1.0/run). The world-model ablation's measured effect is CONFOUNDED with the missing claim channel.

3. **FULL-vs-PROMPTED delta (0.3287) and FULL-vs-SCRIPTED delta (0.347) are both claim-layer measurements, not reasoning-quality measurements.** Two of three comparison arms share the same structural defect.

---

## 6. VERDICT IMPLICATION

Per SENTINEL's directive: D5's framing must include a paragraph (not a footnote) stating that **two of the three comparison arms (PROMPTED_AGENT and SCRIPTED_BASELINE) share the identical structural defect (no verdict channel), and NWM's pass rate is structurally capped by a missing claim channel**. The FULL-vs-PROMPTED and FULL-vs-SCRIPTED deltas are claim-layer measurements, not reasoning-quality measurements.

---