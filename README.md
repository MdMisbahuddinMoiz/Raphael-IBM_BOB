# Raphael-IBM_BOB — Evidence-Driven AI Control Loop (IBM BOB MVP)

RAPHAEL IBM BOB is a governed execution system: it plans against a
mission, acts only through a mediated boundary (Runtime → Broker →
Policy), verifies and falsifies its own findings, replans from
refuted claims, and lets a single QualityGate decide completion.
Every action leaves append-only evidence. Nothing executes outside
the boundary.

```text
Mission → Plan A → Runtime → Broker → Policy → Evidence → Finding
→ Verification → Falsification → Refutation → Replanning
→ Plan B / Plan C → Independent verification → QualityGate
→ COMPLETE / REFUSE
```

## Status (verified, not claimed)

- Branch: `migration/bob-mvp`
- Full suite: **209 tests, 0 failures** (explicit unittest module list)
- Hero demo (`demos/authkit_hero.py`): exit 0, `Gate: COMPLETE`
- Baseline mode (`--mode baseline`): exit nonzero, `Gate: REFUSE`
  (probe condition only — the honest failure signature)
- Benchmark: designated **n=5 baseline + n=5 RAPHAEL**, single
  authkit scenario; additional labeled observations disclosed in
  `docs/PROVENANCE.md`. No generality or significance claimed.
- Submission readiness is **not** claimed here; see
  `docs/submission-checklist.md` for the staged verification state.

## Quickstart (tested on Python 3.14.4, Ubuntu/WSL, stdlib only)

No installation step: `raphael_ibm_bob`, the demo, and the tests are
stdlib-only in their imports (test execution spawns the same
interpreter as a subprocess for RUN_TEST capabilities and the
independent probe). `pytest` is not required. Commands assume the
repository root as working directory; `PYTHONPATH=.` is
belt-and-braces (the demo and tests self-bootstrap `sys.path`).

```bash
# Full test suite (authoritative; `unittest discover` finds 0 tests here)
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner tests.test_m9_multi_replan tests.test_m10_1_runs tests.test_m10_2_metrics tests.test_m10_3_benchmark

# Hero: full governed loop to COMPLETE
PYTHONPATH=. python3 demos/authkit_hero.py

# Benchmark modes
PYTHONPATH=. python3 demos/authkit_hero.py --mode raphael   # same as default
PYTHONPATH=. python3 demos/authkit_hero.py --mode baseline  # REFUSE via probe

# Metrics from durable evidence (output is git-ignored; regenerate, don't trust copies)
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

Each run writes an isolated `runs/<run_id>/{evidence.jsonl,artifacts/}`
(never `/tmp`, never appended across runs) and prints its run ID,
evidence path, and gate verdict. Fixture files self-restore, so
`git status` stays clean.

## What the demo proves

A planted, deterministic auth defect (`fixtures/authkit/session.py`
ignores token expiry and user binding) behind a plausible decoy
(`login.py`). The loop: Plan A → decoy v1 fix → named test passes
→ independent 10-scenario probe fails → falsifier refutes with a
real counter-example → replanner derives Plan B from that evidence
→ correct fix through the boundary → probe green → QualityGate
COMPLETE. Two failure classes are demonstrated live: **FC1** — a
denied action is never reported as executed; **FC2** — a passing
named test is never reported as completion.

## Project layout

```text
raphael_ibm_bob/   governed core: contracts, seams, workspace, policy,
                   capabilities, broker, runtime, evidence ledger,
                   finding store, verifier, falsifier, replanner,
                   runner, mission-driven planner, quality gate
demos/             authkit_hero.py (raphael + baseline benchmark paths)
probes/            independent behavior probe (external oracle)
fixtures/          deterministic authkit scenario
scripts/           audit_runs.py (evidence-backed metrics)
tests/             209 tests incl. mock-free M9 recovery suite
docs/              PROVENANCE.md, demo-runbook.md,
                   submission-checklist.md, metrics.md, migration/
runs/              durable run evidence (generated, git-ignored)
```

## Legacy substrate (isolated, not current capability)

This repository grew from a larger offensive-security research
platform (base commit `7272880f7`; legacy `src/`, `scripts/`,
`evaluations/`, `arena/`, and related report directories). That
substrate is **isolated, not imported** by the BOB path (zero
legacy code imports; test-enforced guards) and is **not** part of
the demonstrated system. Full provenance — adapted concepts,
replacements, isolations, and the no-copied-code evidence — is in
`docs/PROVENANCE.md`; per-milestone history in `docs/migration/`.

## Limitations

1. One scenario (authkit); cross-scenario generality not established.
2. Designated benchmark n=5 per mode; statistical significance not
   established.
3. Tested on Python 3.14.4 although `pyproject.toml` declares
   `>=3.11,<3.13`; other versions untested (UNKNOWN).
4. Mode provenance exists only for post-M10.3 benchmark runs;
   earlier hero observations stay `mode="unknown"`.

## License

```
MIT License

Copyright (c) 2024-2026 The-Despicable

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
