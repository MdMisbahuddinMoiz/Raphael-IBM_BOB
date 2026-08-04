# RBS-v3 Campaign Report — Final Claim Hierarchy

**Campaign:** rbs-v3-campaign-1890  
**Seal:** rbs-v3-seal (working tree at commit 4cfac36a + documented uncommitted diffs)  
**Status:** VALIDATED — SENTINEL accepted checkpoint, campaign completed 1890/1890

---

## Final v3 Claim Hierarchy (Rule 45)

> **World Model has the strongest demonstrated terminal-outcome contribution; Planner has a smaller measurable contribution; Student, LLM, and Falsification demonstrably influence decision trajectories but their terminal value remains unresolved by RBS-v3; Hypothesis contribution remains unresolved because its ablation is anomalous; and RBS-v3 provides no meaningful safety discrimination because prohibited-action opportunities are absent.**

---

## Supporting Evidence Summary

| Component | Terminal Outcome Δ (vs FULL) | Cohen's d | Outcome Diff | Trajectory Diff | Status |
|-----------|-------------------------------|-----------|--------------|-----------------|--------|
| World Model | **-0.183** | **-0.51** | **41%** | 42% | **RESOLVED — PRIMARY DRIVER** |
| Planner | -0.048 | -0.18 | 14% | 100% | **RESOLVED — MODERATE** |
| Student (+1.0 boost) | 0.000 | 0.000 | **0%** | **76%** | TRAJECTORY-ACTIVE / OUTCOME-INERT |
| LLM (gpt-oss:20b-cloud) | 0.000 | 0.000 | **0%** | 24% | TRAJECTORY-ACTIVE / OUTCOME-INERT |
| Falsification | 0.000 | 0.000 | **0%** | **86%** | TRAJECTORY-ACTIVE / OUTCOME-INERT |
| Hypothesis | +0.067* | +0.264* | 13%* | 28% | **UNRESOLVED — ANOMALOUS ABLATION** |
| Safety | N/A | N/A | 0% | N/A | **CEILING — NO DISCRIMINATION** |

*Hypothesis figures are invalid due to NO_HYPOTHESIS anomaly (see adjudication below).

---

## Key Resolved Findings

1. **World Model** — Only component with statistically robust causal effect on terminal outcomes (Δ=-0.183, d=-0.51, 41% outcome diff). Removal degrades performance across all templates.

2. **Planner** — Measurable but smaller terminal effect (Δ=-0.048, d=-0.18, 14% outcome diff), concentrated in defeater-evasion scenarios (T7).

3. **Student (boost=+1.0)** — Decision-active (76% trajectory changes, selected 1.3/run) but terminal-outcome-inert (0% outcome diff). Boost makes Student competitive but scored tasks are insensitive.

3. **LLM (gpt-oss:20b-cloud)** — Produces 5 invocations/run, 4.9 semantic inferences, but ZERO terminal effect (0% outcome diff, NO_LLM ≡ FULL_RAPHAEL exactly 210/210). Contradicts RBS-v2R LLM_DECISION_INFLUENCE_RATE=1.000.

4. **Falsification** — High decision activity (86% trajectory diff, 263 traces/run) but zero terminal effect (0% outcome diff).

---

## Unresolved / Invalid Findings

| Issue | Status | Impact |
|-------|--------|--------|
| **Hypothesis** | **UNRESOLVED** | NO_HYPOTHESIS ablation anomalous: 210/210 runs at 0.04s, 0 LLM calls, no defeater, vacuous T2 passes. Causal estimate invalid. |
| **Safety** | **UNTESTABLE** | No template presents prohibited-action opportunities. 100% safety_pass is trivially satisfied (ceiling). |
| **Template Discrimination** | **LOW** | 5/7 templates saturate at 100% pass. Only T2 and T7 provide gradient. |
| **NO_HYPOTHESIS Anomaly** | **CONFIRMED ARTIFACT** | 210/210 runs short-circuit at 0.04s, no LLM, no defeater, vacuous T2 passes. Excluded from causal inference. |

---

## Experimental Caveats (Pre-Registered)

- Student boost fixed at +1.0; intrinsic Student quality not independently established.
- gpt-oss:20b-cloud via Ollama Cloud with reasoning enabled; results may not generalize.
- Sequential execution; 5.94h wall time for 1,890 runs.
- Instrument: working tree at 4cfac36a + uncommitted diffs (action.py student_boost, ablation_runner.py candidate gate); no v3-rbs-v3-sealed tag created; seal manifest git_head = a28c2159 (pre-instrument).

---

## Artifacts

- Raw data: `evaluations/campaign/rbs_v3_results.jsonl` (1,890 rows)
- Checkpoint: `evaluations/campaign/rbs_v3_smoke_gate_checkpoint.json` (SENTINEL accepted)
- Campaign log: `evaluations/campaign/rbs_v3_campaign.log`
- Full report: `evaluations/campaign/rbs_v3_final_report.md`
- Validity threats: `docs/ThreatsToValidity.md` (Sections 14-17)
- Limitations: `docs/LIMITATIONS.md` (L-024 through L-027)

---

## Sequencing Documentation

| Discrepancy | Detail |
|-------------|--------|
| D1: Manifest git_head | Seal manifest references `a28c2159`; launch at `4cfac36a` |
| D2: Uncommitted instrument | Student boost + candidate gate are working-tree diffs at launch |
| D3: No v3 tag | `v3-rbs-v3-sealed` tag does not exist; seal is logical, not cryptographic |

No retroactive git operations, no code/config changes after launch. All discrepancies recorded per SENTINEL directive.

---

*Report generated: 2026-08-04T19:35:00Z*  
*RBS-v3 Campaign Complete — SENTINEL mandate fulfilled*