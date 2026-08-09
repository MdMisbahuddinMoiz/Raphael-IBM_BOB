# SENTINEL REPORT — D1-C (D1-C-1/2/3)

**Status:** COMPLETE — D5 BLOCKED pending ruling
**Date (UTC):** 2026-08-08
**Author:** RBS-v1 EVALUATION-SURGEON (Raphael-Forge v4)

---

## D1-C-1: Does a STOP-time / final-verdict prompt exist in the llm_only path?

**Answer: NO.**

The `_run_llm_only` method (`src/arena/ablation_runner.py:2774–3000`) runs a **single 5-iteration loop**:

```python
while iteration < max_iterations and self.metrics.actions_dispatched < ACTION_CAP:
    iteration += 1
    context = self._build_prompted_context(view, all_ev, transcript)
    result = self._llm_service.run_inference(observation_text=context, ...)
    parsed = self._parse_prompted_action(result.claim)
    # broker dispatch + execute + ingest observations
    ...
if iteration >= max_iterations:
    decision_outcome = "STOP_OBJECTIVE_REACHED"
```

**Critical findings:**

1. **Only prompt ever used:** `_build_prompted_context` (`:2735–2774`) builds the **same** instruction on every turn:
   ```
   Decide the next single action. Respond ONLY with the envelope JSON object:
   {"claim": "<compact JSON action string>", "category": "state_description",
    "confidence": <0..1>}.
   The "claim" value must itself be a JSON object string with keys:
   action_type, target, capability, method.
   ```

2. **NO separate STOP-time / final-verdict prompt** exists anywhere in the llm_only path. No "report your findings", "summarize what you found", or any conclusion-eliciting prompt exists in the source.

3. `decision_outcome = "STOP_OBJECTIVE_REACHED"` is set by a **hardcoded generic default** at line 2999: `if iteration >= max_iterations: decision_outcome = "STOP_OBJECTIVE_REACHED"`. This fires when the iteration budget (5) is exhausted — it is a **loop-exhaustion signal, not a model belief of success**.

4. The JSONL rows carry `decision_outcome=STOP_OBJECTIVE_REACHED` for **300/300 PROMPTED rows** (and identically 300/300 for all arms), confirming this is a generic terminal-state default, not a signal the model "thought it was done."

**Conclusion D1-C-1:** The PROMPTED_AGENT arm is **structurally incapable of emitting a final conclusion** — the prompt never asks for one, the loop never asks for one, and the only output channel is the next-action envelope. The 0/300 pass on checks that require a final claim (CVE identification, port open, version, patched-status, vulnerable-host) is a **structural impossibility**, not a reasoning failure.

---

## D1-C-2: TERMINAL_VALIDATION_FREEZE.json file list — are ablation.py / run_rbs_v4_holdout_frozen.py covered?

**Answer: PARTIAL — runner is NOT covered; ablation.py is covered BUT was frozen as uncommitted worktree state.**

The freeze list contains exactly **9 files**:

| file | frozen hash | current hash | PROMPTED in git history? |
|------|-------------|--------------|--------------------------|
| src/arena/templates/families.py | MATCH | MATCH | N/A |
| src/arena/templates/base.py | MATCH | MATCH | N/A |
| src/arena/templates/__init__.py | MATCH | MATCH | N/A |
| src/arena/conclusion_evaluator.py | MATCH | MATCH | N/A |
| src/arena/conclusion_adapters.py | MATCH | MATCH | N/A |
| src/arena/runner.py | MATCH | MATCH | N/A |
| src/arena/environment.py | MATCH | MATCH | N/A |
| src/arena/d6_manifest.py | MATCH | MATCH | N/A |
| **src/arena/ablation.py** | **MATCH** | **MATCH** | **NO** (3 history blobs, all `has_PROMPTED=False`) |
| **scripts/run_rbs_v4_holdout_frozen.py** | **NOT IN LIST** | UNTRACKED (`??`) | N/A |

**Critical observations:**

1. **Runner excluded:** `scripts/run_rbs_v4_holdout_frozen.py` (the actual campaign loop that iterates families/arms/seeds, constructs the AblationRunner, calls `runner.save()`, writes the JSONL rows) is **absent** from the 9-file freeze. The integrity gate's "9/9 PASS" never pinned the runner's bytecode — the script is untracked (`??` in `git status`), exists only as worktree state, and its SHA was never frozen.

2. **ablation.py covered BUT frozen as uncommitted state:** The `ablation.py` hash in the freeze (`5eb4a853...`) matches the **current worktree** file — which contains the PROMPTED_AGENT config. **No committed blob in git history contains PROMPTED_AGENT** (3 historical blobs checked: all `has_PROMPTED=False`). The freeze captured a worktree snapshot containing a config that has never been committed to git. The "frozen instrument" claim is a worktree snapshot, not a commit-anchored seal.

**Implication:** The integrity gate's "9/9 PASS" is accurate for the 9 files listed, but **does not cover the runner** and **pins ablation.py in a state that never existed in version history**. This is not a minor disclosure — it means the "frozen instrument" claim is unverified at the code boundary that actually runs the campaign.

---

## D1-C-3: Actual freeze directive text (not "SENTINEL-authorized, directive 4" by fiat)

The PROMPTED_PROMPT_FREEZE.json cites: `"authorizer": "SENTINEL (REPAIR-DEV-01 adjudication, directive 4: prompt freeze before Validation)"`.

The **actual directive text** is in AMENDMENT_LEDGER entry **FREEZE-01** (2026-08-07T05:40:00Z):

> **SENTINEL freeze directive: the PROMPTED_AGENT prompt must be frozen verbatim (static instruction block from _build_prompted_context, lines 2725–2734) so that Validation/Holdout measure the frozen v2.1.1 contract. Artifact: evaluations/campaign/PROMPTED_PROMPT_FREEZE.json with instruction block SHA-256 4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a (380 bytes). Scope: only interface-contract corrections allowed; NO optimization from T8–T12 failures or from Validation data.**

The phrase "directive 4" in the prompt-freeze artifact refers to one of the numbered freeze directives in this adjudication — not a separate document. The actual authoritative text is the `reason` field above.

---

## D1-C SYNTHESIS

| Question | Finding |
|----------|---------|
| STOP-time prompt? | **None.** Only mid-loop action-envelope prompts. `STOP_OBJECTIVE_REACHED` is a hardcoded loop-exhaustion default. |
| Freeze coverage? | **Partial.** Runner script unpinned; ablation.py pinned but as uncommitted worktree state (PROMPTED_AGENT never committed). |
| Freeze directive? | **FREEZE-01 entry verbatim** (above). "Directive 4" was an internal reference, not a standalone document. |

---

## IMPLICATION FOR D5

Per SENTINEL's guidance:

> "If D1-C confirms no verdict channel exists, the honest write-up isn't 'arm invalid as instrument, claim-layer demonstrated' — it's closer to 'this comparison cannot support the central thesis as designed; report FULL/NWM/SCRIPTED numbers on their own merits, and either redesign PROMPTED with a real verdict channel and rerun, or drop the FULL-vs-PROMPTED claim from the terminal report entirely.'"

**D1-C confirms: no verdict channel exists.** The PROMPTED_AGENT arm as frozen **cannot** pass the evaluator's detection checks because the prompt architecture never elicits a conclusion.

**Recommended D5 framing (pending SENTINEL edit):**

> The terminal PROMPTED_AGENT comparison, as frozen, does not test "strong prompting vs explicit architecture" — it tests "an action-loop with no verdict channel vs an architecture with a claim-formalization layer." The 0/300 pass is a structural impossibility of the arm's design (frozen prompt only elicits next-action envelopes; no STOP-time prompt; adapter fallback stamps runs as FULL_RAPHAEL but runs with zero populated cognitive managers). This comparison **cannot support the central thesis**. The FULL/NWM/SCRIPTED numbers stand on their own; the FULL-vs-PROMPTED delta is a claim-layer measurement, not a reasoning-quality measurement. Instrumentation defects (unpinned runner, unpinned ablation.py, mislabeled conclusions) are disclosed. **Recommendation:** either (a) redesign PROMPTED with a frozen final-verdict prompt and rerun, or (b) exclude the FULL-vs-PROMPTED claim from the terminal report and present the no-scaffold arm as a negative control demonstrating what the evaluator buys (claim layer).

---

D2 (sensitivity table) proceeds independently. D5 remains blocked pending SENTINEL final ruling on the framing above.