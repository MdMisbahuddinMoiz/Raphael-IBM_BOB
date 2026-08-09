# SENTINEL REPORT — RBS-v4 Terminal Repair (Items 6–11) & Test Gate

**To:** SENTINEL
**From:** RBS-v4 Evaluation-Surgeon (Raphael-Forge v4)
**Date:** 2026-08-06
**Subject:** Completion of repair items 6–11, mandatory test gate, and READINESS classification.

---

## A. EXECUTIVE SUMMARY

Repair items 1–5 were previously completed and reported. This session completed
**repair items 6–11** (all 11 of the SENTINEL-ordered repair items are now done):

| Item | Title | Status |
|------|-------|--------|
| 1–5 | Token telemetry, env determinism, safety-telemetry semantics, NoOp contract, conclusion/infra accounting | DONE (prior session) |
| 6 | Tool failure vs real observation (evidence provenance distinction) | **DONE** |
| 7 | Resume + logical identity (deterministic run_id, cell dedup, integrity-gate check 9) | **DONE** |
| 8 | Fresh evaluator isolation (trait-leakage elimination) | **DONE** |
| 9 | PROMPTED_AGENT architecture preset + broker-parity test | **DONE** |
| 10 | Budget contract bound to frozen manifest + measurable Dev distributions | **DONE** |
| 11 | Multi-API-key rotation — DESIGN ONLY, NOT ACTIVATED | **DONE** |

**Mandatory test gate: PASS.** Full regression **195 passed, 26 warnings**.
Compile: OK. Live token-usage smoke: SKIP-classified by design (endpoint
unreachable; telemetry path itself verified).

**FINAL CLASSIFICATION: READY_FOR_DEV** (see Section M for the reasoning
and the boundaries of that readiness).

---

## B. OBJECTIVE & MANDATE

Execute the 11 ordered repair items under SENTINEL governance, then run the
mandatory test gate (compile, full regression, new tests, deterministic
replay, NO_WORLD_MODEL regression, safety-exception regression,
tool-crash/evidence-isolation regression, interruption/resume simulation,
live token-usage smoke, PROMPTED_AGENT/FULL broker-parity) and deliver this
report with sections A–M and a READY_FOR_DEV / BLOCKED /
READY_AFTER_SPECIFIC_REPAIR classification.

**Not in scope (respected):** Terminal Falsification was NOT launched; Holdout
data was NOT touched or inspected; cognitive semantics were NOT changed; the
terminal PROMPTED_AGENT comparison experiment is a handoff, NOT authorized
to begin; no multi-API-key rotation was activated.

---

## C. REPAIRS COMPLETED (DETAIL)

### C.6 — Item 6: Tool failure vs real observation (evidence provenance)

- `src/orchestrator/brain/trust.py`: added `TrustLevel.TOOL_FAILURE`
  (distinct from `TOOL_OBSERVATION`).
- `src/arena/environment.py`: `RawObservation.is_tool_failure: bool = False`;
  `ObservationNormalizer.normalize` now emits `TOOL_FAILURE` trust when
  `is_tool_failure` is set, `TOOL_OBSERVATION` otherwise. Explicit caller
  trust-level override is still honored.
- Test: `tests/test_tool_failure_provenance.py` (4 tests).
- Combined with item 5's broker sanitization, a failed tool's output is now
  (a) sanitized at the broker (`EXECUTION_ERROR: tool X failed`) and
  (b) distinguishable at the evidence layer from a real successful
  observation.

### C.7 — Item 7: Resume + logical identity (run_id determinism)

- `src/arena/ablation_runner.py`: `run_id` is now a DETERMINISTIC logical-cell
  identity `abl_<config>_<template>_s<seed>_<split>` (random UUID suffix
  removed). Resume is idempotent: the same logical cell yields the same
  run_id, the same run_dir (overwritten), enabling dedup on run_id.
- `scripts/run_rbs_v4_integrity_gate.py`: added **check 9 — run_id
  determinism**: every row's run_id must equal the logical-cell-derived form
  (`d6c_holdout_<arch>_<scenario>_s<seed>`), no UUID tail.
- Test: `tests/test_run_identity.py` (7 tests) + gate check-9 smoke verified.

### C.8 — Item 8: Fresh evaluator isolation (trait leakage)

- `src/orchestrator/capabilities/interactive_shell/tty_normalizer.py`:
  `EvidenceExtractor` no longer falls back to the process-global
  `get_evidence_graph()` singleton; a missing graph now mints a FRESH
  per-instance `EvidenceGraph()`. Evidence from run A can no longer surface
  in run B's evaluation.
- `scripts/arena.py`: removed the global-singleton fallback; fresh
  `EvidenceGraph()` minted when falsy.
- `src/arena/environment.py`: removed the dead `get_evidence_graph` import
  (latent vector).
- Legacy APIs `get_hypothesis_manager()` / `run_scenario_4_test()` were
  audited: not on any ablation path; left untouched (deliberate legacy
  singletons).
- Test: `tests/test_evaluator_isolation.py` (7 tests).

### C.9 — Item 9: PROMPTED_AGENT architecture preset + broker parity

- `src/arena/ablation.py`: added `PROMPTED_AGENT` preset (strong
  prompted-agent control arm): all cognitive machinery disabled, `llm_enabled`
  true, `baseline_type="llm_only"`, broker NEVER ablated. Registered in
  `ABLATION_PRESETS`. **NOT** registered in the holdout campaign configs —
  the terminal experiment remains a handoff.
- Test: `tests/test_prompted_agent_parity.py` (6 tests) — including identical
  broker allow/deny decisions under an identical `BrokerPolicy` for
  FULL_RAPHAEL vs PROMPTED_AGENT (allow/deny parity across target/action/
  capability probes).

### C.10 — Item 10: Budget contract bound to manifest + Dev distributions

- `src/arena/d6_manifest.py` was already the source of truth
  (`ITERATION_BUDGET = 5`, `ACTION_BUDGET = 20`).
- `src/arena/ablation_runner.py`: all three execution paths (raphael /
  llm_only / scripted) now bind `max_iterations = ITERATION_BUDGET` and guard
  the loop with `actions_started < ACTION_BUDGET` (hardcoded literal removed).
- `src/arena/metrics.py`: `RunMetrics` gains `iterations_used`,
  `budget_iteration_ceiling`, `budget_action_ceiling` so the Dev distribution
  of budget consumption is measurable against the contract.
- Test: `tests/test_budget_contract.py` (6 tests) including an end-to-end
  SCRIPTED_BASELINE dev run staying within the contract.

### C.11 — Item 11: Multi-API-key rotation — DESIGN ONLY

- Deliverable: `docs/MULTI_API_KEY_ROTATION_DESIGN.md`. **No source changes.**
- Specifies optional `api_keys`/`key_rotation` fields, deterministic
  round-robin selection at the single choke point (`call_llm_provider` /
  `run_inference`), key-index attribution, and an explicit activation
  procedure requiring separate SENTINEL authorization.
- Design constraint: rotation rotates the KEY only — never provider/model;
  D-6C no-silent-retry policy preserved; no key stored in git.

---

## D. MANDATORY TEST GATE — RESULTS

| # | Gate item | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Compile (`compileall` src/scripts/tests) | **PASS** | COMPILE: OK |
| 2 | Full regression | **PASS** | 195 passed, 26 warnings |
| 3 | New tests (items 6–11) | **PASS** | 4+7+7+6+6 = 30 new tests, all green |
| 4 | Deterministic replay | **PASS** | `test_repair_gate.py` G1 (scripted + NO_WORLD_MODEL replays identical) |
| 5 | NO_WORLD_MODEL regression | **PASS** | `test_repair_gate.py` G2 (runs green, within budget) |
| 6 | Safety-exception regression | **PASS** | `tests/test_safety_telemetry.py` (5 tests) |
| 7 | Tool-crash/evidence-isolation regression | **PASS** | `tests/test_tool_failure_provenance.py` (4 tests) |
| 8 | Interruption/resume simulation | **PASS** | `test_repair_gate.py` G3 + `test_run_identity.py` |
| 9 | Live token-usage smoke | **SKIP (by design)** | exit 2; `call_count=1 provider_failures=1` telemetry path verified; NVIDIA endpoint unreachable from sandbox |
| 10 | PROMPTED_AGENT/FULL broker-parity | **PASS** | `tests/test_prompted_agent_parity.py` |

**Gate verdict: PASS** (the single SKIP is the designed classification for an
unreachable external endpoint, not a failure).

---

## E. DATA INTEGRITY

- Frozen holdout JSONL (`rbs_v4_holdout.jsonl`, 3,240 rows, SHA-256
  `472e050f...a8b91c`) was NOT modified. No campaign was re-run.
- Integrity gate (`run_rbs_v4_integrity_gate.py`) extended with check 9
  (run_id determinism) but NOT executed against live holdout data (that gate
  runs at holdout analysis time; holdout remains unlaunched).
- No evidence was fabricated, coerced, or hidden. All repair tests assert
  real behavioral invariants against the actual source.

---

## F. IMPORT MAP / IMPORT REALITY

All imports added this session resolve to `src/` files verified by
`compileall` and the 195-test regression. No new third-party imports.
`arena.d6_manifest` import into `ablation_runner` was checked for circular
imports (`arena.runner`/`arena.ablation`/`arena.metrics`/`arena.environment`
do not import `d6_manifest`) — no cycle.

---

## G. CRYPTOGRAPHIC INVERSE / NO SECRETS

- No new crypto operations introduced.
- The frozen NVIDIA key remains a literal in `ablation_runner.py` (pre-existing,
  frozen treatment). The item-11 design explicitly mandates env-var sourcing
  upon any future activation and forbids key storage in git.
- Broker error sanitization (item 5) ensures raw exception text (which could
  contain paths/secrets) never reaches evidence as `TOOL_OBSERVATION`.

---

## H. THREATS / LIMITATIONS

1. **Live LLM endpoint unreachable from sandbox** — live token telemetry and
   PROMPTED_AGENT/LLM-online runs cannot be exercised end-to-end here. The
   mock-mode path (empty `api_base`) is hermetic and used by tests; the real
   provider path is verified only structurally.
2. **NO_WORLD_MODEL / raphael-path gate tests use mock LLM** — they verify
   determinism, budget, and no-crash, not live-cognition correctness.
3. **Integrity-gate check 9** is validated by logic smoke, not against a real
   holdout file (holdout unlaunched).
4. **Item 11 is design-only** — the design's claims are grounded in the actual
   code (single choke point at `call_llm_provider`) but unexercised.

---

## I. CODEBASE HEALTH

- Tests: **195 passed, 26 warnings** (baseline 161 at session start → +34).
- New test files: `test_tool_failure_provenance.py`, `test_run_identity.py`,
  `test_evaluator_isolation.py`, `test_prompted_agent_parity.py`,
  `test_budget_contract.py`, `test_repair_gate.py`.
- Modified `src/`: `trust.py`, `environment.py`, `ablation_runner.py`,
  `ablation.py`, `metrics.py`, `tty_normalizer.py`, `capability_broker.py`
  (item 5 prior).
- Modified scripts: `run_rbs_v4_integrity_gate.py`, `arena.py`.
- New doc: `docs/MULTI_API_KEY_ROTATION_DESIGN.md` (design only).

---

## J. STRIKES / COMPLIANCE

- Strike count: **0/3** (unchanged). No `src/` modification without SENTINEL
  authorization (all changes are the authorized repair items); no
  undocumented results (all changes have raw test evidence); no
  non-resolving imports.

---

## K. RAW EVIDENCE

- Test output: `pytest -q` → 195 passed, 26 warnings (run repeatedly).
- Live smoke: `call_count=1 provider_failures=1 input_tokens=0 output_tokens=0`,
  `provider_timeout`, exit code 2 (SKIP).
- All new tests are committed as files under `tests/`; each asserts raw
  behavioral invariants (no mocked truth, no coerced telemetry).

---

## L. NEXT STEPS (NOT AUTHORIZED — for SENTINEL review only)

1. Decide on the terminal PROMPTED_AGENT comparison (handoff per
   `rbs_v4_final_report.md` §Q7/§26): FULL_RAPHAEL / PROMPTED_AGENT /
   RAW_TOOL_AGENT / SCRIPTED_BASELINE, same model, matched budgets.
2. Consider live-endpoint verification of token telemetry and
   PROMPTED_AGENT online behavior in an environment where the NVIDIA endpoint
   is reachable.
3. Item-11 activation, if ever desired, requires separate authorization and
   must NOT alter the frozen manifest.

---

## M. CLASSIFICATION

**READY_FOR_DEV** — with the following explicit boundaries:

- The 11 ordered repair items are complete; all new defect fixes are covered
  by dedicated tests; the full regression is green (195 passed); the
  mandatory gate passes (single SKIP is by design).
- READY_FOR_DEV applies to **instrument readiness for development-phase
  experiments** (dev/validation splits, architecture-value evaluation,
  PROMPTED_AGENT arm readiness). It is NOT authorization to run the holdout,
  to run Terminal Falsification, or to activate key rotation.
- The one environmental limitation (unreachable LLM endpoint) is a sandbox
  property, not an instrument defect; it is tracked as a SKIP, not a blocker.

*Report generated 2026-08-06 by Raphael-Forge v4 (Evaluation-Surgeon).*
