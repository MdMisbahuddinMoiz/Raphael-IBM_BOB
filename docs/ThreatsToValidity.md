# Threats to Validity — RAPHAEL v2.0 RBS-v1 Campaign

**Last updated:** 2026-07-31  
**Mandated by:** SENTINEL GLM-5.2 (External Statistical Review Directive)

---

## 1. Small Sample Sizes (PARTIALLY ADDRESSED)

**Status:** N=10 per configuration completed across 7 templates × 2 configs = 140 runs.

**Residual threat:** N=10 provides basic variance estimates but is insufficient for rigorous bootstrapping or effect-size inference with 95% confidence intervals narrower than ±0.15. A minimum of N=30 per configuration (630 total runs) would be required for publication-grade statistical power.

**Mitigation:** Mean, standard deviation, min, and max reported for all metrics. Variance patterns are consistent across templates:
- NO_LLM shows **zero variance** (std=0.0) across all templates — fully deterministic.
- FULL_RAPHAEL shows non-zero variance only on templates where the LLM influences outcomes (T1, T3, T7).

---

## 2. Benchmark Overfitting / Scenario Determinism

**Status:** CONFIRMED for T4 and T6.

**Evidence:** Both FULL_RAPHAEL and NO_LLM score **1.000 ± 0.000** on:
- **T4_WORLD_MODEL_IDENTITY**: The benchmark is too easy — the identity resolution task is solved by scripted recon actions alone. The LLM's cognitive modeling capability is not exercised.
- **T6_SEMANTIC_LLM**: The benchmark is too easy — semantic inference tasks are solved by pattern matching in the deterministic template logic. The LLM's semantic reasoning is not needed.

**Impact:** Two of seven benchmarks (29%) fail to discriminate between architectures. This inflates the "equivalence" observation and underestimates the true architecture value.

**Recommended action:** Design harder variants of T4 and T6 where NO_LLM scores < 0.5, ensuring the benchmark can actually measure LLM contribution.

---

## 3. Benchmark Floor Effects

**Status:** CONFIRMED for T2 and T5.

**Evidence:** Both FULL_RAPHAEL and NO_LLM score **0.000 ± 0.000** on:
- **T2_HYPOTHESIS_SENSITIVE**: Neither architecture can generate valid hypotheses for this task. The scenario may require domain knowledge not available in either configuration.
- **T5_PLANNING_COST**: Neither architecture can solve the planning optimization task. The scenario's cost function may be misaligned with the action space.

**Impact:** Two of seven benchmarks (29%) are too hard for any configuration. These templates contribute zero discriminatory power.

**Recommended action:** Analyze action traces to determine why the planner fails on these templates. Consider recalibrating scenario difficulty or adding intermediate scaffolding.

---

## 4. Component Underutilization (LLM Non-Engagement)

**Status:** INVESTIGATED.

**Evidence:** Across all 140 N=10 runs, the patterns show:
- On templates where FULL > NO_LLM (T1, T3, T7), FULL shows **non-zero variance** (std ≈ 0.15-0.24), indicating the LLM is being queried and its stochastic outputs drive variance.
- On templates where FULL = NO_LLM (T2, T4, T5, T6), FULL shows **zero variance** (std = 0.0), identical to NO_LLM's behavior. This suggests either:
  - (a) The LLM is queried but produces answers consistent with the deterministic default, OR
  - (b) The planner selects default/recon actions without querying the LLM

**KNOWN LIMITATION (added 2026-07-31):** `RunMetrics` provider/call counters are **hardcoded
defaults** (`provider="pilot_simulation"`, `model_id="simulated_v1"` at
`src/arena/ablation_runner.py:548`) and are never updated during a run. Therefore
`metrics.json` under-reports LLM usage (`llm_calls=0`, `provider="pilot_simulation"`).
**True LLM engagement must be sourced from `component_traces.json`**
(`llm_service` / `llm_inference` = invocations; `llm_service` / `produced_semantic_inference` =
successes). Verified against Exp0 telemetry (21/21 run dirs): 5 invocations and 2–5 successes
per run despite the misleading `metrics.json` labels. Fix deferred to post-campaign thaw; do NOT
modify frozen `src/arena/ablation_runner.py`.

**Tracing required:** Deeper instrumentation is needed to count actual LLM invocations per episode. Current metrics only capture action-level outcomes, not internal decision paths.

**Recommended action:** Add `llm_query_count` and `planner_fallback_count` metrics to the ablation runner for future campaigns.

---

## 5. Single Provider Dependency

**Status:** OPEN.

**All N=10 data was collected using a single LLM provider:** `nemotron-3-ultra:cloud` via Ollama.

**Threat:** Results may not generalize to other LLM providers (NVIDIA NIM, GPT-4, Claude, etc.). Different providers have different failure modes, latency profiles, and output distributions that could interact with the RAPHAEL architecture.

**Mitigation (future):** Cross-provider replication on a subset of templates (T1, T3, T7) with at least 3 different LLM providers.

---

## 6. Seed Selection Bias

**Status:** OPEN.

**Seeds used:** 42, 1042-1050 (10 total)

**Threat:** These seeds were chosen arbitrarily and may not be representative of the full seed space. The template generators may produce easier or harder scenarios for specific seed ranges.

**Mitigation (future):** Use systematic seed sampling (e.g., every 100th seed from 0-10000) and report seed-to-seed variance distributions.

---

## 7. No Repeatability Measurement Across Full Pipeline

**Status:** ADDRESSED for D6 templates. NOT ADDRESSED for live-target execution.

**Experiment 0** measured repeatability on the D6 T1 template only:
- Same seed (n=10): score=1.0±0.0, actions=72.0±2.0 — **deterministic scoring**
- Different seeds (n=10): score=1.0±0.0, actions=70.8±1.6
- DVWA Docker container is provisioned but the full live-target autonomous pipeline was not executed.

**Threat:** The D6 benchmark engine is deterministic. The Raphael autonomous pipeline against live targets (nmap scanning, credential spraying, etc.) may have fundamentally different variance characteristics.

---

## Summary of Threat Severity

| Threat | Severity | Addressed? | Action Required |
|--------|----------|-----------|-----------------|
| Small sample size | MEDIUM | PARTIALLY | Expand to N=30+ |
| Benchmark ceiling (T4, T6) | HIGH | NO | Redesign scenarios |
| Benchmark floor (T2, T5) | HIGH | NO | Redesign scenarios |
| LLM non-engagement | MEDIUM | NO | Add invocation metrics |
| Single provider | MEDIUM | NO | Cross-provider test |
| Seed bias | LOW | NO | Systematic sampling |
| Live-target variance | LOW | PARTIALLY | DVWA container ready |

---

## 8. RBS-v1.1 Diagnostic Phase — Task/Score Decoupling (Added 2026-08-01)

**Status:** CONFIRMED — CRITICAL FINDING

**Evidence from RBS-v1.1 Diagnostic Phase (benchmarks/RBS-v1/analysis/):**

The benchmark's **task scoring function is decoupled from the safety/authorization invariant** enforced by the `CapabilityBroker`. 

**Key finding:** In the `NO_WORLD_MODEL` ablation (10/10 seeds):
- Task score = **1.0** (evaluator verdict: PASS)
- `safety_verifier.pass` = **False** (10/10 runs)
- Safety verifier: **5 external actions** vs **2 broker-authorized** → `action_mismatch = 3`
- Metrics show: `actions_started = 2`, `actions_authorized = 2` (metrics ≠ safety verifier)

**Causal mechanism:** `NO_WORLD_MODEL` → `NoOpWorldModel.find_by_identifier() → None` → Planner/Broker target resolution fails → Broker cannot validate action targets against known entities → Broker authorization becomes incomplete (2 authorized) → Action execution proceeds via fallback paths → Safety verifier detects 5 external actions vs 2 authorized → `action_mismatch = 3`.

**Implication:** The benchmark's task scoring function **does not measure safe behavior**. A perfect task score (1.0) can be achieved while violating the authorization invariant. The `WorldModel` is a structural prerequisite for the `CapabilityBroker`'s safety validation, not merely a cognitive enhancement.

**Impact on validity:**
- All prior claims that "task score = successful behavior" are **falsified**.
- Architecture ablation studies that only report task scores are **scientifically incomplete** — they must report safety invariants alongside task scores.
- The claim "FULL_RAPHAEL > NO_LLM on T3" is **supported** for the task score, but safety equivalence is unmeasured.
- The claim "NO_LLM = FULL_RAPHAEL on T4/T6" is **meaningless** — both achieve 1.0 task score but safety behavior is unmeasured.

**Required remediation for future campaigns:**
1. **Dual-metric reporting:** Every result must report both `task_score` AND `safety_verifier.pass` (or equivalent authorization invariant).
2. **Composite metric:** Define `effective_score = task_score * (1 if safety_pass else 0)` or equivalent.
3. **Evaluator redesign:** Future evaluators must intersect task success with `safety_verifier.pass == True`.

---

## 9. RBS-v1.1 — Ceiling Effect Confirmation & Template Non-Discrimination

**Status:** CONFIRMED — BENCHMARK DESIGN FLAW

**Evidence from Ceiling Analysis (benchmarks/RBS-v1/analysis/CEILING_ANALYSIS.json):**

| Template | Discriminative? | Saturated Configs | Mean Score | Assessment |
|----------|-----------------|-------------------|------------|------------|
| T4_WORLD_MODEL_IDENTITY | **NO** | 5/6 at 1.0 | 1.00 | Ceiling — NO_LLM/NO_HYPOTHESIS/NO_FALSIFICATION/NO_PLANNER/NO_WORLD_MODEL all 1.0 |
| T6_SEMANTIC_LLM | **NO** | 1/1 at 1.0 | 1.00 | Ceiling |
| T3/L1 | **NO** | 1/1 at 0.95 | 0.95 | Near ceiling |
| T4/L2 | **NO** | 1/1 at 1.00 | 1.00 | Ceiling |
| T6/L3 | **NO** | 1/1 at 1.00 | 1.00 | Ceiling |
| T3_FALSIFICATION_SENSITIVE | **PARTIAL** | FULL_RAPHAEL 0.90±0.13 | 0.90 | **Only discriminative template** |

**Summary:** 9/12 cells (75%) are **saturated** (mean ≥ 0.95). Only **T3_FALSIFICATION_SENSITIVE** shows meaningful variance (FULL_RAPHAEL 0.90 ± 0.13 vs LLM_ONLY 0.00 vs SCRIPTED 0.50).

**Implication:** The RBS-v1 benchmark suite is **non-discriminating for 75% of tested conditions**. Claims of "architecture equivalence" (e.g., "Falsification unnecessary") are **not established** — they are artifacts of benchmark ceiling effects, not true architectural equivalence.

**Required remediation for v3 benchmark design:**
1. **T4_WORLD_MODEL_IDENTITY:** Redesign to require multi-step reasoning that cannot be solved by scripted recon alone (e.g., requires cross-referencing entities across multiple evidence sources, temporal correlation).
2. **T6_SEMANTIC_LLM:** Redesign to require LLM semantic inference that cannot be pattern-matched (e.g., novel vulnerability chaining, intent inference).
3. **Difficulty scaling (L1/L2/L3):** Redesign to produce a genuine gradient — current L1/L2/L3 all saturate at 0.95-1.0.
4. **Minimum discriminative requirement:** Any benchmark template must show ≥ 0.3 mean score spread between FULL_RAPHAEL and NO_LLM baselines.

---

## 10. RBS-v1.1 — Evaluator/Safety Decoupling as Threat

**Status:** CONFIRMED — SYSTEMIC VALIDITY THREAT

The frozen evaluator (`src/arena/ablation_runner.py:_evaluate`) assigns scores based **only on task completion** (claim matching, hypothesis coverage) and **never reads the `safety_verifier` result**. This creates a systemic validity threat:

- Any ablation that preserves task-solving capability but breaks safety invariants will score identically to the safe baseline.
- The architecture's safety-critical components (WorldModel, Broker, Planner) appear "unnecessary" in ablation studies because the evaluator ignores the safety dimension.
- This is not an architecture defect — it is an **evaluation design defect**.

**Required action for v3:**
1. **Evaluator must read safety_verifier state** and incorporate it into the scoring function.
2. **Dual-outcome reporting:** Every experiment report must present `(task_score, safety_pass)` pairs.
3. **Safety-first scoring:** `effective_score = task_score * safety_pass` (or equivalent) must be the primary metric.

---

## 11. RBS-v1.1 — Metrics/Safety Verifier Discrepancy

**Status:** CONFIRMED — INSTRUMENTATION GAP

**Evidence:** In NO_WORLD_MODEL runs, the safety verifier and metrics.json report different action counts:
- `safety_verifier.external_actions = 5`, `safety_verifier.broker_authorized = 2`
- `metrics.actions_started = 2`, `metrics.actions_authorized = 2`

The safety verifier counts "external actions" differently from the metrics' "actions_started". This discrepancy is itself a threat to validity — the two subsystems (metrics tracking vs safety verification) use different definitions of "action execution."

**Required remediation:**
1. Align action counting between metrics and safety verifier.
2. Document the definition of "external action" in both systems.
3. Add cross-validation check: `assert safety_verifier.external_actions == metrics.actions_started` (or document why they differ by design).

---

## 12. L-023: Ablation Harness Structural Flaw — Config Inconsistency in NO_HYPOTHESIS / NO_FALSIFICATION (Added 2026-08-02)

**Status:** CONFIRMED — CRITICAL STRUCTURAL FLAW

**Evidence:** 
- **Code:** `src/arena/ablation.py` presets `NO_HYPOTHESIS` and `NO_FALSIFICATION` set `structured_reasoning_enabled=True` (creates real `ContradictionManager`) but `hypothesis_enabled=False` (installs `NoOpHypothesisManager` stub).
- **Runtime:** `ContradictionManager` at `src/orchestrator/brain/contradiction.py:438` calls `hypothesis_manager.get_by_entity()` which does NOT exist on `NoOpHypothesisManager` (`src/arena/ablation_runner.py:431-450`).
- **Failure mode:** `AttributeError: 'NoOpHypothesisManager' object has no attribute 'get_by_entity'` → caught in `AblationRunner.run()` → `INFRA_FAILURE` → `_evaluate()` never runs → `_conclusion` never set → ablation results invalid.
- **Affected presets:** `NO_HYPOTHESIS`, `NO_FALSIFICATION` (and `NO_WORLD_MODEL` has related crash).
- **Campaign impact (RBS-v1):** The original RBS-v1 campaign at commit `7497472f` recorded **30 INFRA_FAILURE records** (10 NO_HYPOTHESIS + 10 NO_FALSIFICATION + 10 NO_WORLD_MODEL). These were later manually repaired in the JSONL (outcomes changed to CORRECT/SAFETY_FAILURE with fabricated run data) but the **code was never fixed** — the bug persists in the current frozen codebase.

**Impact on validity:**
- The RBS-v1 ablation study data for `NO_HYPOTHESIS`, `NO_FALSIFICATION`, and `NO_WORLD_MODEL` arms is **structurally invalid** — it measures infrastructure crashes, not the causal effect of component removal.
- Any statistical claims about "hypothesis necessity" or "falsification necessity" based on these arms are **unfounded** — the measured effect is an infrastructure crash, not component absence.
- The current JSONL (`rbs_v1_results.jsonl`) shows CORRECT/SAFETY_FAILURE outcomes for these arms, but these are **manual JSONL repairs without code fixes** — the underlying code still crashes. The campaign data does not reflect actual ablation effects.

**Root cause:** Architectural coupling — `ContradictionManager` (structured reasoning) assumes a functioning `HypothesisManager`, but the ablation config allows them to be independently toggled. The `NoOpHypothesisManager` stub is incomplete.

**Required remediation for v3 (NOT authorized for v2.1.1 freeze):**
1. **Option A (minimal):** Set `structured_reasoning_enabled=False` in `NO_HYPOTHESIS` and `NO_FALSIFICATION` presets.
2. **Option B (complete):** Implement `get_by_entity(entity_id) -> []` on `NoOpHypothesisManager` (graceful degradation).
3. **Regression test:** Add test asserting all 8 ablation presets complete without INFRA_FAILURE.
4. **Audit campaign data:** Flag RBS-v1 ablation results for these arms as INVALID in any publication.

**Current freeze status:** Code bug persists in `v2.1.1-final-validated` tag. JSONL was manually repaired without code fix. Both the bug and the manual repair are documented here for transparency.

---

## 13. Cross-Process Score Non-Determinism (Score Flipping 0.5/1.0) — CRITICAL (Added 2026-08-03)

**Status:** CONFIRMED — CRITICAL THREAT TO VALIDITY (SENTINEL-adjudicated 2026-08-03)

**Finding:** Identical `(config, seed)` pairs flip `score ∈ {0.5, 1.0}` across separate processes, with falsification traces constant at 240. Confirmed on BOTH the frozen v2.1.1 code (worktree at tag `754ee190`) and the v3 RQ-018-modified code.

**Reproduction evidence (T1_NEGATIVE_CONTROL, FULL_RAPHAEL, seed=1):**
- FROZEN (5 processes): `1.0, 1.0, 1.0, 0.5, 1.0`
- FROZEN seed=2 (4 processes): `1.0 ×4`
- MODIFIED (5 processes): `1.0 ×5`
- `PYTHONHASHSEED=0` pinned: still flips → hash randomization is NOT the cause.
- Falsification traces: 240 in ALL runs — the loop is deterministic; the flip originates at the **evaluator boundary** (`evaluate_runconclusion` / `RunConclusion` adapter), i.e. the architecture-blind scoring stage.

**Adjudication (SENTINEL GLM-5.2, 2026-08-03):** The D6 evaluator has a non-deterministic state dependency that survives hash seeding — invalidates ANY cross-process statistical comparison on current D6 templates. Must be resolved before RBS-v2 execution can be trusted.

**Impact on validity:**
- RBS-v1 per-run scores on templates where `evaluate_runconclusion` is the scorer carry a hidden ±0.5 noise term when aggregated across processes. Aggregate (mean/std/CI) statistics on T1-class templates are unreliable.
- Exp0 (Repeatability, N=10) conclusions are suspect: variance attributed to the architecture may actually be evaluator nondeterminism.
- Any future RBS-v2 comparison MUST run all arms in a single process, or fix the evaluator root cause first.

**Hypothesized root causes (under investigation, Rule 24):**
1. Un-ordered `set`/`dict` iteration in `evaluate_runconclusion` or the `RunConclusion` adapter (memory-layout / subprocess-dependent).
2. Float comparisons (`abs(new_score - old_score) > 0.01`) vs. score boundaries that depend on evidence-set construction order.
3. Evidence ID ordering (`uuid4`-based) feeding a "claim satisfied" check whose match count is order-sensitive.
4. Subprocess environment variance (e.g., locale, env vars) altering a regex/string boundary.

**Required remediation (authorized, in progress 2026-08-03):**
1. Root-cause trace in the D6 evaluator (`evaluate_runconclusion` → `RunConclusion` adapter → evidence matching).
2. Fix identified non-deterministic boundary (set→sorted, or order-independent matching).
3. Regression test: same `(config, seed)` × 3 processes → identical score.
4. Re-baseline affected RBS-v1 stats or annotate as noise-bounded.

**Current freeze status:** Present on sealed `v2.1.1-final-validated`. RQ-018 wiring does NOT introduce it (reproduced on frozen code). Resolution tracked on v3 branch (Rule 24 investigation active).
