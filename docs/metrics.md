# Metrics (M10.2)

Measurement-only layer over durable run evidence. No behavior is
measured except what persisted ledger records prove.

## What is computed

`scripts/audit_runs.py` reads `runs/*/evidence.jsonl` and writes
`metrics.json`. Aggregates (see `--help` and the module docstring for
exact definitions):

- run counts: total / valid / invalid, completion and refusal counts
  and rates (verdict = LAST persisted gate record, never exit codes)
- recovery: average/max replans (from `producer="replanner"`
  evidence), plan depth (`1 + replans`), complete/refused-with-replan
- policy: ALLOW/DENY totals, requested vs executed per capability
  (a DENY is requested but never executed)
- findings: terminal states per finding id (last finding record wins)
  kept separate from the transition count
- integrity: artifact references total vs resolved on this machine
- mode: reported `unknown` with an empty breakdown — current
  evidence carries no mode provenance, and none is fabricated

## M10.3 benchmark modes

Runs executed through the benchmark interface record one
`producer="benchmark"` evidence record with a string
`payload.mode` (`baseline` or `raphael`; see
`append_run_provenance`). The auditor reports these under
`metrics.by_mode` with the same aggregate shape per mode
(completion/refusal, replans, policy, findings, successful test
executions). Runs without mode provenance stay `mode="unknown"`
and are excluded from `by_mode` — pre-mode hero observations are
never relabeled. Interface:

```bash
python3 demos/authkit_hero.py --mode baseline   # named-test-only path
python3 demos/authkit_hero.py --mode raphael    # full control loop
```

## What evidence feeds them

Only parsed `evidence.jsonl` records of known kinds (request,
decision, result, evidence, finding, gate) plus result artifact files
for the resolved count. The tool never imports `raphael_bob`; the
JSONL schema is the contract.

## What invalidates a run

Missing/unreadable/empty `evidence.jsonl`, unparseable lines,
non-object records, unknown or missing kinds, bad sequence numbers,
non-dense sequences, missing gate record, gate `run_id` mismatch
with the directory name, or any unresolvable result artifact
reference. Invalid runs are listed with reasons in `validation` and
excluded from every aggregate — never silently.

## How to reproduce metrics

```bash
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

For a fixed evidence set the metric values are deterministic
(sorted traversal, sorted keys); only the `generated_at` metadata
field varies. `metrics.json` is generated output (git-ignored):
re-run the command instead of trusting a stale copy.

## What cannot yet be measured

- mode/baseline separation (`mode = unknown` until runs record it)
- statistical performance claims: the current `runs/` are repeated
  hero observations demonstrating that aggregation works, not a
  benchmark sample (M10.3 owns the ≥5-runs-per-mode sample)
- cross-machine artifact resolution (references are absolute paths)
