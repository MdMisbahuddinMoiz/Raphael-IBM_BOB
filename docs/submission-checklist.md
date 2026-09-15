# RAPHAEL IBM BOB MVP — Submission Checklist

Status vocabulary: **VERIFIED** (physically executed on the current
tree) · **DOCUMENTED** (written, accuracy tied to a verification
step) · **NOT VERIFIED** (not yet proven) · **BLOCKED** (cannot
proceed). No other status words are used. Submission readiness as a
whole is NOT claimed by this file (see Packaging Readiness).

Verified 2026-09-15 on branch `migration/bob-mvp`, Python 3.14.4.
HEAD must be the M10.5 commit: confirm with `git log --oneline -1`.

## Repository — VERIFIED

- [x] **VERIFIED** — branch is `migration/bob-mvp`
  (`git branch --show-current`).
- [x] **VERIFIED** — tree clean after verification
  (`git status --short` empty; fixtures restored by every run).
- [x] **VERIFIED** — milestone commits present, none rewritten:
  `1039ebf58` M0, `d16333c92` M1, `ac3c177ad` M2, `4b87bf31a` M3,
  `1d1a6ba58` M4, `3a27f20f5` M5, `6d364eb59` M6, `a76efd0ff` M7,
  `a19fcc30c` M8-partial, `7ebcca046` M8-complete, `7498a420c` M9,
  `2c24f88c8` M10.1, `0b3589ed0` M10.2, `a5506a279` M10.3,
  `8709a4777` M10.4 (+ M10.5 commit on top).
- [x] **VERIFIED** — no accidental untracked files (only intended
  `docs/` additions staged per milestone; `git status` inspected).
- [x] **VERIFIED** — no generated artifacts committed: `runs/*`
  (except tracked `runs/.gitkeep`) and `metrics.json` are ignored
  (`git check-ignore` confirms) and absent from `git ls-files`.
- [x] **VERIFIED** — `git diff --check` clean.

## Functional Verification — VERIFIED

- [x] **VERIFIED** — full suite: `Ran 209 tests — OK (0 failed)`
  via the explicit 12-module unittest command
  (`docs/demo-runbook.md` §4). The single fatal-invocation stderr
  line is asserted test behavior, not a failure.
- [x] **VERIFIED** — default hero: exit 0, `Gate: COMPLETE`,
  durable `runs/<run_id>/` (`PYTHONPATH=. python3
  demos/authkit_hero.py`).
- [x] **VERIFIED** — RAPHAEL mode: exit 0, `Gate: COMPLETE`
  (`--mode raphael`; identical to default).
- [x] **VERIFIED** — baseline mode: exit nonzero, `Gate: REFUSE`
  failed only on `D:independent-behavior-probe`
  (`--mode baseline`).
- [x] **VERIFIED** — metrics generation: `scripts/audit_runs.py
  --runs-root runs --output metrics.json` exit 0, all discovered
  runs valid, verdicts from gate records.
- [x] **VERIFIED** — evidence durability: post-process reopen of
  `runs/<run_id>/evidence.jsonl` reconstructs gate + replan chain
  (`tests/test_m10_1_runs.py`, plus manual inspection).
- [x] **VERIFIED** — gate behavior: sole COMPLETE authority; no
  other module constructs `GateVerdict.COMPLETE` (source-asserted
  in M6/M9 tests).
- [x] **VERIFIED** — refusal behavior: exhausted bounded recovery
  → REFUSE (M9 failure path); denied RUN_TEST → REFUSE paths
  (M6 §17 regression tests); baseline → REFUSE.

## Evidence / Auditability — VERIFIED

- [x] **VERIFIED** — durable runs: `runs/<run_id>/{evidence.jsonl,
  artifacts/}`, unique per execution, never appended across runs.
- [x] **VERIFIED** — evidence JSONL: six record kinds, dense
  per-run sequences, validator-enforced (`scripts/audit_runs.py`).
- [x] **VERIFIED** — artifacts resolve inside their run dir.
- [x] **VERIFIED** — provenance: `docs/PROVENANCE.md` (substrate,
  adaptations with file refs, replacements, isolations, zero
  legacy code imports by scoped search).
- [x] **VERIFIED** — benchmark provenance: `producer="benchmark"`
  mode records in every post-M10.3 run; pre-mode runs stay
  `mode="unknown"`, excluded from `by_mode`.
- [x] **VERIFIED** — independent behavior probe: external
  subprocess, separate surface from unit tests, red-on-v1 observed.
- [x] **VERIFIED** — finding lifecycle UNVERIFIED → VERIFIED /
  REFUTED enforced by `FindingStore` (sole authority).
- [x] **VERIFIED** — replan causality: `parent_plan_id` /
  `plan_b_id` / `refuted_finding_id` on every replanner record;
  chain walk asserted in M9 tests.
- [x] **VERIFIED** — quality gate authority: Runner delegates;
  `outcome.gate_verdict is gate_evaluation.verdict`.

## Documentation — VERIFIED

- [x] **VERIFIED** — `docs/PROVENANCE.md` exists; license facts
  marked UNKNOWN (no LICENSE file; no license field found);
  no copied-code claims (scoped search evidence inside).
- [x] **VERIFIED** — `docs/demo-runbook.md` exists; every command
  in it was executed live on 2026-09-15 (suite/heroes/metrics/
  troubleshooting probes).
- [x] **VERIFIED** — `docs/submission-checklist.md` exists (this
  file); every box checked against a physical run above.

## Benchmark Claims — VERIFIED (bounded wording)

- [x] **VERIFIED** — designated sample is exactly n=5 baseline
  (all REFUSE) + n=5 RAPHAEL (all COMPLETE), IDs listed in
  `docs/PROVENANCE.md` §10; additional labeled observations
  disclosed, never hidden.
- [x] **VERIFIED** — no document in `docs/` claims statistical
  significance, general superiority, or percentages (searched;
  only scenario-scoped wording remains).
- [x] **DOCUMENTED** — single-scenario / n=5 scope boundary stated
  in runbook §10, checklist here, and PROVENANCE §10/§14.

## Packaging Readiness — NOT claimed

- [x] **VERIFIED now** — everything above on the current tree.
- [ ] **Requires final audit** — one more clean-tree full-suite +
  hero pass at packaging time (commands in runbook §4–§8);
  confirm `git status` clean and HEAD hash recorded.
- [ ] **Intentionally deferred** — final submission archive (ZIP)
  creation, transport, and any judge-portal steps. No archive
  exists yet; none is claimed.
