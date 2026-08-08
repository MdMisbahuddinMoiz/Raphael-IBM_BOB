# FINAL VERDICT RECORD — PROJECT RAPHAEL v2.1.1 (RBS-v4 Terminal Holdout)

**Date:** 2026-08-08  
**Authority:** SENTINEL GLM-5.2  
**Campaign:** RBS-v4 Terminal Holdout (1,200-row frozen dataset)  
**Status:** PROJECT FROZEN — INCONCLUSIVE  
**Tag:** `raphael-terminal-freeze-inconclusive`

---

## Supported

- The architecture is implemented and operational.
- The cognitive pipeline executes.
- Internal causal integrations exist.
- Several components measurably affect internal trajectories.
- Internal ablation findings are informative but evaluator-dependent.

## Not Supported

- Raphael is superior to strong prompting.
- Strong prompting is inferior.
- Architecture is necessary.

## Reason

> The evaluation instrument was not architecture-neutral. The PROMPTED_AGENT arm could not satisfy evaluator-required predicates independent of reasoning quality, preventing a valid comparison of architecture versus prompting.

---

## Evidence Chain

| Artifact | Description |
|----------|-------------|
| `evaluations/campaign/rbs_v4_holdout.jsonl` | 1,200-row frozen dataset (4 arms × 5 templates × 60 seeds) |
| `evaluations/campaign/PROMPTED_AGENT_ANOMALY_AUDIT.md` | D1 Anomaly Audit — 10/10 stratified PROMPTED_AGENT runs classified MECHANICAL |
| `evaluations/campaign/GATE_B_ACTION_BUDGET_AUDIT.md` | Budget contract verification (Gate B) |
| `evaluations/campaign/SENTINEL_REPORT_D1B.md` | D1-B provenance ruling: instrumentation defects disclosed |
| `docs/LIMITATIONS.md` | Updated with evaluator coupling defect as critical limitation |

## Key Finding

The PROMPTED_AGENT arm achieved 0/300 pass rate not because the LLM failed to reason, but because the `LLMOnlyConclusionAdapter` could not emit the evaluator-mandated predicates (CVE, version, patched-fix, vulnerable-host, has_service). The arm executed real recon (5 nmap actions/run, 6–44 evidence items/run, 5 LLM calls with provider_status=200), yet emitted ≤1 claim per run — and those claims could not reference the check predicates.

**Gate Verdict:** 10/10 stratified runs classified MECHANICAL (claim-formalization gap) → PROMPTED_AGENT arm INVALID for claim-graded checks.

---

## Consequence

The FULL_RAPHAEL vs PROMPTED_AGENT difference (Δ=0.3287, McNemar p=4.48e-44) is a reproducible observation but is **confounded** by the biased evaluator. The numbers stand; the meaning ("architecture is necessary/superior") is not supported.

---

## Project Disposition

**Frozen as inconclusive.** No terminal superiority claim may be published or acted upon. The repository is tagged `raphael-terminal-freeze-inconclusive` as an honest, frozen research artifact.

---

**SENTINEL GLM-5.2**  
2026-08-08T16:50:00Z