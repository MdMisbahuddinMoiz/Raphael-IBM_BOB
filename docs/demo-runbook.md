# RAPHAEL IBM BOB MVP — Demo Runbook

Judge-facing reproducibility guide. Every command below was physically
executed against branch `migration/bob-mvp` on 2026-09-15 (Python
3.14.4, Ubuntu/WSL). Nothing here is copied from memory: if a command
is listed, it ran. Related documents: `docs/PROVENANCE.md` (what the
system is), `docs/metrics.md` (what the numbers mean).

## 1. Purpose

The demo proves that an evidence-driven control loop can fix a real
(planted, deterministic) defect without ever acting outside a
mediated boundary:

```text
Mission → Plan A → ActionRequest → Runtime → Broker → Policy
→ ExecutionResult → EvidenceReceipt → Observation/Finding
→ Retest/Verification → Falsification → Focused Context → Replan
→ Plan B/C → Independent verification → Output Quality Gate
→ COMPLETE / REFUSE
```

Every stage above exists in `raphael_bob/` and is exercised by the
hero (`demos/authkit_hero.py`). The demo does not claim generality:
one scenario (authkit), one mission (`M-authkit`), deterministic
fixture. See §10 for the exact scope boundary.

## 2. Environment / prerequisites

- Python **3.14.4** (verified: `python3 --version`). `pyproject.toml`
  declares `requires-python = ">=3.11,<3.13"`: the suite passes on
  3.14.4 anyway, but compatibility with any other version is NOT
  claimed — only 3.14.4 was tested.
- Repository root as working directory for all commands below.
- `raphael_bob`, the demo, and the tests are **stdlib-only** in
  their imports; test execution additionally spawns the same
  interpreter as a subprocess (`python3 -m unittest …`) for
  RUN_TEST capabilities and the independent probe. No network
  access is used or required.
- **pytest is not required** (and was not installed here). The suite
  runs on stdlib `unittest`.
- `PYTHONPATH=.` appears in the documented commands as
  belt-and-braces, but the demo and every test module
  self-bootstrap `sys.path` — all commands in this runbook were
  additionally verified to work with a bare `python3` invocation.
- OS tested: Linux (Ubuntu under WSL). No OS-specific behavior is
  relied upon beyond POSIX-style relative paths.

## 3. Setup

From a clean checkout on the right branch (no installation step —
there are no third-party runtime dependencies for the BOB path):

```bash
git status --short          # expect: clean
git log --oneline -3        # expect: M10.5-era history (see §12 of PROVENANCE.md)
git branch --show-current   # expect: migration/bob-mvp
python3 --version           # tested: Python 3.14.4
```

`runs/` is auto-created on first use; do not create it by hand.

## 4. Full test suite

The explicit module list is authoritative (`unittest discover`
finds 0 tests in this layout — verified — so it must not be used):

```bash
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner tests.test_m9_multi_replan tests.test_m10_1_runs tests.test_m10_2_metrics tests.test_m10_3_benchmark
```

Verified result: **Ran 209 tests — OK (0 failed)**. Expected stderr:
one line `error: runs root not found: /tmp/m10_2_runs_…/nope` from
the fatal-invocation test (`Determinism.test_missing_root_is_fatal`),
which asserts exit code 2 for a missing runs root. Harmless and
asserted, not a failure.

## 5. Hero demo

```bash
PYTHONPATH=. python3 demos/authkit_hero.py
```

Verified: exit 0, `Gate: COMPLETE`, durable `runs/<run_id>/`. The
judge-readable story, mapped to console steps [01]–[12]:

1. **Mission** identifies the auth/session problem (`M-authkit`).
2. **Planner** produces Plan A against the symptom file
   (`fixtures/authkit/login.py` — the decoy).
3. A plausible but incorrect remediation (v1, password
   case-folding) is attempted **through a broker-mediated WRITE**.
4. An unauthorized action (RUN_TEST on a non-test file) is
   **DENIED** by the Runtime/Broker/Policy boundary with no side
   effect and no result record.
5. Reads and the finding registration are recorded as evidence.
6. The finding is retested (**verified**) through the boundary.
7. v1 **appears successful**: the named test
   (`fixtures.authkit.test_login`) passes via a real ALLOWed
   RUN_TEST with returncode 0.
8. The **independent behavior probe**
   (`probes/auth_behavior_probe.py`, 10 scenarios, separate surface
   from the unit tests) runs as an external subprocess and FAILS on
   v1 — expired and cross-user tokens still validate.
9. The **falsifier** records a real counter-example and the finding
   transitions VERIFIED → REFUTED.
10. The **replanner** derives Plan B (`fixtures/authkit/session.py`,
    the actual defect) from the persisted counter-evidence and
    executes it through the boundary (`requester="replanner"`).
11. The correct remediation (v2) is applied via broker-mediated
    WRITE; named test, invariant test (`test_auth`), and probe all
    pass through real executions.
12. The **QualityGate — never the Runner** — evaluates 7 persisted
    conditions and authorizes COMPLETE.

### FC1 — Unauthorized action must not be falsely reported as executed

Step [04] every run: Policy DENY, `capability_invoked=False`, no
`result` record, and (since M9) the repaired gate cannot count the
denial toward required tests. Proven behaviorally in
`tests/test_m7_hero.py` and `tests/test_m9_multi_replan.py`
(unauthorized Plan C variant).

### FC2 — Superficial success must not be falsely reported as complete

Steps [06]–[09]: the v1 named-test pass never reaches the gate
unchallenged — probe red → falsifier REFUTED → replan required.
Proven by the M9 bounded-failure path (exhaustion with a REFUTED
terminal finding → REFUSE) and the baseline benchmark (§7).

## 6. Evidence inspection

Each run creates an isolated directory (never appended to by later
runs; never under `/tmp`):

```bash
ls runs/<run_id>/                  # evidence.jsonl  artifacts/
ls runs/<run_id>/artifacts/        # one JSON payload per result
```

The console prints `Run ID:`, `Run dir:`, `Evidence:
runs/<run_id>/evidence.jsonl`, and `Gate:`. Ledger kinds and their
meaning: `request` (an action was asked), `decision` (Policy ALLOW /
DENY + reason), `result` (execution outcome + `artifact_ref`),
`evidence` (producer receipts: policy/execution/verifier/falsifier/
replanner/probe/regression/benchmark), `finding` (lifecycle
transitions UNVERIFIED → VERIFIED / REFUTED), `gate` (final
verdict + passed/failed checks + evidence refs). Replan causality:
`producer="replanner"` records carry `parent_plan_id`,
`plan_b_id`, `refuted_finding_id`. The exact read pattern
(`LedgerReader(...).records()`, `gate_decisions()`) is exercised by
`tests/test_m10_1_runs.py` and was additionally executed verbatim
against a real run on 2026-09-15 (64 records, gate `complete`,
replan `P-f5947b0c1d42 → P-4159a960ba36 after F-authkit`).

`runs/*` and `metrics.json` are git-ignored by policy: runtime
outputs are reproducible artifacts, not committed evidence. A judge
re-runs commands to obtain them; nothing that must be audited only
exists in git.

## 7. Baseline benchmark

```bash
PYTHONPATH=. python3 demos/authkit_hero.py --mode baseline
```

Verified: exit **nonzero**, `Gate: REFUSE`, verdict REFUSE failed
only on `D:independent-behavior-probe`, durable `runs/<run_id>/`.
Baseline intentionally differs in exactly one experimental
dimension: v1 fix + named-test-only verification, **no falsifier
challenge, no replan, no v2 fix**. The probe oracle still runs and
is recorded red, so the shared honest gate refuses. Same mission,
fixture, workspace, initial state, and Plan A as RAPHAEL. Baseline
does not prove general inferiority — it proves that this defect,
under this protocol, cannot complete without the challenged loop.

## 8. RAPHAEL benchmark

```bash
PYTHONPATH=. python3 demos/authkit_hero.py --mode raphael
```

Verified: exit 0, `Gate: COMPLETE`, durable `runs/<run_id>/`.
Identical to the default hero command. Exercises the full governed
loop of §5 including falsification, replanning, and final gating.

## 9. Metrics reproduction

```bash
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

Verified: exit 0 (example: `runs=103 valid=103 invalid=0`).
The tool reads `runs/*/evidence.jsonl`, validates each run (parse,
dense sequences from 1, known kinds, gate present, gate `run_id`
matches directory, artifact refs resolve), and writes deterministic
`metrics.json` (sorted traversal/keys; only `generated_at` varies).
Verdicts come from persisted gate records, never exit codes.
`metrics.by_mode` separates `baseline`/`raphael` using the persisted
`producer="benchmark"` mode record; the 40+ pre-mode hero runs stay
`mode="unknown"` and are excluded from `by_mode`, never relabeled.
Per-run `mode`, requested-vs-executed capabilities, terminal finding
states, and replan counts are all ledger-derived. Do not paste
metric values from here into new claims — regenerate; the file is
git-ignored precisely so stale numbers cannot become evidence.

## 10. Benchmark methodology (facts only)

- Designated sample: **n=5 baseline + n=5 RAPHAEL**, each an
  independent execution with a unique `runs/<run_id>/`
  (IDs listed in `docs/PROVENANCE.md` §10).
- Same scenario (authkit), mission, fixture, workspace, initial
  state; mode path is the experimental difference.
- Additional valid labeled observations exist (real executions from
  test/dev runs); they are included in `by_mode` totals and
  disclosed here rather than hidden.
- Results are not generalized beyond this scenario and sample; no
  statistical-significance claim is made from n=5.

## 11. Troubleshooting (all reproduced)

- `ModuleNotFoundError: raphael_bob` — not observed with the
  documented commands: the demo and all test modules
  self-bootstrap `sys.path` (verified with bare `python3`).
  If seen, the working directory is wrong: `cd` to the repo root.
- `Ran 0 tests / NO TESTS RAN` — expected from bare `python3 -m
  unittest discover` in this layout (verified); use the explicit
  module list in §4.
- `runs/` missing — not an error: it is auto-created
  (`create_run_dir` makes parents). If a run must be re-done, just
  re-run; nothing is overwritten.
- `metrics.json` absent/stale — regenerate with §9 (it is ignored
  output, never committed).
- Python other than 3.14.4 — untested combinations; the declared
  `<3.13` range is documented as a limitation, not a promise.
  Behavior outside 3.14.4 is UNKNOWN.

## 12. Limitations

Identical to the audited `docs/PROVENANCE.md` §14 (single
scenario; n=5 significance; Python 3.14.4 vs declared `<3.13`;
pre-mode runs unlabeled). No additional limitation was found
during M10.5 verification; none was removed.
