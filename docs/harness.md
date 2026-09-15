# RAPHAEL Harness Foundation (M13)

The Harness is the operator/programmatic layer around the RAPHAEL
governance core. It orchestrates, persists, observes, and exposes
state. It is **not** an authority.

## The critical distinction

```text
HARNESS  ≠  AUTHORITY
```

- **Harness** owns: session, workspace view, mission intake, run
  lifecycle records, event projection, evidence/artifact inspection,
  model configuration, cancellation, CLI.
- **RAPHAEL core** owns: authorization (Policy), execution
  (Broker + capabilities), Evidence, Verification, Falsification,
  Replanning, and the QualityGate's COMPLETE/REFUSE decision.

The Harness never executes a capability, never bypasses
Runtime → Broker → Policy, never writes evidence, and never decides
completion. It is a thin orchestration + read-only inspection layer.

## 1. Harness responsibilities

- Create and persist **sessions** (mission + workspace + model
  reference + run history).
- Accept **missions** and hand them to the core.
- Start **runs** — either Runner-driven (`start_run`) or model-led
  (`start_model_run`) — and record their lifecycle.
- Project the ledger into a deterministic **event stream**.
- Expose **read-only** access to evidence, artifacts, the gate
  record, and the seal.
- Provide a **CLI** that calls the same public API.

## 2. RAPHAEL core responsibilities (unchanged)

```text
Model → Skill Registry → ActionRequest
      → Runtime → Broker → Policy
      → Execution → Evidence
      → Verification → Falsification → Replan
      → Independent Verification → QualityGate
      → COMPLETE / REFUSE
```

Only `QualityGate.evaluate` constructs `GateVerdict.COMPLETE`
(single site, `quality_gate.py`). Only `broker.py` calls
`execute_capability`. The Harness adds neither.

## 3. API surface

`raphael_ibm_bob.harness.api`:

| Operation | Purpose |
|---|---|
| `create_session(...)` / `get_session(id)` / `get_sessions()` | session lifecycle |
| `submit_mission(id, mission)` | attach/replace mission |
| `start_run(session, ...)` | Runner-driven governed run |
| `start_model_run(session, model=..., probe=..., max_turns=...)` | model-led governed run |
| `get_run(id)` / `get_runs()` | run records |
| `cancel_run(id)` | cooperative cancel (pending only) |
| `get_events(id)` | deterministic event projection |
| `get_evidence(id)` | read-only ledger records |
| `get_artifacts(id)` | artifact paths |
| `get_gate(id)` | last QualityGate record |
| `get_seal(id)` | evidence seal verification |
| `describe_workspace(root, ...)` | read-only workspace view |
| `make_model_adapter(provider)` | provider from env config |

All functions take a `runs_root` / `sessions_root` (defaults `runs/`,
`sessions/`).

## 4. Session / Run / Workspace relationship

```text
Session (durable, sessions/<id>/session.json)
  ├── mission            (Mission)
  ├── workspace          (WorkspaceContext: root + project + run_ids)
  ├── provider/model     (names only — never credentials)
  ├── status             (open, ...)
  └── run_ids[] →        Run (runs/<run_id>/harness.json)
                           ├── mission, workspace_root
                           ├── state (see below)
                           ├── ledger_dir → evidence.jsonl + artifacts/
                           ├── plan_ids, finding_ids
                           └── gate_verdict
```

`WorkspaceContext` describes; it never executes. Containment rules
stay in the core `Workspace`. `describe_workspace` answers "what
runs/artifacts/capabilities belong here" without granting anything.

## 5. Event model

Events are a **deterministic projection** of committed ledger records
(plus clearly-marked `synthetic` context events) — there is no second
event source and no event is manufactured to fake progress. Replaying
the same ledger yields the same event list. Types: `SESSION_CREATED`,
`MISSION_STARTED`, `PLAN_CREATED`, `ACTION_REQUESTED`,
`POLICY_DECISION`, `EXECUTION_RESULT`, `EVIDENCE_RECORDED`,
`FINDING_CHANGED`, `VERIFICATION_RESULT`, `FALSIFICATION_RESULT`,
`REPLAN_CREATED`, `GATE_EVALUATED`, and terminal `RUN_*` events.
Reconstruction works after process restart (reads only from disk).

## 6. Cancellation semantics (honest)

- A **pending** run (allocated, not executing) can be cancelled;
  `cancel_run` returns it in state `cancelled`.
- A run **already executing** synchronously cannot be preempted;
  `cancel_run` reports it unchanged (`cancel == False`). In-flight
  provider HTTP calls remain bounded by `RAPHAEL_MODEL_TIMEOUT`.
- A terminal run is never silently restarted as the same run.
- Cancellation never corrupts evidence: it changes only the run
  record's state.

## 7. Evidence / artifact access

Read-only. `get_evidence` returns parsed ledger records; `get_artifacts`
returns paths; `get_gate` returns the last `kind="gate"` record;
`get_seal` verifies the tamper-evident seal. The API exposes no way to
rewrite or delete evidence. Missing runs/seals raise or return an
explicit reason rather than a silent empty result.

## 8. Governance boundary

- No direct capability invocation, no subprocess, no network in the
  Harness (only the provider adapter opens a socket).
- Model output is validated against the Skill Registry before it
  becomes an `ActionRequest`; invalid proposals never reach the Broker.
- A DENIED action does not execute.
- `DoneSignal` ends the turn loop but cannot cause COMPLETE — the
  QualityGate evaluates the persisted evidence independently.

## 9. Live provider configuration

```bash
RAPHAEL_MODEL_ENDPOINT=https://opencode.ai/zen/go/v1 \
RAPHAEL_MODEL_NAME=deepseek-v4.1-flash \
RAPHAEL_MODEL_API_KEY=<key> \
PYTHONPATH=. python3 demos/live_authkit_hero.py
```

`RAPHAEL_MODEL_TIMEOUT`, `RAPHAEL_MODEL_MAX_TOKENS`,
`RAPHAEL_MODEL_TEMPERATURE`, `RAPHAEL_MODEL_EXTRA_BODY`, and
`RAPHAEL_MODEL_OPENCODE_HEADERS` tune the call. Credentials are read
from the environment only, never persisted in sessions or evidence.
OpenCode-specific headers are sent only to OpenCode endpoints.

## 10. Limitations

- Cancellation is cooperative before dispatch; in-flight synchronous
  calls are bounded by timeout, not preempted.
- `get_run` works for Harness-started runs (those with a
  `harness.json`); the scripted deterministic hero writes only a
  ledger.
- The model-led run's `plan_ids` is empty: the model proposes
  capability actions directly (no Planner `Plan` objects). Replanning
  remains a core capability verified deterministically.
- One scenario; small samples; no statistical claim.
