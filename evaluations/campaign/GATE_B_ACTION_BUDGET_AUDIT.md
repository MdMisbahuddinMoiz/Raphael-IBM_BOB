# SENTINEL GATE B — ACTION-BUDGET SEMANTIC AUDIT REPORT

**Date:** 2026-08-06
**Status:** AUDIT COMPLETE — NO CODE CHANGES MADE
**Verdict:** **PREREGISTRATION_AMENDMENT_REQUIRED**

---

## A. EXECUTION-FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     FULL_RAPHAEL (_run_raphael)                         │
├─────────────────────────────────────────────────────────────────────────┤
│  while iteration < ITERATION_BUDGET (5) AND actions_started < ACTION_BUDGET (20) │
│    │                                                                    │
│    ├─► Generate candidates (max 15: 10 base + up to 5 falsification)   │
│    │    actions_proposed += len(candidates)                            │
│    │                                                                    │
│    ├─► Select ONE candidate (planner/fallback)                         │
│    │                                                                    │
│    ├─► Broker dispatch: runner.propose_action()                        │
│    │    broker_invocation_count += 1                                   │
│    │                                                                    │
│    ├─► IF denied:                                                      │
│    │    actions_denied += 1                                            │
│    │    continue  ──► next iteration (consumes iteration, NOT action)  │
│    │                                                                    │
│    └─► IF allowed:                                                     │
│         actions_authorized += 1                                        │
│         actions_started += 1         ◄── EXACTLY ONCE per execution   │
│         Execute tool: env.handle_action()                              │
│         Ingest observations → EvidenceGraph                            │
│         (NO second actions_started increment)                          │
│                                                                         │
│  Loop exits when: iteration >= 5 OR actions_started >= 20             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     PROMPTED_AGENT / LLM_ONLY (_run_llm_only)           │
├─────────────────────────────────────────────────────────────────────────┤
│  while iteration < ITERATION_BUDGET (5) AND actions_started < ACTION_BUDGET (20) │
│    │                                                                    │
│    ├─► LLM call → response                                             │
│    ├─► Generate candidates (max 10 base, no falsification)             │
│    │                                                                    │
│    ├─► Select ONE candidate (first valid)                              │
│    │                                                                    │
│    ├─► Broker dispatch: runner.propose_action()                        │
│    │                                                                    │
│    ├─► IF denied:                                                      │
│    │    actions_denied += 1                                            │
│    │    continue ──► next iteration (consumes iteration, NOT action)   │
│    │                                                                    │
│    └─► IF allowed:                                                     │
│         actions_started += 1      ◄── FIRST INCREMENT (line 2764)     │
│         actions_authorized += 1                                        │
│         Execute tool: env.handle_action()                              │
│         Ingest observations                                            │
│         actions_succeeded += 1                                         │
│         actions_started += 1      ◄── SECOND INCREMENT (line 2785) ✗ BUG │
│         actions_authorized += 1                                        │
│                                                                         │
│  Loop exits when: iteration >= 5 OR actions_started >= 20             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     SCRIPTED_BASELINE (_run_scripted)                   │
├─────────────────────────────────────────────────────────────────────────┤
│  while iteration < ITERATION_BUDGET (5) AND actions_started < ACTION_BUDGET (20) │
│    │                                                                    │
│    ├─► Generate candidates (max 10, deterministic round-robin)         │
│    │                                                                    │
│    ├─► Select next untried candidate (round-robin)                     │
│    │                                                                    │
│    ├─► Broker dispatch: runner.propose_action()                        │
│    │                                                                    │
│    ├─► IF denied:                                                      │
│    │    NO actions_denied increment!                                   │
│    │    continue ──► next iteration (consumes iteration, NOT action)   │
│    │                                                                    │
│    └─► IF allowed:                                                     │
│         actions_authorized += 1                                        │
│         actions_started += 1      ◄── FIRST INCREMENT (line 2908)     │
│         Execute tool: env.handle_action()                              │
│         Ingest observations                                            │
│         actions_succeeded += 1                                         │
│         actions_started += 1      ◄── SECOND INCREMENT (line 2929) ✗ BUG │
│         actions_authorized += 1                                        │
│                                                                         │
│  Loop exits when: iteration >= 5 OR actions_started >= 20             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     RAW_TOOL_AGENT                                      │
├─────────────────────────────────────────────────────────────────────────┤
│  NOT IMPLEMENTED in codebase.                                          │
│  Mentioned in rbs_v4_final_report §Q7 as a terminal arm:              │
│  "Arms: FULL_RAPHAEL, PROMPTED_AGENT, RAW_TOOL_AGENT, SCRIPTED_BASELINE" │
│  No code path exists. Would need separate implementation.              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## B. PER-PATH TRACE TABLE (DETERMINISTIC DEV-SAFE EPISODE)

Assumptions for trace: T1_NEGATIVE_CONTROL scenario, seed=42, FULL_RAPHAEL config,
all broker requests ALLOWED (no denials), 5 iterations max.

| Iteration | LLM Calls | Candidates Generated | Planner Decisions | Broker Dispatches | Broker Denials | Broker Approvals | Tool Executions | actions_started |
|-----------|-----------|----------------------|-------------------|-------------------|----------------|------------------|-----------------|-----------------|
| **FULL_RAPHAEL** (ITERATION_BUDGET=5, max_actions=20) |
| 1 | 1 (semantic inference) | 10 | 1 | 1 | 0 | 1 | 1 | 1 |
| 2 | 1 | 9 | 1 | 1 | 0 | 1 | 1 | 2 |
| 3 | 1 | 8 | 1 | 1 | 0 | 1 | 1 | 3 |
| 4 | 1 | 7 | 1 | 1 | 0 | 1 | 1 | 4 |
| 5 | 1 | 6 | 1 | 1 | 0 | 1 | 1 | 5 |
| **TOTAL** | **5** | **40** | **5** | **5** | **0** | **5** | **5** | **5** |

| Iteration | LLM Calls | Candidates Generated | Planner Decisions | Broker Dispatches | Broker Denials | Broker Approvals | Tool Executions | actions_started |
|-----------|-----------|----------------------|-------------------|-------------------|----------------|------------------|-----------------|-----------------|
| **PROMPTED_AGENT / LLM_ONLY** (ITERATION_BUDGET=5, max_actions=20) |
| 1 | 1 (propose action) | 10 | 0 (no planner) | 1 | 0 | 1 | 1 | **2** (BUG: double inc) |
| 2 | 1 | 9 | 0 | 1 | 0 | 1 | 1 | **4** |
| 3 | 1 | 8 | 0 | 1 | 0 | 1 | 1 | **6** |
| 4 | 1 | 7 | 0 | 1 | 0 | 1 | 1 | **8** |
| 5 | 1 | 6 | 0 | 1 | 0 | 1 | 1 | **10** |
| **TOTAL** | **5** | **40** | **0** | **5** | **0** | **5** | **5** | **10** (BUG: 2× real) |

| Iteration | LLM Calls | Candidates Generated | Planner Decisions | Broker Dispatches | Broker Denials | Broker Approvals | Tool Executions | actions_started |
|-----------|-----------|----------------------|-------------------|-------------------|----------------|------------------|-----------------|-----------------|
| **SCRIPTED_BASELINE** (ITERATION_BUDGET=5, max_actions=20) |
| 1 | 0 | 10 | 0 (no planner) | 1 | 0 | 1 | 1 | **2** (BUG: double inc) |
| 2 | 0 | 9 | 0 | 1 | 0 | 1 | 1 | **4** |
| 3 | 0 | 8 | 0 | 1 | 0 | 1 | 1 | **6** |
| 4 | 0 | 7 | 0 | 1 | 0 | 1 | 1 | **8** |
| 5 | 0 | 6 | 0 | 1 | 0 | 1 | 1 | **10** |
| **TOTAL** | **0** | **40** | **0** | **5** | **0** | **5** | **5** | **10** (BUG: 2× real) |

**With denials** (e.g., 2 denials, then approval on 3rd attempt in same iteration - but current code uses `continue` so denials consume full iterations):

| Scenario | FULL_RAPHAEL | PROMPTED_AGENT | SCRIPTED_BASELINE |
|----------|--------------|----------------|-------------------|
| 2 denials, then approval (3 iterations consumed) | iterations=3, actions=1 | iterations=3, actions=2 (bug) | iterations=3, actions=2 (bug) |
| 5 denials across 5 iterations | iterations=5, actions=0 | iterations=5, actions=0 | iterations=5, actions=0 (no actions_denied inc!) |

---

## C. EXACT LOCATION WHERE `actions_started` INCREMENTS

| Path | File | Line | Context |
|------|------|------|---------|
| FULL_RAPHAEL | `src/arena/ablation_runner.py` | **1479** | After broker allows, before `env.handle_action()` |
| PROMPTED_AGENT / LLM_ONLY | `src/arena/ablation_runner.py` | **2764** | After broker allows, before `env.handle_action()` |
| PROMPTED_AGENT / LLM_ONLY | `src/arena/ablation_runner.py` | **2785** | **DUPLICATE** - after `env.handle_action()` ✗ BUG |
| SCRIPTED_BASELINE | `src/arena/ablation_runner.py` | **2908** | After broker allows, before `env.handle_action()` |
| SCRIPTED_BASELINE | `src/arena/ablation_runner.py` | **2929** | **DUPLICATE** - after `env.handle_action()` ✗ BUG |

**FULL_RAPHAEL has exactly ONE increment per executed action** (correct per SENTINEL definition).

**PROMPTED_AGENT and SCRIPTED_BASELINE have DOUBLE increments** - they increment once on authorization and again after execution, doubling the counter.

---

## D. WHETHER DENIED BROKER REQUESTS INCREMENT `actions_started`

| Path | Denied Request → `actions_started`? | `actions_denied` Increments? |
|------|--------------------------------------|-------------------------------|
| **FULL_RAPHAEL** | **NO** (line 1472 `continue` skips increment) | **YES** (line 1443) |
| **PROMPTED_AGENT / LLM_ONLY** | **NO** (line 2760 `continue`) | **YES** (line 2746) |
| **SCRIPTED_BASELINE** | **NO** (line 2904 `continue`) | **NO** (line 2889-2904 has NO `actions_denied` increment!) |

**Critical finding:** SCRIPTED_BASELINE does NOT increment `actions_denied` when broker denies. This breaks telemetry for that path.

---

## E. MAXIMUM POSSIBLE BROKER DISPATCHES UNDER CURRENT FULL_RAPHAEL EXECUTION

Constraints:
- `ITERATION_BUDGET = 5` (from manifest, enforced by `iteration < max_iterations`)
- Each iteration selects ONE candidate and dispatches ONE broker request
- Denial consumes the iteration (`continue` → next iteration)
- Approval consumes the iteration AND increments `actions_started`

**Maximum broker dispatches = ITERATION_BUDGET = 5**

This is because the while loop condition is `iteration < max_iterations`, and iteration increments once per loop regardless of broker decision. There is no inner loop to retry multiple candidates per iteration - the `continue` on denial goes to the next iteration.

**Maximum possible successful actions = 5** (one per iteration, all approved)

**Maximum possible broker dispatches (if all denied) = 5** (one per iteration, all denied)

The `ACTION_BUDGET = 20` is never binding under current FULL_RAPHAEL execution because the iteration limit (5) is reached first.

---

## F. MAXIMUM POSSIBLE BROKER DISPATCHES UNDER PROMPTED_AGENT

Same loop structure as FULL_RAPHAEL (same `while iteration < max_iterations...`), so:

**Maximum broker dispatches = ITERATION_BUDGET = 5**

However, due to the double-increment bug on `actions_started`:
- After 5 successful actions, `actions_started` = 10 (not 5)
- Still below `ACTION_BUDGET = 20`, so iteration limit still binds first
- If the bug were fixed (single increment), `actions_started` would be 5 after 5 actions

**Maximum broker dispatches = 5** (same as FULL_RAPHAEL, iteration-limited)

---

## G. WHETHER ACTION_BUDGET IS ACTUALLY ENFORCED OR MERELY TELEMETRY

**Currently: TELEMETRY ONLY — not enforced as a binding constraint.**

Evidence:
1. Loop condition: `while iteration < max_iterations and self.metrics.actions_started < max_actions`
2. `max_iterations = ITERATION_BUDGET = 5`
3. `max_actions = ACTION_BUDGET = 20`
4. FULL_RAPHAEL: max 5 successful actions → `actions_started` max = 5 << 20
5. LLM_ONLY (buggy): max 5 successful actions → `actions_started` max = 10 (bug) << 20
6. SCRIPTED_BASELINE (buggy): max 5 successful actions → `actions_started` max = 10 << 20

**The iteration budget (5) is the binding constraint. The action budget (20) is never reached.**

The `ACTION_BUDGET = 20` in the manifest and the budget guard in the code are effectively **decorative telemetry** — they are never the binding constraint under current execution parameters.

---

## H. RECOMMENDATION FOR A COMMON TERMINAL ACTION CAP

### Semantic Analysis

**SENTINEL canonical action definition:** ACTION = one action request dispatched to CapabilityBroker for authorization.

This means:
- Every `runner.propose_action()` call = 1 action
- Includes both approved AND denied requests
- Candidate generation, planner decisions, LLM calls, tool executions = 0 actions

### Current Implementation vs. Definition

| Metric | SENTINEL Definition | FULL_RAPHAEL Current | PROMPTED_AGENT Current | SCRIPTED_BASELINE Current |
|--------|---------------------|----------------------|------------------------|---------------------------|
| Broker dispatch (allow) | 1 action | `actions_started += 1` ✓ | `actions_started += 2` ✗ (2×) | `actions_started += 2` ✗ (2×) |
| Broker dispatch (deny) | 1 action | NO increment ✗ | NO increment ✗ | NO increment + no `actions_denied` ✗✗ |
| Candidate generation | 0 | N/A | N/A | N/A |
| Planner decision | 0 | N/A | N/A | N/A |
| LLM call | 0 | N/A | N/A | N/A |
| Tool execution | 0 | N/A | N/A | N/A |

### Key Defects to Fix (Before Terminal Experiment)

1. **Double-increment bug** in PROMPTED_AGENT/LLM_ONLY and SCRIPTED_BASELINE: `actions_started` increments twice per successful action.

2. **Denial not counted as action** in any path: denied broker requests should increment the action counter per SENTINEL definition, but currently don't increment `actions_started` anywhere.

3. **SCRIPTED_BASELINE missing `actions_denied` increment**: denials are completely invisible in telemetry.

4. **Budget guard uses wrong counter**: the `actions_started < max_actions` guard uses a counter that doesn't match the SENTINEL action definition.

### Maximum Dispatches Under Fixed Semantics

If we fix the code so that `actions_dispatched` (new metric) increments on EVERY broker dispatch (allow + deny):

| Path | Max Iterations | Max Candidates/Iteration | Max Broker Dispatches (all denied) |
|------|----------------|---------------------------|-------------------------------------|
| FULL_RAPHAEL | 5 | 1 | 5 |
| PROMPTED_AGENT | 5 | 1 | 5 |
| SCRIPTED_BASELINE | 5 | 1 | 5 |

With max 1 candidate selected per iteration, max broker dispatches = `ITERATION_BUDGET = 5`.

But wait — what if we allowed retrying next candidate after denial within the SAME iteration? Current code uses `continue` which consumes the iteration. If we changed to retry logic:

| Path | Max Candidates/Iteration | Max Broker Dispatches (all denied) |
|------|--------------------------|-------------------------------------|
| FULL_RAPHAEL | 10-15 | 5 × 15 = 75 |
| PROMPTED_AGENT | 10 | 5 × 10 = 50 |
| SCRIPTED_BASELINE | 10 | 5 × 10 = 50 |

But the current code does NOT do this - it uses `continue` which consumes the iteration.

### Recommendation: Common Terminal Action Cap

**Based on semantic parity and architecture-neutral resource matching:**

The terminal experiment specifies: "same tools, same CapabilityBroker, matched inference-token budget, **matched action budget**"

**Current manifest constants:**
- `ITERATION_BUDGET = 5` (hard loop limit)
- `ACTION_BUDGET = 20` (telemetry only, never binds)
- `max_candidates_per_generation = 15` (falsification cap)

**Recommendation: Define the terminal action cap as `ACTION_CAP = 5` actions (broker dispatches), matching the iteration budget.**

**Rationale:**
1. **Architecture-neutral**: All three paths (FULL_RAPHAEL, PROMPTED_AGENT, SCRIPTED_BASELINE) have identical loop structure — max 5 iterations, 1 broker dispatch per iteration.
2. **Semantic parity**: Under SENTINEL's action definition (broker dispatch = 1 action), all paths have identical maximum possible action count = 5.
3. **Resource matching**: The action cap matches the iteration budget, which is the actual binding constraint in the current implementation.
4. **Manifest alignment**: `ITERATION_BUDGET = 5` already exists as the effective cap. The `ACTION_BUDGET = 20` should be either:
   - Updated to 5 to match reality, OR
   - The iteration budget should be increased if 20 actions are desired (requiring architectural change to allow multiple broker dispatches per iteration)

**Proposed Terminal Experiment Parameters:**

| Parameter | Value | Justification |
|-----------|-------|---------------|
| **Action Cap** | 5 broker dispatches per episode | Matches ITERATION_BUDGET; architecture-neutral |
| **Iteration Budget** | 5 | Frozen manifest constant |
| **Max Candidates/Generation** | 15 (falsification) / 10 (base) | Frozen manifest |
| **Action Definition** | One broker dispatch (allow + deny) | SENTINEL canonical |
| **Telemetry** | `actions_dispatched` = allow + deny | New metric matching definition |
| **Budget Guard** | `actions_dispatched < ACTION_CAP` | Enforces the actual cap |

**Implementation Required Before Terminal Experiment:**
1. Fix double-increment bug in LLM_ONLY and SCRIPTED_BASELINE
2. Add `actions_dispatched` metric that increments on EVERY `propose_action()` call
3. Fix SCRIPTED_BASELINE `actions_denied` increment
4. Change budget guard to use `actions_dispatched < ACTION_CAP`
5. Set `ACTION_CAP = 5` (or update `ITERATION_BUDGET` if more actions desired)

---

## GATE B VERDICT: **PREREGISTRATION_AMENDMENT_REQUIRED**

### Reasons:

1. **Semantic mismatch**: The existing `actions_started` metric does NOT implement SENTINEL's canonical action definition (broker dispatch = 1 action). It counts only successful executions, not broker dispatches.

2. **Double-increment bug**: PROMPTED_AGENT and SCRIPTED_BASELINE paths double-count successful actions, making their telemetry incomparable to FULL_RAPHAEL.

3. **Denial invisibility**: Denied broker requests are not counted as actions anywhere (and SCRIPTED_BASELINE doesn't even increment `actions_denied`).

4. **Budget constant mismatch**: The manifest declares `ACTION_BUDGET = 20` but the code's binding constraint is `ITERATION_BUDGET = 5`. The action budget is never enforced.

5. **Terminal experiment cannot proceed** with "matched action budget" until:
   - The action definition is implemented consistently across all paths
   - The action cap is defined and enforced consistently
   - The preregistration's action budget is updated to match the agreed cap

---

## REQUIRED BEFORE TERMINAL EXPERIMENT AUTHORIZATION

- [ ] Fix double-increment bug in `src/arena/ablation_runner.py` (lines 2764/2785, 2908/2929)
- [ ] Add `actions_dispatched` metric incrementing on EVERY `propose_action()` call
- [ ] Fix SCRIPTED_BASELINE `actions_denied` increment
- [ ] Change budget guard to use `actions_dispatched < ACTION_CAP`
- [ ] Define `ACTION_CAP` in manifest (recommendation: 5, matching `ITERATION_BUDGET`)
- [ ] Update preregistration manifest (`rbs_v4_benchmark_frozen-F.json`) with agreed `ACTION_CAP`
- [ ] SENTINEL approval of preregistration amendment (model + action cap changes)

**Gate B Status: PREREGISTRATION_AMENDMENT_REQUIRED**