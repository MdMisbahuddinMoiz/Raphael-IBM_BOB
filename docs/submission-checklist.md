# RAPHAEL IBM BOB MVP — Submission Checklist (M12)

Status vocabulary: **VERIFIED** (physically executed on the current
tree) · **DOCUMENTED** (written, accuracy tied to a verification
step) · **NOT VERIFIED** (not yet proven) · **BLOCKED** (cannot
proceed). Submission readiness is asserted only where every
submission-critical box below is VERIFIED.

Verified 2026-09-15 on branch `feature/raphael-harness-live-model`,
Python 3.14.4. Code HEAD at verification time: `5dad890b0` (this file
and `docs/live-model.md` are added in the following commit; the final
submission SHA is that commit — see the M12 report).

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

## Documentation

- [x] **VERIFIED** — `docs/live-model.md` (architecture, provider,
  live results, live-vs-deterministic, limitations).
- [x] **VERIFIED** — `docs/demo-runbook.md`, `docs/PROVENANCE.md`,
  `docs/metrics.md`, `docs/submission-checklist.md` (this file) match
  the implementation; no statistical/generalization overclaims.

## Packaging Readiness

- [x] **VERIFIED now** — everything above on the current tree.
- [ ] **Deferred** — final submission archive (ZIP), transport, and
  judge-portal steps. No archive is created by M12.
