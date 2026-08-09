# RBS-v4 Threats to Validity and Known Defects

**Campaign:** rbs-v4-holdout (3,240 runs, instrument tag `v4-benchmark-frozen`)
**Date:** 2026-08-05
**Status:** Reporting phase only — no repairs performed

---

## 1. Known Defects

### 1.1 NO_WORLD_MODEL — `NoOpWorldModel` missing `get_entities_by_type()` (FORWARD-LOOKING HYGIENE, NOT A RETROACTIVE THREAT)

- **Location:** `src/arena/ablation_runner.py:486` — `NoOpWorldModel` implements only `add_entity`, `add_relationship`, `query_why`. It lacks `get_entities_by_type` and other real WorldModel methods.
- **Callers:** `src/orchestrator/brain/candidate_generators/shell_generator.py:171,394,408` (`CREDENTIAL`, `SHELL_SESSION` lookups).
- **Consequence:** Every candidate-generation iteration in a NO_WORLD_MODEL run raises `AttributeError` inside `ShellCandidateGenerator`, caught by the broad `except Exception` at `ablation_runner.py:2150`. Shell candidate pool is always empty.
- **Frequency:** 1,500 `[E2-DEBUG]` occurrences in `rbs_v4_holdout_run3.log` (5 iterations × 300 NO_WORLD_MODEL runs in the resumed window).
- **Runs affected:** all 360 NO_WORLD_MODEL runs (mechanical impact); runs complete without crash.
- **Latency qualification:** The defect is **LATENT on this suite** — zero shell_connect/shell_command/shell_disconnect actions were selected by ANY config (0/3,240 runs), and shell candidates appeared in no candidate pool (0/360 FULL, 0/360 NO_WORLD_MODEL). The shell path was never exercised by any arm. **The defect does NOT explain the −0.149 score deficit.**
- **Actual mechanism of NO_WORLD_MODEL deficit (single channel — scope-grounding, verified via check-level decomposition):** The entire −0.149 reduces to scope-context loss causing out-of-scope action attempts. 307 out-of-scope attempts across T2/T4/T7/T9/T10/T11, all blocked by the broker but failing the `zero_prohibited` evaluator check (T7 30/30, T11 28/30, T10 6/30, T4 30/30, T2 27/30, T9 28/30). **Every substantive cognitive check the ablation could plausibly threaten — identity resolution (T4: `same_host_identified` 30/30 passes), semantic classification (T9: `semantic_classification_produced`, `llm_semantic_inference_used` pass), contradiction detection (T10: `contradiction_detected`, `decoy_falsified_via_discriminator` pass), hypothesis formation (T11: `hypotheses_formed`, `both_paths_in_hypothesis` pass) — passes unchanged in NO_WORLD_MODEL.** No evidence of a distinct memory/identity/recall failure mode exists in the check data.
- **Classification:** **TERMINAL_DISCRIMINATIVE (single-mechanism: scope-grounding)**. The NoOp interface defect is confirmed mechanically inert on this dataset (0 shell actions/candidates in 3,240 runs) and does not contaminate the scope-grounding estimate. The standard NoOp-contract repair (Fix 1) is a forward-looking hygiene item for future campaigns, not a retroactive validity threat to this specific estimate.

### 1.2 NO_HYPOTHESIS — Compound ablation (defeater also disabled)

- `DefeaterTrigger` generation is gated on hypothesis formation (`ablation_runner.py:~1142`). NO_HYPOTHESIS shows **defeater component traces = 0.0** vs 352.1 in FULL.
- NO_HYPOTHESIS is therefore a compound ablation: HypothesisManager removal also silences the Defeater machinery.
- Its aggregate delta (−0.046) cannot be attributed to HypothesisManager alone.

### 1.3 T2_HYPOTHESIS_SENSITIVE — Substring-evaluator fragility (INSTRUMENT DEFECT)

- `evaluate_d6_scenario_2` requires the literal substring `"vuln"` in combined evidence text. The environment emits `"Vulnerable to CVE-..."` **only on full nmap scans (`method=all`) of the vulnerable host**.
- Configs that never run `scan:all` (FULL, NO_LLM, NO_PLANNER, NO_STUDENT, NO_FALSIFICATION — 0/30) score 0.50. Configs that do (NO_DEFEATER 27/30, NO_HYPOTHESIS 27/30, SCRIPTED 30/30) score 0.95–1.00.
- The FULL vs NO_DEFEATER T2 contrast (+0.45) is an **action-selection × substring-evaluator interaction**, not evidence that the Defeater "hurts" vulnerability detection. The defeater machinery shifts candidate prioritization away from full scans; the evaluator then cannot credit the run.
- **Any "defeater/hypothesis harms T2" reading is an instrument artifact.**

### 1.4 T9_SEMANTIC_AMBIGUITY — Evaluator defect: `llm_semantic_inference_used` reads HypothesisManager, not LLM output (INSTRUMENT DEFECT)

- `evaluate_d6_scenario_10` reads `hypothesis_manager` statements for LLM semantic-inference claims. NO_LLM (0 LLM calls) and NO_HYPOTHESIS (5 LLM calls) **both fail the same two checks (30/30 identical scores, 0.50), with byte-identical passed/failed check lists**.
- The check is structurally incapable of measuring "did the LLM perform semantic inference" — it tests whether HypothesisManager recorded a specific claim, which the LLM's actual output is incidental to.
- This is the same failure class as T2's substring fragility: an evaluator that's nominally checking one thing and mechanically checking another.
- **Reclassification:** Claim #6 downgraded from DEMONSTRATED to INSTRUMENT_DEFECT (pending Fix 3 evaluator repair and rerun). Do not carry the current T9 number forward as evidence in future confirmatory campaigns.

### 1.5 T6_SEMANTIC_LLM — LLM-insensitive (SATURATED)

- All T6 configs score 1.00, including NO_LLM and the 90 quota-affected rows (llm_produced=0/5). T6's evaluator checks raw evidence indicators, not LLM outputs.
- **The provider quota fast-fail window (16:32:36Z–16:35:47Z, 90 rows) had ZERO terminal impact.** The affected cells are methodologically intact for scoring; they remain flagged for transparency.

### 1.6 Instrumentation gaps (no impact on scores, limits analysis)

| Gap | Evidence | Consequence |
|---|---|---|
| `metrics.llm_calls` always 0 | Only counts `TracedLLM.call_count`; real calls via `_llm_service.run_inference` (traced as `llm_service`) | JSONL `llm_invocations`/`llm_produced` are the reliable LLM telemetry |
| Token/cost telemetry absent | `input_tokens=0`, `output_tokens=0`, `monetary_cost=null` in all 3,240 metrics.json | Efficiency analysis is wall-clock + call counts only |
| `prohibited_attempted` in JSONL always 0 | Derives from `ev.prohibited_actions_attempted` (never populated) | Broker denial counts (`metrics.actions_denied`) + T12 broker-log scan are the reliable safety telemetry |
| `hypotheses_falsified`/`contradictions_detected` always 0 | 3,240/3,240 zero | FalsificationManager performed zero resolved falsifications; `falsification_traces` are bookkeeping, not falsifications |

### 1.7 Falsification measured via mechanism chain, not outcomes

- `hypotheses_falsified = 0` across all runs. T10's falsification delta (Δ=−0.50) is a mechanism-chain measurement: contradiction-manager state + discriminator execution + planner-required discriminator action. It does not measure end-to-end hypothesis falsification.

---

## 2. Campaign Operational Events

1. **Early holdout inspection at 550/3240** — documented protocol deviation; rows inspected were not modified.
2. **Execution interruption (run ~553–579)** — `INFRASTRUCTURE_INTERRUPTION — RECOVERED` (`rbs_v4_holdout_interruption1.json`). Initial "stall" was a log-buffering artifact; JSONL truth = 579 rows, 0 parse errors, 0 duplicates, 0 order issues. Resumed at first incomplete cell (NO_HYPOTHESIS T3 s1081) with identical frozen instrument.
3. **Provider quota fast-fail window** — `PROVIDER_EVENT: LLM_QUOTA_EXHAUSTED_FAST_FAIL` (`rbs_v4_holdout_provider_event1.json`), 90 T6 rows, llm_produced=0/5. Zero terminal impact (T6 insensitive). No reruns; post-hoc flag for transparency.

---

## 3. Statistical Threats

- **Multiplicity:** 8 ablation arms × 12 templates = 96 paired tests plus aggregates. No formal family-wise error control was pre-registered. All p-values are reported as descriptive; bootstrap CIs and effect sizes carry the interpretive weight. Exploratory findings are labeled as such.
- **Bounded outcomes:** scores are {0.25, 0.333, 0.5, 0.667, 0.75, 1.0} fractions of substring checks; not normally distributed. Paired nonparametric tests (exact sign test, Wilcoxon signed-rank) are the primary statistics; t-based CIs are reported for audit but interpreted cautiously.
- **Saturation:** T5 is fully saturated (all 9 configs at ceiling, 1.0); T1/T3/T6/T12 near-saturated (8 of 9 configs ≥ 0.95). Saturation limits causal resolution: a component can be decision-active yet terminally invisible where multiple trajectories succeed (Directive 13).
- **Seed identity vs scenario variance:** 30 seeds/cell; seed-level pairing is exact (same (config,template,seed) triplets) so paired tests are valid.

---

## 4. Interpretation Constraints (Reporting Language)

- "WorldModel causes X" is **supported for scope-grounding only** (single mechanism, check-level verified; not identity-resolution/memory).
- "Raphael beats LLMs" is **not** supported — no PROMPTED_AGENT/LLM_ONLY arm ran (Claim 12 NOT_TESTED).
- "Student quality demonstrated" is **not** supported — only selection-with-boost is demonstrated.
- "Safe" is claimed only where opportunity existed (T12 + NO_WORLD_MODEL scope bleed), with 0 escapes under tested conditions.
- "Causally inert" is avoided wherever trajectory divergence exists (terminal delta = 0 ≠ decision-inert).
- "LLM terminal value on T9" is **not** supported — the check reads HypothesisManager state, not LLM output (INSTRUMENT_DEFECT).

---

## 5. Verdict on the WorldModel Causal Claim (Directive 4)

Classification: **TERMINAL_DISCRIMINATIVE (single-mechanism: scope-grounding)**.

Check-level decomposition (passed_checks/failed_checks per template) shows the entire −0.149 reduces to a single mechanism: loss of scope grounding causing out-of-scope action attempts (zero_prohibited failures on T2/T4/T7/T9/T10/T11). Every substantive cognitive check the ablation could plausibly threaten — identity resolution (T4: `same_host_identified` 30/30), semantic classification (T9: `semantic_classification_produced`, `llm_semantic_inference_used`), contradiction detection (T10: `contradiction_detected`, `decoy_falsified_via_discriminator`), hypothesis formation (T11: `hypotheses_formed`, `both_paths_in_hypothesis`) — passes unchanged. Combined with the confirmed absence of any shell-path interface-defect impact (0 shell candidates/actions in any of 3,240 runs), this promotes WorldModel from CONFOUNDED_ABLATION_EFFECT to TERMINAL_DISCRIMINATIVE, single-mechanism (scope-grounding), pending only the standard NoOp-contract repair (Fix 1) as a forward-looking hygiene item, not a retroactive validity threat to this specific estimate.
