# RAPHAEL IBM BOB MVP — Submission Checklist (M12)

Status vocabulary: **VERIFIED** (physically executed on the current
tree) · **DOCUMENTED** (written, accuracy tied to a verification
step) · **NOT VERIFIED** (not yet proven) · **BLOCKED** (cannot
proceed). Submission readiness is asserted only where every
submission-critical box below is VERIFIED.

Verified 2026-09-15 on branch `feature/raphael-harness-live-model`,
Python 3.14.4. The final submission SHA is the commit that contains
this file (see the M12 report for the exact hash).

## Repository

- [x] **VERIFIED** — working tree clean (`git status --short` empty
  after verification; fixtures restored by every run).
- [x] **VERIFIED** — final SHA recorded in the M12 report; milestone
  commits present and not rewritten.
- [x] **VERIFIED** — no generated artifacts committed: `runs/*`
  (except tracked `runs/.gitkeep`), `metrics.json`, and `sessions/`
  are git-ignored and absent from `git ls-files`.
- [x] **VERIFIED** — no credentials committed (secret sweep below).

## Functional Verification

- [x] **VERIFIED** — full test suite: **357 tests, 0 failures**
  (21-module explicit unittest command; see `docs/demo-runbook.md` §4).
- [x] **VERIFIED** — deterministic hero (`demos/authkit_hero.py`):
  exit 0, `Gate: COMPLETE`.
- [x] **VERIFIED** — RAPHAEL mode (`--mode raphael`): exit 0,
  `Gate: COMPLETE`.
- [x] **VERIFIED** — baseline mode (`--mode baseline`): exit nonzero
  (1), `Gate: REFUSE`, failed only on `D:independent-behavior-probe`.
- [x] **VERIFIED** — live model hero (`demos/live_authkit_hero.py`,
  DeepSeek V4.1 Flash via OpenCode Go): run
  `20260915T161002_2ad7e0`, `Gate: COMPLETE`, 7/7 conditions.
- [x] **VERIFIED** — metrics: `scripts/audit_runs.py --runs-root runs
  --output metrics.json` → `runs=327 valid=327 invalid=0`.

## Evidence / Auditability

- [x] **VERIFIED** — durable runs: `runs/<run_id>/{evidence.jsonl,
  artifacts/}`, unique per execution, never appended across runs.
- [x] **VERIFIED** — evidence reconstructable: the hero run's 48
  records re-read from disk reconstruct the full chain (requests,
  decisions, results, policy/verifier/falsifier/probe/regression
  evidence, finding lifecycle, gate) without console narration.
- [x] **VERIFIED** — seal verification: `seal.json` written for the
  hero run; `python3 scripts/audit_runs.py --verify-seal
  runs/20260915T161002_2ad7e0` → `seal-ok`, rc 0. Record tampering
  and deletion are detected (head-mismatch / record-count-mismatch).
- [x] **VERIFIED** — artifacts resolve; no missing/malformed evidence
  (`invalid_run_count` = 0).
- [x] **VERIFIED** — verdict comes from the QualityGate record
  (`kind="gate"`, `decision="complete"`), not from process exit.

## Governance Audit

- [x] **VERIFIED** — no direct capability invocation:
  `execute_capability` is imported/called only by `broker.py`
  (plus the package re-export).
- [x] **VERIFIED** — policy mediation intact: every action is
  Runtime → Broker → Policy; DENY does not execute.
- [x] **VERIFIED** — no unauthorized network path: `urllib` appears
  only in the provider adapter (`harness/providers/openai_compat.py`).
- [x] **VERIFIED** — no unauthorized subprocess: `subprocess` appears
  only in the scoped RUN_TEST capability.
- [x] **VERIFIED** — no filesystem bypass: the only agent-path writer
  is `capabilities._write`, reached only via Broker dispatch.
- [x] **VERIFIED** — invalid proposals cannot reach the Broker
  (validated before submission; broker submission count unchanged).
- [x] **VERIFIED** — `DoneSignal` is terminal but cannot cause
  COMPLETE; QualityGate remains the sole COMPLETE authority (only
  construction site is `quality_gate.py:358`).
- [x] **VERIFIED** — falsification intact: the Falsifier challenges
  apparent success (live hero challenge record; M9 refutation tests).

## Model Result (accurately reported)

- [x] **VERIFIED** — DeepSeek V4.1 Flash (OpenCode Go): 5 live
  missions, 4 COMPLETE, 1 REFUSE; 4 reached RUN_TEST/WRITE/verification.
- [x] **VERIFIED** — Nemotron 3.5 Lightning (NVIDIA NIM): 8 live
  missions, inspection-only, 0 COMPLETE.
- [x] **VERIFIED** — live vs deterministic distinction documented
  (`docs/live-model.md`); live replan **not** claimed (deterministic
  integration only).
- [x] **VERIFIED** — replan integration verified deterministically:
  `tests/test_m9_multi_replan.py` (17 tests) covers bad fix → refute →
  Falsifier → Finding REFUTED → Replanner → Plan B → correct fix →
  independent verification → COMPLETE, with parent/child plan linkage.

## Secret Sweep

- [x] **VERIFIED** — no live API key in tracked files, `runs/`
  evidence, `/tmp` helpers, or recent commit diffs.
- [x] **VERIFIED** — pre-existing legacy-substrate files
  (`evaluations/campaign/*`, `forge/*`, `scripts/rbs_v2r_*`,
  `src/arena/manifests/*`, `src/orchestrator/nvidia_provider.py`) had
  committed NVIDIA API-key values; these were **redacted to
  `nvapi-REDACTED` at HEAD** (structure and narrative preserved).
  Test placeholders (`nvapi-test`, `nvapi-live`, `nvapi-stale`,
  `nvapi-your-key-here`) are intentionally left as-is.
- [ ] **DISCLOSED LIMITATION** — the redacted key values remain
  present in **git history** (not the working tree). Removing them
  from history requires a history rewrite, which is out of scope for
  M12; disclose or rotate the affected keys before public release.

## C1A (Phase 2C)

- [x] **VERIFIED** — C1A is a first-class capability; it is never aliased
  to `READ` (identity tests).
- [x] **VERIFIED** — authorization binding covers the full identity; every
  field mutation, replay, and foreign-identity case fails closed.
- [x] **VERIFIED** — canonical scope containment shared by Policy and
  QualityGate Condition E; sibling prefix/traversal/malformed paths fail.
- [x] **VERIFIED** — bounded transport: timeout and late output never
  become success.
- [x] **VERIFIED** — pinned launcher digest mismatch fails closed.
- [x] **VERIFIED** — provider output is untrusted evidence and cannot
  create VERIFIED/REFUTED/COMPLETE.
- [x] **VERIFIED** — inert-provider end-to-end path reaches
  `Gate: COMPLETE` through the real QualityGate.
- [ ] **BLOCKED** — live C1A proof: real T3MP3ST provider absent;
  `scripts/c1a_live_proof.py` reports `BLOCKED`. M1/M2/M5 are **not**
  claimed. See `docs/integration/c1a-release-gate.md`.
- [ ] **DISCLOSED** — test-count discrepancy: this file states 357 tests
  (21-module command) while `README.md` states 209 (a shorter explicit
  module list). The counts reflect different module lists, not
  contradictory results; the authoritative count is the explicit
  `unittest` command actually run. Reconcile the two numbers in a future
  documentation pass.



- [x] **VERIFIED** — `docs/live-model.md` (architecture, provider,
  live results, live-vs-deterministic, limitations).
- [x] **VERIFIED** — `docs/demo-runbook.md`, `docs/PROVENANCE.md`,
  `docs/metrics.md`, `docs/submission-checklist.md` (this file) match
  the implementation; no statistical/generalization overclaims.

## Packaging Readiness

- [x] **VERIFIED now** — everything above on the current tree.
- [ ] **Deferred** — final submission archive (ZIP), transport, and
  judge-portal steps. No archive is created by M12.
