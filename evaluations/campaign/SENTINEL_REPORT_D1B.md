# SENTINEL REPORT — D1-B: BUG OR ABLATION? (provenance + mechanism ruling)

**Status:** COMPLETE
**Date (UTC):** 2026-08-08
**Author:** RBS-v1 EVALUATION CAMPAIGN (Raphael-Forge v4)
**Supersedes:** PROMPTED_AGENT_ANOMALY_AUDIT.md §1–4 mechanism attribution (one
fact corrected below: the adapter actually used was FullConclusionAdapter via
registry fallback, NOT LLMOnly).

---

## 1. SENTINEL question

> Was PROMPTED_AGENT's failure (a) a harness bug — the conclusion adapter
> accidentally omitting the semantic-claim path — or (b) the ablation doing
> exactly what it was designed to do (raw prompting, no formal claim layer)?

---

## 2. Findings

### 2.1 Fix: which adapter ACTUALLY ran for PROMPTED_AGENT

`get_adapter(config_id)` (`src/arena/conclusion_adapters.py:1138`) has no
`"PROMPTED_AGENT"` key; the mapping ends with `mapping.get(config_id,
FullConclusionAdapter)`. All 300 PROMPTED rows in the JSONL carry
`adapter_name=FullConclusionAdapter` — confirmed from the data, not inferred
(zero `adapter_error_events`; `run_conclusion.json` stamped
`architecture_id: "FULL_RAPHAEL"` — a labeling defect, see §2.4).

Under the Full adapter with the PROMPTED config (hypothesis=False,
world_model=False, planner=False, falsification=False, defeater=False,
student=False) the hypothesis-derived claim sources **cannot fire**: traces show
zero `hypothesis.*` operations for PROMPTED (vs 40+ for FULL). So the semantic
path (`_semantic_inference_to_claims`, gated on `hypothesis_manager`) yields
nothing — not because the code path is missing from the adapter, but because
the manager for this arm is empty by configuration. Only evidence-derived
direct-observation claims survive → 0.72 claims/run.

### 2.2 Was the claim layer omitted deliberately? — YES, structurally

- `PROMPted_AGENT` in `src/arena/ablation.py` (worktree) sets every cognitive
  component `enabled=False`, `baseline_type="llm_only"`. It is defined to be
  "no explicit cognitive machinery". This mirrors the intent in
  `rbs_v4_final_report.md §26` (terminal handoff): same model, same tools,
  same Broker, matched budgets — **no scaffolding**.
- The **prompt** (`evaluations/campaign/PROMPTED_PROMPT_FREEZE.json`, frozen by
  SENTINEL directive 4) instructs the model: "Decide the next single action.
  Respond ONLY with the envelope JSON object" — the envelope has 3 keys
  (claim/category/confidence) whose `claim` must be an *action* string
  (`action_type/target/capability/method`). **There is no final-verdict channel
  in the frozen prompt.** The only thing this arm is asked to emit throughout
  the run is the next action envelope.
- So the failure mode observed — "found the port in evidence, never appears in
  final claims" — is **the intended scope of the arm**: prompted action-loop,
  no formal claim layer. The 0/300 is not the LLM failing; it is the LLM's
  final-claim channel not existing by design.

### 2.3 NO_WORLD_MODEL cross-check corroborates intent

`NoWorldModelConclusionAdapter` is a SINGLE-removal ablation: it keeps
`_hypothesis_to_claims` (calls it) and only drops world-model paths. NWM
produced 10.4 claims/run via the same evidence + hypothesis machinery
(traces show hypothesis ops). FULL → 42, NWM → 10.4, SCRIPTED → 1.3,
PROMPTED → 0.72. The claims gradient tracks the deliberate, configurable
removal order of cognitive components — not the presence of a broken adapter.
The two arms are *by design* different in scope:
- NWM = "remove only the world model";
- PROMPTED = "remove everything except the prompt+action loop".

### 2.4 Instrumentation defects found (do not change the mechanism, must be disclosed)

| # | Defect | Evidence | Impact |
|---|--------|----------|--------|
| D1-B-1 | `get_adapter` registry has no `PROMPTED_AGENT` → falls through to `FullConclusionAdapter`, and every run_conclusion is stamped `architecture_id: "FULL_RAPHAEL"` | `conclusion_adapters.py:1152`; `run_conclusion.json` for `abl_PROMPTED_AGENT_known-observable_s0000_holdout` | Provenance contamination: PROMPTED runs' conclusion artifact claims to have been built by the FULL architecture. Cosmetic for the numerical finding; a real defect for auditability. |
| D1-B-2 | The terminal instrument (`run_rbs_v4_holdout_frozen.py`) and the `ablation.py` PROMPTED block are **uncommitted worktree state**; git `HEAD`/`74e52edd` do not contain them. The "frozen instrument" claim (header comment, `instrument_tag=terminal-holdout-frozen`) is not enforced at the git boundary the way other campaign stages claim to be. | `git status --porcelain`: `M src/arena/ablation.py`, `?? scripts/run_rbs_v4_holdout_frozen.py`; `git show 74e52edd:...` returns false for PROMPTED. | The 1,200-row artifact remains auditable from the JSONL + run dirs, but the instrument byte-state at collection time is not pinned to any commit. Recommend pinning the exact worktree state (stash commit) into the reproducibility manifest. |
| D1-B-3 | PROMPTED's single claim (service_type=http on known-observable s0000) came from the Full adapter's `_evidence_to_claims` regex channel, not from LLM text. Consistent across arms. | claims inventory. | Informational. |

### 2.5 Why the D1 "LLMOnly" attribution was wrong and what changes

D1 reported the LLMOnly adapter isn't calling `_semantic_inference_to_claims`.
Technically true, but **irrelevant**: PROMPTED never ran through LLMOnly; it
ran through `FullConclusionAdapter` with zero populated cognitive managers.
The reachability conclusion survives (the semantic-claim channel is gated on
the hypothesis manager, which this arm disables by configuration), but the
mechanism is "ablated brain + registry fallback", not "missing adapter call".

**Neither reading supports (a).**

---

## 3. SENTINEL ruling requested

***Verdict: `(b) intended ablation` — with disclosed instrumentation defects.***

Recommended text for D5 (subject to SENTINEL edit):

> PROMPTED_AGENT is a purposive, formally no-scaffold negative control
> (hypothesis, world model, falsification, planner, defeater, student all
> disabled; prompt frozen to emit only next-action envelopes). Its 0% pass is
> the designed absence of the claim-formalization layer, NOT evidence that a
> strong LLM cannot reason. The evaluation therefore demonstrates:
> **Raphael's world-model + hypothesis + claim-formalization layer is what the
> chosen evaluator rewards**, not that the underlying LLM reasons better when
> scaffolded. FULL-vs-PROMPTED deltas are real measurements of the
> architecture's claim-layer, not of raw reasoning. The three defects in §2.4
> must be recorded as disclosed instrumentation caveats; none changes the
> classification.

(The alternative interpretation — 'arm INVALID, rerun with a claim-emitting
prompt' — is available if SENTINEL prefers a claim-layer-active rather than
claim-layer-absent counterfactual. This report recommends **against** that
count for the current bench: the frozen prompt was SENTINEL-authorized, the
ablation was deliberate, and re-running with a different prompt would test a
different ablation.)

---

## 4. What D1's audit document needs

- Amend §1–4 of PROMPTED_AGENT_ANOMALY_AUDIT.md: replace 'LLMOnly adapter'
  attribution with 'FullConclusionAdapter via registry fallback over ablation-empty
  brain; semantic-path gated on hypothesis manager which this arm disables'.
- Add §2.4 defects D1-B-1..3.
- Result: an ablation-scoped, not harness-scoped, interpretation. The anomaly
  is now preserved as a **result**, not a **defect to repair** (except the
  provenance stamping and unpinned instrument bytecode, which are repairs in
  the instrumentation layer, not in the cognitive core — no `src/` core
  changes required).

---

## 5. Files changed this session (audit-only, no core edits)

- `PROMPTED_AGENT_ANOMALY_AUDIT.md` (existing; needs § mechanism correction per §4)
- New analysis scripts under `evaluations/campaign/_d1b_*.py` (throwaway only)
- No `src/` core edits.

---

**Ready for D2 (sensitivity table) per SENTINEL: D2 independent of D1-B.**