# D2 SENSITIVITY TABLE REPORT (SENTINEL Directive 2)

**Status:** COMPLETE
**Date (UTC):** 2026-08-08
**Source data:** `evaluations/campaign/rbs-v4_holdout.jsonl` (1,200 rows, paired by (template, seed) with infra-invalid seeds 15 & 57 excluded per TERMINAL_VALIDATION_FREEZE)
**Replaces:** The post-hoc Δ≥0.10 "adjudication" bar used in earlier narrative — replaced by a full sensitivity curve per comparison and per family.

---

## 1. Summary Table (Aggregate, n=290 per comparison)

| Comparison | n_pairs | Δ≥0.00 | Δ≥0.05 | **Δ≥0.10** | Δ≥0.15 | Δ≥0.20 | Δ≥0.25 | **Δ≥0.30** | Δ≥0.35 | Δ≥0.40 | Δ≥0.50 | Δ≥0.60 | Δ≥0.70 | mean_diff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **FULL_vs_PROMPTED** (primary, central thesis) | 290 | 99.3% | 66.9% | **66.9%** | 66.9% | 66.9% | 66.9% | **66.9%** | 32.4% | 32.4% | 32.4% | 0.0% | 0.0% | 0.3287 |
| FULL_vs_NO_WORLD_MODEL (secondary, world-model) | 290 | 100.0% | 54.5% | **54.5%** | 54.5% | 54.5% | 54.5% | **54.5%** | 27.6% | 27.6% | 27.6% | 0.0% | 0.0% | 0.2736 |
| FULL_vs_SCRIPTED (secondary, operator utility) | 290 | 95.5% | 54.8% | **54.8%** | 54.8% | 54.8% | 54.8% | **54.8%** | 14.1% | 14.1% | 14.7% | 0.0% | 0.0% | 0.2149 |

**Interpretation of the Δ≥0.10 column (former "adjudication bar"):**  
At the former "Δ≥0.10 bar," the three comparisons show 66.9%, 54.5%, and 54.8% of paired cells exceeding the threshold — not a binary pass/fail but a continuous sensitivity. The former narrative treated Δ≥0.10 as a binary adjudication gate; this table replaces it with the full sensitivity curve.

---

## 2. Family-Level Breakdown (FULL_vs_PROMPTED, n=58 per family)

| Family | n | Δ≥0.00 | Δ≥0.05 | **Δ≥0.10** | Δ≥0.15 | Δ≥0.20 | Δ≥0.25 | **Δ≥0.30** | Δ≥0.35 | Δ≥0.40 | Δ≥0.50 | mean_diff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **known-observable** | 58 | 100% | 100% | **100%** | 100% | 100% | 100% | **100%** | 32.8% | 32.8% | 32.8% | 0.4425 |
| **false-lead** | 58 | 100% | 100% | **100%** | 100% | 100% | 100% | **100%** | 79.3% | 79.3% | 79.3% | 0.5977 |
| **contradiction** | 58 | 100% | 56.9% | **56.9%** | 56.9% | 56.9% | 56.9% | **56.9%** | 32.8% | 32.8% | 32.8% | 0.2989 |
| **forbidden-proximity** | 58 | 96.6% | 58.6% | **58.6%** | 58.6% | 58.6% | 58.6% | **58.6%** | 0.0% | 0.0% | 0.0% | 0.1839 |
| **signal-noise** | 58 | 100% | 19.0% | **19.0%** | 19.0% | 19.0% | 19.0% | **19.0%** | 17.2% | 17.2% | 17.2% | 0.1207 |

**Key observation:** The central-thesis advantage is **highly heterogeneous across families**. Known-observable and false-lead show near-universal FULL advantage (100% at Δ≥0.10, 100% at Δ≥0.30), while signal-noise shows only 19% at Δ≥0.10 and forbidden-proximity shows 58.6% at Δ≥0.10. The aggregate 66.9% at Δ≥0.10 is a weighted average of highly different family behaviors.

---

## 3. What This Replaces

The previous narrative treated **Δ≥0.10 as a binary "adjudication bar"**: if the mean FULL−PROMPTED difference exceeded 0.10, the comparison was "adjudicated" as favoring FULL. That post-hoc threshold was:

- Not preregistered (TERMINAL_FALSIFICATION_PREREGISTRATION.json and TERMINAL_VALIDATION_FREEZE.json contain no numeric advantage threshold).
- Arbitrary (0.10 was chosen post-hoc).
- Binary, discarding the continuous distribution of paired differences.

This sensitivity table replaces that bar with:
- A **full sensitivity curve** per comparison (aggregate and per family).
- The raw proportion of paired cells exceeding each Δ threshold.
- The mean difference for context.
- No binary adjudication — just the continuous evidence.

---

## 4. Connection to Paired Statistical Tests

The paired McNemar exact tests in TERMINAL_ANALYSIS_RESULTS.json remain the primary inferential statistics:

| Comparison | n_pairs | McNemar exact p | Cliff δ | Cliff δ 95% CI |
|---|---|---|---|---|
| FULL_vs_PROMPTED | 290 | 4.48×10⁻⁴⁴ | 0.5948 | [0.5905, 0.5991] |
| FULL_vs_NO_WORLD_MODEL | 290 | 3.16×10⁻³⁰ | 0.4798 | [0.4749, 0.4847] |
| FULL_vs_SCRIPTED | 290 | 5.74×10⁻⁴² | 0.4192 | [0.4141, 0.4244] |

All three significant at Bonferroni-adjusted α = 0.0167. The sensitivity table does not replace these — it supplements them by showing **how many paired cells exceed each Δ threshold**, which the p-value/δ do not directly show.

---

## 5. D2 Complete

**Deliverable:** This sensitivity table (aggregate + family-level) now stands as the D2 artifact, replacing the post-hoc Δ≥0.10 adjudication bar. The TERMINAL_ANALYSIS_RESULTS.json retains its statistical primacy; this table is the descriptive supplement mandated by SENTINEL.

**Next (D3):** Independent recomputation from fresh session + diff vs TERMINAL_ANALYSIS_RESULTS.json.