# RAPHAEL IBM BOB MVP — Provenance

This document states, with file-level evidence, what RAPHAEL is, what
it was built from, what was verified, and what remains limited. Every
claim below is traceable to the physical repository on branch
`migration/bob-mvp`. Quantitative claims cite their reproduction
command rather than pasting values that regenerate.

## 1. What RAPHAEL is

RAPHAEL is the IBM BOB Hackathon MVP: an evidence-driven control loop
that plans, acts only through a mediated boundary, verifies and
falsifies its own findings, replans from refuted claims, and lets a
single QualityGate decide completion. The implementation lives in
`raphael_ibm_bob/` (stdlib-only Python), demonstrated by
`demos/authkit_hero.py` against `fixtures/authkit/`, measured by
`scripts/audit_runs.py` over `runs/*/evidence.jsonl`.

## 2. Legacy substrate

The BOB MVP was migrated from a larger pre-existing codebase. Base
commit `7272880f7` holds that substrate: ~67,000 tracked files
forming an offensive-security platform (visible subsystems include
`src/orchestrator`, `src/raphael`, `src/agent`, `src/arena`,
`cli/`, `evaluations/`, `benchmarks/`, exploit/payload reference
material). `pyproject.toml` declares `raphael-v2 2.0.0`; planning
docs reference a 2.1 line (`docs/raphael-v2.1.md`). Beyond those two
facts, exact legacy version numbering is UNKNOWN and is not claimed.

## 3. License / attribution discipline

- No `LICENSE`/`LICENCE` file exists at the repository root, and no
  license field was found in `pyproject.toml`/`requirements.txt`.
  The root `README.md` does, however, carry a verbatim MIT grant
  (`Copyright (c) 2024-2026 The-Despicable`), retained through the
  M10.5-era README rewrite: that embedded grant is the only license
  text found in the repository, and no broader licensing claim is
  made or inferred beyond it.
- No legacy code was copied into the BOB path. Evidence: a
  repository search for legacy imports (`from src…`,
  `from raphael.…`, `import raphael…`) across `raphael_ibm_bob/`,
  `demos/`, `probes/`, `tests/` returns zero code imports; the only
  matches are docstring references, the adapter index, and test
  guards that assert the isolation. Legacy modules appear solely as
  named inspirations with file:line pointers (see §4).
- Per-module docstrings record, for each seam, whether the legacy
  source was conceptually adapted, deliberately replaced, or
  isolated. The authoritative index is
  `raphael_ibm_bob/adapters/legacy.py` (a documentation-only module; it
  contains no runtime logic).

## 4. Adapted concepts (inspiration, rewritten code)

| Legacy source | Concept reused | BOB re-expression |
|---|---|---|
| `src/orchestrator/brain/capability_broker.py` (5-dim deny-by-default authorization) | mediation + provenance receipts | `raphael_ibm_bob/broker.py` (`BOBBroker`: Policy consult before every invocation; `BrokerResult` carries ledger sequences) |
| `src/orchestrator/brain/scope_parser.py` (fail-closed scope) | fail-closed scope checks | `raphael_ibm_bob/policy.py` (`BOBPolicy`: workspace containment, mission-scope substring, capability invariants) |
| `src/orchestrator/brain/evidence.py` (frozen dataclass + SHA-256 digest) | digest-identified immutable records | `raphael_ibm_bob/evidence_ledger.py` (canonical JSON + digests; flat causal links instead of the legacy in-memory relation graph) |
| `src/orchestrator/brain/contradiction.py` (active-challenge lifecycle) | challenge apparent success with observations | `raphael_ibm_bob/falsifier.py` (broker-mediated counter-example search; `ChallengeSpec`/`ChallengeOutcome`) |
| `src/raphael/verifier/core.py` (preflight/observe/adapt lifecycle shape) | lifecycle shape only | `raphael_ibm_bob/verifier.py` (behavioral retest through Runtime/Broker/Policy, not exploit-canary callbacks) |
| `src/orchestrator/brain/action.py` (Action/Precondition/Effect shape) | action shape (capability + target + purpose) | `raphael_ibm_bob/planner.py` (BOB-native READ actions from `Mission.problem`, not offensive grammar) |

## 5. Replaced components

Deliberately replaced because legacy semantics did not match the
roadmap: the UCB utility-driven step selector
(`src/raphael/cognitive/planner.py` → mission-driven `Planner`);
the nonexistent on-target Replanner and QualityGate (built new as
`replanner.py` / `quality_gate.py`); the nonexistent
broker-mediated Runtime (built new as `runtime.py`).

## 6. Isolated legacy components

Kept outside the BOB path by test-enforced guards
(`tests/test_m5_replanner_runner.py`,
`tests/test_m7_hero.py::HeroEndToEnd`,
`tests/test_m10_3_benchmark.py::RunnerAuthority` assert no
`raphael.main` imports): the Wave 1 cognitive loop
(`src/raphael/main.py`), shell-capability machinery, trust-level
taxonomy, rate limiter, and all offensive grammars/payloads/C2
systems. The demo, runner, and tests never invoke them.

## 7. New BOB MVP components

`contracts.py` (typed request/decision/result/finding/plan/mission
records), `seams.py` (10 Protocol interfaces), `workspace.py`
(realpath containment), `policy.py`, `capabilities.py`
(READ/LIST/SEARCH/WRITE/RUN_TEST), `broker.py`, `runtime.py`,
`evidence_ledger.py` (append-only JSONL + artifacts + run
directories), `finding.py` (lifecycle store, sole transition
authority), `verifier.py`, `falsifier.py`, `replanner.py`
(evidence-derived Plan B/C), `runner.py` (bounded control loop,
delegates COMPLETE), `planner.py` (mission-driven Plan A),
`quality_gate.py` (sole COMPLETE authority, 7 conditions),
`scripts/audit_runs.py` (measurement), `probes/auth_behavior_probe.py`
(independent 10-scenario oracle).

## 8. Roadmap → implementation map

| Roadmap requirement | Implementation | Physical proof |
|---|---|---|
| Mission | `contracts.py::Mission` (+ `problem` for Plan A derivation) | `tests/test_m8_planner.py` (13 tests) |
| Planner → Plan A | `planner.py::Planner.plan_a` (no Runner injection) | `tests/test_m8_planner.py`; hero step [01] |
| Runtime → Broker → Policy | `runtime.py`, `broker.py`, `policy.py` | `tests/test_m2_boundary.py` (21); FC1 DENY in every hero run |
| Evidence (append-only, sequenced) | `evidence_ledger.py` (`runs/<id>/evidence.jsonl` + `artifacts/`) | `tests/test_m3_evidence.py`; `tests/test_m10_1_runs.py` (11) |
| Verifier (broker-mediated retest) | `verifier.py` | `tests/test_m4_verifier_falsifier.py` (17) |
| Falsifier (active challenge) | `falsifier.py` | same suite; hero step [08] counter-example |
| Replanner (Plan B from refutation) | `replanner.py` | `tests/test_m5_replanner_runner.py`; hero step [09] |
| Bounded multi-replan (Plan C, max_replans) | `runner.py` loop + per-attempt findings | `tests/test_m9_multi_replan.py` (17, mock-free) |
| QualityGate (sole COMPLETE, 7 checks) | `quality_gate.py` (B/C ledger-hardened at M9) | `tests/test_m6_quality_gate.py` (19); gate record per run |
| Hero (authkit defect/decoy) | `demos/authkit_hero.py`, `fixtures/authkit/`, probe | `tests/test_m7_hero.py`; hero exit 0, COMPLETE |
| Benchmark (baseline vs raphael) | `--mode` paths + `producer="benchmark"` provenance | `tests/test_m10_3_benchmark.py` (13); `metrics.json:by_mode` |

## 9. Architectural story (judge-facing)

```text
Mission → Plan A → Runtime → Broker → Policy → Evidence → Finding
→ Verification → Falsification → Refutation → Focused Context
→ Replanning → Plan B / Plan C → Independent verification
→ QualityGate → COMPLETE / REFUSE
```

Two failure classes are the product story, both demonstrated live in
every raphael run: **Failure Class 1** — an unauthorized action
(RUN_TEST on a non-test file) is DENIED with no side effect and no
result record (never treated as executed, never counted by the
repaired gate). **Failure Class 2** — superficial success (v1 fix,
named test green) is not treated as verified completion: the
falsifier refutes it with a real counter-example, the replanner
derives Plan B from that evidence, and only the independent probe
plus real test evidence lets the gate complete.

## 10. Benchmark disclosure (M10.3)

- Designated baseline sample: **n=5** valid runs
  (`100350_3b7a3a`, `100353_acdaa7`, `100357_18c9ed`,
  `100401_714532`, `100406_ebb5d2`), all REFUSE (probe condition).
- Designated RAPHAEL sample: **n=5** valid runs
  (`100409_8191ad`, `100413_469288`, `100417_f7f26f`,
  `100420_9b2cbd`, `100424_18ae16`), all COMPLETE 7/7.
- Scenario: authkit only (`M-authkit`, same mission/fixture/workspace/
  initial state both modes; the absent challenge/replan is the
  experimental difference).
- Baseline: v1 fix + named-test-only verification, no falsifier, no
  replan; oracle probe recorded red.
- RAPHAEL: full evidence-driven control loop above.
- Additional valid labeled observations exist (real executions from
  test/dev runs, e.g. the M10.3 suite's own end-to-end runs); they
  are included in `by_mode` totals. Current totals: regenerate
  `metrics.json` (never trust a stale copy).
- This sample demonstrates the mechanism, not generality: no claim
  is made beyond the designated authkit sample. Phrases such as
  "X% better" do not appear in this project and are not supported.

## 11. Metrics reproduction

```bash
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

Metrics derive exclusively from `runs/*/evidence.jsonl` (+ artifact
files for the resolved count). Verdicts come from persisted gate
records, never exit codes. `metrics.json` is generated output
(git-ignored). Full semantics: `docs/metrics.md`. Determinism: same
evidence → identical metric values (only `generated_at` varies).

## 12. Reproduction commands (verified 2026-09-15)

```bash
PYTHONPATH=. python3 demos/authkit_hero.py                  # raphael, COMPLETE, exit 0
PYTHONPATH=. python3 demos/authkit_hero.py --mode raphael   # identical to default
PYTHONPATH=. python3 demos/authkit_hero.py --mode baseline  # REFUSE via probe, exit 1
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner tests.test_m9_multi_replan tests.test_m10_1_runs tests.test_m10_2_metrics tests.test_m10_3_benchmark
```

Expected: 209 passed, 0 failed. (`unittest discover` finds 0 tests
in this layout; the explicit suite command above is authoritative.)

## 13. Checkpoint history (physical commits, branch `migration/bob-mvp`)

```text
1039ebf58  M0  repository inventory + archaeology
d16333c92  M1  migration seams
ac3c177ad  M2  runtime/broker/policy boundary
4b87bf31a  M3  append-only evidence ledger
1d1a6ba58  M4  verifier + falsifier
3a27f20f5  M5  replanning + runner
6d364eb59  M6  evidence-backed quality gate
a76efd0ff  M7  authkit hero + real planner
a19fcc30c  M8-partial (tests moved to Mission.problem shape; inconsistent alone)
7ebcca046  M8-complete (mission-driven planner, consistent tree)
7498a420c  M9  bounded multi-replan + gate/lifecycle hardening
2c24f88c8  M10.1 durable runs/<run_id>/ persistence
0b3589ed0  M10.2 evidence-backed metrics aggregation
a5506a279  M10.3 benchmark modes + real run dataset
```

Base: `7272880f7`. Per-milestone design notes:
`docs/migration/M{2,3,4,5,6,7,8,9}-*.md`,
`docs/migration/M10.1-durable-runs.md`, `docs/metrics.md`.

## 14. Limitations (all evidence-backed)

1. Cross-scenario generality is not established (one scenario:
   authkit).
2. Statistical significance is not established (designated n=5 per
   mode; labels beyond that are incidental observations).
3. Environment uses Python 3.14.4 although `pyproject.toml`
   declares `requires-python = ">=3.11,<3.13"`.
4. Mode provenance exists only for benchmark runs made after M10.3;
   the 40+ pre-mode hero observations stay `mode="unknown"` and are
   excluded from `by_mode` (never relabeled after the fact).

## 15. Phase 2C C1A (out-of-process inspection)

C1A (`Capability.C1A_STATIC_FILE_INSPECT`) extends the same governed
boundary rather than bypassing it: an authorized, single-use binding
(`c1a_authorization`) feeds a bounded transport and the pinned
`provider/c1a_launcher.js`. Provider output is classified as UNTRUSTED
evidence (`c1a_evidence`) and can never produce VERIFIED/REFUTED/COMPLETE.

Honesty boundary (unchanged, explicit):

- The **real T3MP3ST provider is absent**; `T3MP3STAdapter` fails closed.
- `InertProviderDouble` is test infrastructure and is never called
  "T3MP3ST".
- Live proof is **BLOCKED** (`scripts/c1a_live_proof.py`,
  `LIVE_PROOF_AUTHORIZED = False`). No M1/M2/M5 or provider-execution
  claim is made.
- The design substrate (`isolation_substrate`, `seccomp_policy`) is
  ISOLATED/DECLARED; it is not launched by this implementation.

See `docs/integration/c1a-evidence-contract.md`,
`docs/integration/c1a-runbook.md`, and
`docs/integration/c1a-release-gate.md`.
