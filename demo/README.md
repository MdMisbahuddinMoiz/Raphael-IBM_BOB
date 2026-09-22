# RAPHAEL × IBM BOB — Demo Evidence Package

This directory is the reproducible, machine-readable evidence package for the
hackathon demonstration. It contains **two canonical persisted runs** and the
transcripts produced by the canonical entrypoint
[`scripts/run_hackathon_demo.sh`](../scripts/run_hackathon_demo.sh).

> Nothing in this package is hand-typed. Every JSON file is exported directly
> from the append-only ledger of a real run by
> [`scripts/demo_export.py`](../scripts/demo_export.py); re-running reproduces
> them from the same run.

## Layout

```text
demo/
  README.md            this file
  success/             DEMO A — governed run → 7/7 COMPLETE
  refusal/             DEMO B — honest refusal → REFUSE
  screenshots/         operator-captured UI screenshots (see README there)
  transcripts/         raw stdout of the canonical demo driver
```

Each of `success/` and `refusal/` contains:

| File | Contents |
|---|---|
| `run.json` | the persisted Harness run record (`runs/<id>/harness.json`) |
| `ledger.jsonl` | an exact copy of the append-only evidence ledger (unmodified) |
| `gate.json` | the persisted QualityGate record for the run |
| `summary.json` | derived, reproducible summary: A–G, requests, probe, regression |
| `transcript.txt` | human-readable transcript of the same chain |

## DEMO A — success (QualityGate COMPLETE)

```text
run_id     : 20260922T184344_cad5ac
mission    : M-HTB-001
state      : completed
verdict    : complete
conditions : 7/7  (A B C D E F G all PASS)
```

Chain: `TESTING/HTB → TargetProfile → NETWORK_HTTP_REQUEST → Policy ALLOW →
execution → independent probe → RUN_TEST → regression evidence → QualityGate →
COMPLETE`.

## DEMO B — refusal (QualityGate REFUSE)

```text
run_id     : 20260922T184344_7686de
mission    : M-HTB-001
state      : refused
verdict    : refuse
conditions : 6/7  (D FAIL — independent behavior probe has no proof)
```

The authorized target service was unavailable. The governed requests were
ALLOWed by Policy but the service did not answer, so no probe evidence was
produced. Raphael recorded the failure and the QualityGate **REFUSED** — it did
not convert failure into COMPLETE.

## Regenerating this package

With the server running and an authorized HTTP target reachable:

```bash
./scripts/run_hackathon_demo.sh --success   # note the printed run_id
./scripts/run_hackathon_demo.sh --refuse    # note the printed run_id
python3 scripts/demo_export.py <success_run_id> demo/success
python3 scripts/demo_export.py <refusal_run_id> demo/refusal
```
