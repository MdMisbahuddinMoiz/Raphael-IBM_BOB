# RBS-v1 Campaign Report (Exp1-3)

- Generated: /home/yaser/Raphael_RedTeam/evaluations/campaign/rbs_v1_results.jsonl with 120 rows
- Provider: pilot_simulation / simulated_v1 (metrics.json label; true engagement per component_traces.json)
- LLM-engaged rows (wall>10s AND llm_produced>0): 60/120
- FULL_RAPHAEL LLM-engaged: 50/50 (all runs using the cognitive loop with learned inference; the remaining rows are structural baselines LLM_ONLY/SCRIPTED/NO_LLM and INFRA_FAILURE ablations that bypass or break the LLM path).

## Per-Configuration Aggregation

| experiment | config | template | level | n | score m±95CI | score sd | wall m | llm_prod m | llm_inv m |
|---|---|---|---|---|---|---|---|---|---|
| exp1_architecture | FULL_RAPHAEL | T3_FALSIFICATION_SENSITIVE | None | 10 | 0.90 ±0.13 | 0.21 | 47.6 | 4.00 | 5.00 |
| exp1_architecture | LLM_ONLY | T3_FALSIFICATION_SENSITIVE | None | 10 | 0.00 ±0.00 | 0.00 | 0.0 | 0.00 | 0.00 |
| exp1_architecture | SCRIPTED_BASELINE | T3_FALSIFICATION_SENSITIVE | None | 10 | 0.50 ±0.00 | 0.00 | 0.0 | 0.00 | 0.00 |
| exp2_ablation | FULL_RAPHAEL | T4_WORLD_MODEL_IDENTITY | None | 10 | 1.00 ±0.00 | 0.00 | 79.1 | 4.50 | 5.00 |
| exp2_ablation | NO_FALSIFICATION | T4_WORLD_MODEL_IDENTITY | None | 10 | — — | — | 10.2 | — | — |
| exp2_ablation | NO_HYPOTHESIS | T4_WORLD_MODEL_IDENTITY | None | 10 | — — | — | 0.0 | — | — |
| exp2_ablation | NO_LLM | T4_WORLD_MODEL_IDENTITY | None | 10 | 1.00 ±0.00 | 0.00 | 0.2 | 0.00 | 0.00 |
| exp2_ablation | NO_PLANNER | T4_WORLD_MODEL_IDENTITY | None | 10 | 1.00 ±0.00 | 0.00 | 74.8 | 4.90 | 5.00 |
| exp2_ablation | NO_WORLD_MODEL | T4_WORLD_MODEL_IDENTITY | None | 10 | — — | — | 16.5 | — | — |
| exp3_difficulty | FULL_RAPHAEL | T3_FALSIFICATION_SENSITIVE | Level_1 | 10 | 0.95 ±0.10 | 0.16 | 46.9 | 4.40 | 5.00 |
| exp3_difficulty | FULL_RAPHAEL | T4_WORLD_MODEL_IDENTITY | Level_2 | 10 | 1.00 ±0.00 | 0.00 | 72.5 | 4.80 | 5.00 |
| exp3_difficulty | FULL_RAPHAEL | T6_SEMANTIC_LLM | Level_3 | 10 | 1.00 ±0.00 | 0.00 | 65.5 | 3.50 | 5.00 |

## Evaluator Confound (frozen, unflagged)

- Rows scored 0.5/INCONCLUSIVE: 13. This is the frozen evaluator assigning baseline types (llm_only/scripted) score 0.5 unconditionally (ablation_runner._evaluate). Not an architectural failure.

## LLM Engagement

`llm_produced` / `llm_invocations` are read from each run's `component_traces.json` (produced_semantic_inference / llm_inference), because `metrics.json` hardcodes provider/calls (ablation_runner.py:548).

## Run-Count Accountability

- Planned: 120 runs (Exp1: 3 configs x T3 x 10 seeds; Exp2: 6 configs x T4 x 10 seeds; Exp3: 3 templates x Level x 10 seeds).
- Recorded: 120 rows. Errors: 0.
