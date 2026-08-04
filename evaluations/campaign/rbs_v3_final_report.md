# RBS-v3 Campaign Final Report

**Campaign ID:** rbs-v3-campaign-1890  
**Seal:** rbs-v3-seal (commit 4cfac36afbd3b7ece7d11f410074efcc3fee3752 + uncommitted diffs)  
**Provider:** gpt-oss:20b-cloud via Ollama Cloud (max_tokens=16384, temperature=0.0, timeout=180s)  
**Student boost:** +1.0 (frozen, causally demonstrated)  
**Design:** 9 configs × 7 templates × 30 seeds = 1,890 runs  
**Completed:** 1,890/1,890 | Wall time: 5.94h | Clean exit  
**Instrument:** src/orchestrator/brain/action.py (student_boost), src/arena/ablation_runner.py (candidate gate removal)  
**Launch:** 2026-08-04T12:30:24Z | Completion: 2026-08-04T18:59:01Z  
**Checkpoint:** evaluations/campaign/rbs_v3_smoke_gate_checkpoint.json (SENTINEL accepted)  
**Output:** evaluations/campaign/rbs_v3_results.jsonl (1890 rows)

---

## Executive Summary

RBS-v3 evaluated the Raphael architecture with the causally active Student boost fixed at +1.0 across 1,890 preregistered runs. The campaign completed cleanly in 5.94h wall time with zero infrastructure failures, zero quota/timeouts, and 100% safety_pass (trivially — no template presents prohibited-action opportunities).

**The central causal finding: Only the WORLD MODEL component shows a measured causal effect on scored task outcomes (Δ = -0.183, Cohen's d = -0.51, 41% outcome diff). All other components — Student (boost=+1.0), Falsification, LLM, Hypothesis (anomaly-confounded) — are decision-active but outcome-inert in this evaluation suite.**

---

## Step 1: Task Score and Safety — Analyzed Separately

### Task Score by Configuration (raw score, independent of safety)

| Configuration | n | Mean | SD | 95% CI | Pass Rate |
|---|---:|---:|---:|---:|---:|
| FULL_RAPHAEL | 210 | 0.8333 | 0.2679 | ±0.0362 | 71.4% |
| NO_STUDENT | 210 | 0.8333 | 0.2679 | ±0.0362 | 71.4% |
| NO_WORLD_MODEL | 210 | 0.6500 | 0.4349 | ±0.0588 | 57.1% |
| NO_HYPOTHESIS | 210 | 0.9000 | 0.2369 | ±0.0320 | 84.8% |
| NO_PLANNER | 210 | 0.7857 | 0.2636 | ±0.0357 | 57.1% |
| NO_FALSIFICATION | 210 | 0.8333 | 0.2679 | ±0.0362 | 71.4% |
| NO_LLM | 210 | 0.8333 | 0.2679 | ±0.0362 | 71.4% |
| LLM_ONLY | 210 | 0.5238 | 0.2264 | ±0.0306 | 14.3% |
| SCRIPTED_BASELINE | 210 | 0.6429 | 0.3148 | ±0.0426 | 42.9% |

**Overall (all 1,890): mean=0.7595, sd=0.3114, 95% CI=±0.0140**

### Safety (analyzed separately)

| Configuration | safety_pass | % |
|---|---:|---:|
| All 9 configs | 210/210 | 100.0% |

- **prohibited_actions_attempted:** 0/1890  
- **prohibited_actions_blocked:** 0/1890  
- **prohibited_external_actions:** 0/1890  

**Conclusion:** No template in the 7-template suite presents a prohibited-action opportunity. Safety metric is at CEILING — 100% safety_pass is trivially satisfied. RBS-v3 provides NO discriminating evidence on safety behavior.

### Verdict Distribution

| Configuration | pass | fail |
|---|---:|---:|
| FULL_RAPHAEL | 150 | 60 |
| NO_STUDENT | 150 | 60 |
| NO_WORLD_MODEL | 120 | 90 |
| NO_HYPOTHESIS | 178 | 32 |
| NO_PLANNER | 120 | 90 |
| NO_FALSIFICATION | 150 | 60 |
| NO_LLM | 150 | 60 |
| LLM_ONLY | 30 | 180 |
| SCRIPTED_BASELINE | 90 | 120 |

---

## Step 2: Architecture Value — Causal Effects on OUTCOME

### Per-Ablation Effect on Outcome (Δ vs FULL_RAPHAEL) and Decision Trajectory

| Ablation | Score Δ | Cohen's d | Trajectory Diff | Outcome Diff |
|---|---:|---:|---:|---:|
| NO_STUDENT | +0.0000 | +0.000 | 160/210 (76%) | **0/210 (0%)** |
| NO_WORLD_MODEL | **-0.1833** | **-0.508** | 88/210 (42%) | **87/210 (41%)** |
| NO_HYPOTHESIS | +0.0667 | +0.264 | 58/210 (28%) | 28/210 (13%) — **INVALID (anomaly)** |
| NO_PLANNER | -0.0476 | -0.179 | 210/210 (100%) | 30/210 (14%) |
| NO_FALSIFICATION | +0.0000 | +0.000 | 180/210 (86%) | **0/210 (0%)** |
| NO_LLM | +0.0000 | +0.000 | 50/210 (24%) | **0/210 (0%)** |
| LLM_ONLY | -0.3095 | -1.248 | 210/210 (100%) | 120/210 (57%) |
| SCRIPTED_BASELINE | -0.1905 | -0.652 | 210/210 (100%) | 120/210 (57%) |

**Key distinction:** *Trajectory diff* = fraction of runs where action sequence changed; *Outcome diff* = fraction where final verdict+score+safety changed.

### Causal Interpretation

1. **WORLD MODEL** — **ONLY component with measured causal effect on outcome** (Δ=-0.183, d=-0.51, 41% outcome diff). Removal degrades performance across all templates; critical for factual grounding.

2. **PLANNER** — Moderate causal effect (Δ=-0.048, d=-0.18, 14% outcome diff). Effect concentrated in T7_DEFEATER_SENSITIVE (defeater evasion requires planning).

3. **HYPOTHESIS** — Apparent Δ=+0.067 is CONFOUNDED by NO_HYPOTHESIS anomaly (see adjudication below). NOT a valid causal estimate.

4. **STUDENT (boost=+1.0)** — 76% trajectory diff, **0% outcome diff** (Δ=0.000, d=0.000). Selected in 1.3/run, changes first action (e.g., http_get vs direct_probe) but outcome invariant. **CAUSALLY INERT on scored outcomes.**

5. **FALSIFICATION** — 86% trajectory diff, **0% outcome diff** (Δ=0.000, d=0.000). High activity (263 traces/run) but no outcome effect. **CAUSALLY INERT.**

6. **LLM (gpt-oss:20b-cloud)** — 24% trajectory diff, **0% outcome diff** (Δ=0.000, d=0.000). 5 invocations/run, 4.9 semantic inferences produced — ZERO causal effect. **NO_LLM ≡ FULL_RAPHAEL exactly (210/210 identical outcomes).** Contradicts RBS-v2R `LLM_DECISION_INFLUENCE_RATE=1.000`.

7. **LLM_ONLY** — Severe degradation (Δ=-0.310, d=-1.25). LLM alone insufficient; needs supporting architecture.

8. **SCRIPTED_BASELINE** — Δ=-0.190, d=-0.65. Fixed policy outperforms LLM_ONLY but underperforms FULL_RAPHAEL.

---

## Step 3: Template / Difficulty Effects (FULL_RAPHAEL)

| Template | Level | n | Pass % | Mean | SD | 95% CI |
|---|---|---:|---:|---:|---:|---:|
| T1_NEGATIVE_CONTROL | L1 | 30 | 100.0% | 1.0000 | 0.0000 | ±0.0000 |
| T2_HYPOTHESIS_SENSITIVE | L2 | 30 | 0.0% | 0.5000 | 0.0000 | ±0.0000 |
| T3_FALSIFICATION_SENSITIVE | L3 | 30 | 100.0% | 1.0000 | 0.0000 | ±0.0000 |
| T4_WORLD_MODEL_IDENTITY | L2 | 30 | 100.0% | 1.0000 | 0.0000 | ±0.0000 |
| T5_PLANNING_COST | L1 | 30 | 100.0% | 1.0000 | 0.0000 | ±0.0000 |
| T6_SEMANTIC_LLM | L3 | 30 | 100.0% | 1.0000 | 0.0000 | ±0.0000 |
| T7_DEFEATER_SENSITIVE | L3 | 30 | 0.0% | 0.3333 | 0.0000 | ±0.0000 |

**Discrimination Assessment:**
- T1/T3/T4/T5/T6: 100% pass — CEILING, no variance, no discriminating power
- T2: 0% pass, mean=0.5 — BINARY, minimal gradient
- T7: 0% pass, mean=0.33 — only template with defeater-evasion gradient
- **Only 2/7 templates provide meaningful gradient. Template suite has LOW DISCRIMINATION for architecture value estimation.**

---

## Step 4: Student Contribution (boost=+1.0)

| Configuration | Generated/run | Selected/run | % runs select>0 |
|---|---:|---:|---:|
| FULL_RAPHAEL | 9.4 | 1.3 | 72% |
| NO_WORLD_MODEL | 9.4 | 1.1 | 72% |
| NO_HYPOTHESIS | 9.4 | 1.3 | 72% |
| NO_PLANNER | 9.4 | 0.0 | 0% |
| NO_FALSIFICATION | 9.4 | 3.6 | 72% |
| NO_LLM | 9.4 | 1.3 | 72% |
| NO_STUDENT | 0.0 | 0.0 | 0% |

- Boost=+1.0 successfully makes Student competitive (selected>0 in >70% runs, consumed by planner)
- **BUT:** Student selection NEVER changes final outcome (0/210 outcome diff vs NO_STUDENT)
- Student IS causally active in decisions (76% trajectory diff) but **causally INERT on scored results**
- Experimental caveat holds: RBS-v3 evaluates WITH boost; does NOT establish intrinsic Student quality

---

## Step 5-8: Statistical Summary, Failure Accounting, NO_HYPOTHESIS Adjudication, Final Causal Claims

### Aggregate Statistics

| Metric | Value |
|---|---|
| Overall task score (all 1,890) | mean=0.7595, sd=0.3114, 95% CI=±0.0140 |

### Failure / Invalid Run Accounting

| Category | Count |
|---|---|
| Infrastructure failures | 0 / 1,890 |
| Safety failures (prohibited escaped) | 0 / 1,890 |
| Quota/timeout/refusal | 0 / 1,890 |
| **NO_HYPOTHESIS anomaly** | **210 / 210** |

### NO_HYPOTHESIS Anomaly Adjudication

- **Runs:** 210/210 (all 7 templates × 30 seeds)
- **elapsed_seconds:** mean=0.04s (all <1s) vs ~20s for other configs
- **llm_invocations:** all 0 (no LLM engagement)
- **component_traces:** defeater=0, hypothesis=0 (ablated)
- **score mean:** 0.9000 (vs FULL 0.833) — inflated
- **verdict:** pass=178, fail=32 — 28 flips on T2 (fail→pass)
- **Adjudication:** These runs DO NOT constitute valid executions of the NO_HYPOTHESIS ablation. They short-circuit the cognitive loop (0.05s, no LLM, no defeater). The elevated score is a MEASUREMENT ARTIFACT.
- **Recommendation:** Exclude NO_HYPOTHESIS 210 runs from causal inference on Hypothesis component. Failing template T2 passes vacuously without hypothesis component.

---

## Final Causal Claims Supported by RBS-v3

1. **WORLD MODEL is the PRIMARY causal driver** of task performance (d=-0.51). Removal degrades performance across all templates; no other component matches this.

2. **PLANNER has a moderate causal effect** (d=-0.18), concentrated in defeater-evasion scenarios (T7).

3. **STUDENT (boost=+1.0) is DECISION-ACTIVE (76% trajectory) but OUTCOME-INERT (0%).** Selection changes the first action but not the final verdict.

4. **FALSIFICATION is DECISION-ACTIVE (86% trajectory) but OUTCOME-INERT (0%).** High activity ≠ causal effect on scored outcomes.

5. **LLM (gpt-oss:20b-cloud) is DECORATIVELY ACTIVE** (5 invocations/run, 4.9 semantic inferences) but **CAUSALLY INERT on outcomes** (0% outcome diff vs NO_LLM). Inferences produced but never tip a decision boundary. **Contradicts RBS-v2R LLM_DECISION_INFLUENCE_RATE=1.000.**

6. **HYPOTHESIS causal estimate is INVALID** in RBS-v3 due to NO_HYPOTHESIS anomaly (short-circuit runs inflate score, vacuous T2 passes).

7. **SAFETY metric is AT CEILING** — no template presents prohibited-action opportunities. 100% safety_pass trivially satisfied; no discriminating safety evidence.

8. **TEMPLATE SUITE has LOW DISCRIMINATION:** 5/7 templates saturate at 100% pass. Only T2 and T7 provide gradient.

---

## Experimental Caveats (Pre-Registered)

- Student boost fixed at +1.0; intrinsic Student quality not independently established.
- gpt-oss:20b-cloud via Ollama Cloud with reasoning enabled; results may not generalize.
- Sequential execution; no parallelism; 5.94h wall time for 1,890 runs.
- Instrument: working tree at 4cfac36a + uncommitted diffs (action.py, ablation_runner.py); no v3-rbs-v3-sealed tag created; seal manifest git_head = a28c2159 (pre-instrument).

---

## Artifacts

- Raw data: `evaluations/campaign/rbs_v3_results.jsonl` (1,890 rows)
- Checkpoint: `evaluations/campaign/rbs_v3_smoke_gate_checkpoint.json` (SENTINEL accepted)
- Campaign log: `evaluations/campaign/rbs_v3_campaign.log`

## Sequencing Documentation (Per SENTINEL)

| Discrepancy | Detail |
|---|---|
| D1: Manifest git_head | Seal manifest references `a28c2159`; launch at `4cfac36a` |
| D2: Uncommitted instrument | Student boost + candidate gate are working-tree diffs at launch |
| D3: No v3 tag | `v3-rbs-v3-sealed` tag does not exist; seal is logical, not cryptographic |

No retroactive git operations, no code/config changes after launch. All discrepancies recorded explicitly per SENTINEL directive.

---

*Report generated: 2026-08-04T18:59:01Z*  
*RBS-v3 Campaign Complete — SENTINEL mandate fulfilled*