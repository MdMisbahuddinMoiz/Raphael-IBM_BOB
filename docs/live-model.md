# RAPHAEL IBM BOB MVP — Live Model Hero

This document covers model-driven execution: a real LLM proposing
actions that RAPHAEL governs, verifies, falsifies, and gates. It
separates clearly what was observed with a **live model** from what is
**deterministically verified** by fixtures and integration tests. No
statistical or general-performance claim is made.

## Architecture (unchanged by the model swap)

```text
Model
 → Skill Registry (declaration; grants no authority)
 → ActionRequest (validated model proposal)
 → Runtime → Broker → Policy
 → Execution
 → Evidence
 → Verification
 → Falsification
 → Replan
 → Independent Verification
 → QualityGate
 → COMPLETE / REFUSE
```

The model only **proposes**. Every proposal is validated against the
skill registry, then submitted through the existing
Runtime → Broker → Policy boundary. The model cannot execute a
capability directly, authorize itself, declare completion, or write
evidence. `QualityGate` remains the sole authority for COMPLETE.

## Provider

| Field | Value |
|---|---|
| Endpoint | `https://opencode.ai/zen/go/v1` (adapter appends `/chat/completions`) |
| Model | `deepseek-v4.1-flash` |
| Auth | `RAPHAEL_MODEL_API_KEY` from the environment only — never hardcoded, logged, persisted, or committed |
| Client contract | OpenCode requires a self-identifying User-Agent and a stable `x-opencode-session` routing header; both are sent **only** to OpenCode endpoints (see `OpenAICompatConfig.uses_opencode_headers`) |

## Run the live hero

```bash
RAPHAEL_MODEL_ENDPOINT=https://opencode.ai/zen/go/v1 \
RAPHAEL_MODEL_NAME=deepseek-v4.1-flash \
RAPHAEL_MODEL_API_KEY=<key> \
PYTHONPATH=. python3 demos/live_authkit_hero.py
```

Optional tuning via environment: `RAPHAEL_MODEL_TIMEOUT`,
`RAPHAEL_MODEL_MAX_TOKENS`, `RAPHAEL_MODEL_TEMPERATURE`,
`RAPHAEL_MODEL_EXTRA_BODY`, `RAPHAEL_MODEL_OPENCODE_HEADERS`.

Without model configuration the script exits 2 with a clear message
and never fabricates a run. The deterministic fallback remains
`PYTHONPATH=. python3 demos/authkit_hero.py`.

The same authkit fixture, mission (`M-authkit-live`), scope, policy,
and QualityGate criteria are used as in the deterministic hero; the
model is the experimental difference.

## Observed live result (DeepSeek V4.1 Flash)

Judge-demo run: **`20260915T161002_2ad7e0`** — reached `COMPLETE` on
the first attempt, 7/7 gate conditions, 48 ledger records,
`seal.json` present and verifying (`seal-ok`). Sequence: read
`session.py` → read `store.py` → read `test_auth.py` → `write`
`session.py` (verifier VERIFIED, probe PASS, falsifier challenge
clean) → `run_test` `test_auth.py` → `run_test` `test_login.py` →
model `done` → QualityGate COMPLETE.

Bounded sample (`M-authkit-live`, via the live driver):

| Metric | DeepSeek V4.1 Flash (OpenCode Go) |
|---|---|
| Live missions | 5 |
| Reached RUN_TEST | 4 |
| Reached WRITE | 4 |
| Reached verification (finding VERIFIED) | 4 |
| Reached falsification challenge | 4 |
| Triggered replan | 0 |
| Reached COMPLETE | 4 |
| REFUSE | 1 |

Earlier comparison (`M-authkit-live`, same harness):

| Metric | Nemotron 3.5 Lightning (NVIDIA NIM) |
|---|---|
| Live missions | 8 |
| Reached RUN_TEST | 0 |
| Reached WRITE | 0 |
| Reached COMPLETE | 0 |
| Behavior | inspection-only |

**These are observed runs on a single scenario, not a benchmark.**
They show that the governed loop is usable by at least one live model;
they do not establish performance, reliability, or generalization.

## Live vs deterministic (do not conflate)

- **LIVE MODEL-VERIFIED**: the DeepSeek runs above — a real model chose
  the actions; RAPHAEL governed, verified, falsified, and gated them.
- **DETERMINISTIC / INTEGRATION-VERIFIED**: the scripted hero
  (`demos/authkit_hero.py`), the M9 bounded-recovery suite
  (`tests/test_m9_multi_replan.py`), and the M11 integration tests
  (`tests/test_m11_4_integration.py`). These use fixtures or a scripted
  adapter but the real Runtime/Broker/Policy/Evidence/Verifier/
  Falsifier/Replanner/QualityGate.
- **LIVE REPLAN NOT OBSERVED**: in the live sample the model's first
  fix was correct, so no refutation and no replan occurred. Replanning
  is therefore **deterministically verified only** (bad fix → refute →
  Falsifier → Finding REFUTED → Replanner → Plan B → correct fix →
  independent verification → COMPLETE), with parent/child plan
  linkage asserted in the M9 suite. It is **not** claimed as
  live-model-verified.

## Limitations

- One scenario (authkit); cross-scenario generality not established.
- Small observed samples (5 live DeepSeek runs, 8 live Nemotron runs);
  no statistical significance.
- Live runs exercised the falsifier challenge but not refutation/
  replanning (the fixes were correct); replan is deterministic-only.
- Tested on Python 3.14.4 although `pyproject.toml` declares
  `>=3.11,<3.13`; other versions untested.
