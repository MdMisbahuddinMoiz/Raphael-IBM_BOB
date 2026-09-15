# M15.1 — RAPHAEL Harness HTTP/JSON API

A small HTTP/JSON API over the existing Harness. It is a
**presentation / integration layer**, **not an execution authority**.

```text
HTTP  ->  harness.api  ->  existing Harness
      ->  Runtime -> Broker -> Policy -> Execution
      ->  Evidence -> Verification -> Falsification -> Replan
      ->  QualityGate
```

The HTTP layer never bypasses `harness.api`. It does not call
`execute_capability`, the Broker, Policy, the QualityGate, the
capabilities module, the ledger writer, `subprocess`, or any outbound
network function. The core never imports this package
(`RAPHAEL core -> HTTP` does not exist).

## 1. Architecture

- **Framework:** Python standard library `http.server`
  (`ThreadingHTTPServer`). **No new dependencies.** The repository is
  deliberately stdlib-only; adding FastAPI would pull in
  pydantic/starlette/uvicorn for no governance benefit, and the
  RAPHAEL core must remain usable without any HTTP server. Choosing
  stdlib keeps the change minimal and auditable.
- **Dependency direction:** `raphael_ibm_bob/http` imports
  `raphael_ibm_bob.harness.api` and pure declarations
  (`contracts`, `harness.providers` error types). Nothing in
  `raphael_ibm_bob/**` outside `http/` imports `http/`.
- **Package shape:**

  ```text
  raphael_ibm_bob/http/
      __init__.py        lazy re-export of the app surface
      app.py             config, router, dispatch, transport, main()
      errors.py          structured errors + stable codes
      schemas.py         explicit, whitelisted JSON projections
      routes/
          _common.py     request-body / mission parsing
          health.py      GET /health
          sessions.py    session + mission routes
          runs.py        run lifecycle + inspection
          workspaces.py  read-only workspace description
          discovery.py   read-only roles/skills/capabilities
          tasks.py       read-only task decomposition
  ```

- **Events are a projection.** `GET /runs/{id}/events` folds the
  persisted ledger via the existing `harness.events.collect_events`;
  there is no second event bus. Evidence, gate, artifacts, and seal
  are read from authoritative persisted state.

## 2. Endpoint list

| Method | Path | Harness API |
|---|---|---|
| GET  | `/health` | (none; liveness) |
| GET  | `/sessions` | `get_sessions()` |
| POST | `/sessions` | `create_session()` |
| GET  | `/sessions/{session_id}` | `get_session()` |
| POST | `/sessions/{session_id}/missions` | `submit_mission()` |
| GET  | `/runs` | `get_runs()` |
| POST | `/runs` | `start_run()` |
| POST | `/runs/model` | `make_model_adapter()` + `start_model_run()` |
| GET  | `/runs/{run_id}` | `get_run()` |
| POST | `/runs/{run_id}/cancel` | `get_run()` + `cancel_run()` |
| GET  | `/runs/{run_id}/events` | `get_events()` |
| GET  | `/runs/{run_id}/evidence` | `get_evidence()` |
| GET  | `/runs/{run_id}/artifacts` | `get_artifacts()` |
| GET  | `/runs/{run_id}/gate` | `get_gate()` |
| GET  | `/runs/{run_id}/seal` | `get_seal()` |
| GET  | `/runs/{run_id}/tasks` | `get_tasks()` |
| GET  | `/runs/{run_id}/tasks/{task_id}` | `get_tasks()` |
| GET  | `/workspaces/{workspace_id}` | `describe_workspace()` |
| GET  | `/roles` | `list_roles()` |
| GET  | `/skills` | `list_skills()` |
| GET  | `/capabilities` | `list_capabilities()` |

Read = sessions/runs/events/evidence/artifacts/gate/seal/tasks/
workspace/discovery. Write/control = create session, submit mission,
start run, model run, cancel. There are **no execution endpoints**.

## 3. Request / response examples

Every response is deterministic JSON.

```bash
# liveness
curl -s localhost:8787/health
# {"service":"raphael-harness","status":"ok"}

# create a session bound to a workspace and mission
curl -s -X POST localhost:8787/sessions -H 'Content-Type: application/json' -d '{
  "workspace_root": "/abs/path/to/workspace",
  "project_name": "authkit",
  "mission": {"mission_id":"M-1","description":"fix","scope":"src/",
              "criteria":["recover"],"problem":{"symptom_target":"src/a.py"}}}'
# 201 {"session_id":"...","mission":{...},"workspace":{...}, ...}

# start one governed run
curl -s -X POST localhost:8787/runs -H 'Content-Type: application/json' \
  -d '{"session_id":"<id>"}'
# 201 {"run_id":"...","state":"refused","terminal":true,
#      "gate_verdict":"refuse", ...}

# inspect
curl -s localhost:8787/runs/<run_id>/gate
# {"run_id":"...","gate":{"kind":"gate","decision":"refuse","checks":[...]}}
curl -s localhost:8787/runs/<run_id>/events
curl -s localhost:8787/runs/<run_id>/evidence
curl -s localhost:8787/runs/<run_id>/tasks
curl -s localhost:8787/runs/<run_id>/seal

# discovery (read-only catalog; declarations grant nothing)
curl -s 'localhost:8787/skills?role=investigator'
curl -s 'localhost:8787/skills?capability=READ'
curl -s 'localhost:8787/skills?evidence_available=inspection'
curl -s 'localhost:8787/capabilities?role=test_analyst'
```

`workspace_id` is the URL-encoded workspace root path
(e.g. `/abs/ws` -> `%2Fabs%2Fws`).

## 4. Authentication behavior

- If `RAPHAEL_API_KEY` is set, every route except `/health` requires
  it via `X-API-Key: <key>` or `Authorization: Bearer <key>`.
  Comparison is constant-time (`hmac.compare_digest`).
- The key is read from the environment only. It is **never persisted,
  never logged, and never returned**. `log_message` logs only
  method + path.
- If `RAPHAEL_API_KEY` is unset, authentication is **disabled** — the
  interface is open. This is documented and is acceptable only for
  local/demo use on loopback (see §5 and §10).
- Authentication protects the HTTP interface. It does **not** bypass
  Policy: every capability execution is still authorized by Policy.

## 5. Host / port configuration

- Default bind: `127.0.0.1:8787` (loopback only).
- Environment: `RAPHAEL_HTTP_HOST`, `RAPHAEL_HTTP_PORT`,
  `RAPHAEL_HTTP_SESSIONS_ROOT`, `RAPHAEL_HTTP_RUNS_ROOT`,
  `RAPHAEL_HTTP_MAX_TURNS`.
- CLI flags: `--host`, `--port`, `--sessions-root`, `--runs-root`,
  `--verbose`.
- Binding to a non-loopback address is an explicit opt-in (you must
  set it). When non-loopback and no `RAPHAEL_API_KEY` is set, the
  server prints a warning. It never *defaults* to `0.0.0.0`.
- The server is **inbound only**. It opens no outbound network path.
  The only external outbound path remains the model provider adapter
  (`harness/providers/openai_compat.py`).

## 6. Error semantics

Structured JSON, no stack traces, no secrets:

```json
{"error": {"code": "RUN_NOT_FOUND", "message": "Run not found"}}
```

| Status | Code | When |
|---|---|---|
| 400 | `BAD_REQUEST` | malformed JSON body, bad `Content-Length` |
| 401 | `UNAUTHORIZED` | API key missing/invalid (when enabled) |
| 404 | `SESSION_NOT_FOUND` / `RUN_NOT_FOUND` / `WORKSPACE_NOT_FOUND` / `TASK_NOT_FOUND` / `ROLE_NOT_FOUND` / `NOT_FOUND` | missing resource or unknown route |
| 405 | `METHOD_NOT_ALLOWED` | path exists, method does not |
| 409 | `RUN_TERMINAL` / `RUN_NOT_CANCELLABLE` | illegal lifecycle operation |
| 413 | `PAYLOAD_TOO_LARGE` | body exceeds 1 MiB |
| 422 | `INVALID_INPUT` | semantically invalid input |
| 503 | `MODEL_NOT_CONFIGURED` | live model requested, env not configured |
| 500 | `INTERNAL_ERROR` | unexpected failure (generic message) |

Domain exceptions are mapped to these codes; useful errors are never
swallowed (e.g. a missing session on `POST /runs` is
`SESSION_NOT_FOUND`, not a generic 500).

## 7. Cancellation semantics

`POST /runs/{run_id}/cancel` is **honest**; it does not claim process
control it does not have:

- `pending` -> cancelled; `200 {"cancelled": true, "run": {...}}`.
- `cancelled` -> idempotent; `200 {"cancelled": false, "note":
  "already cancelled"}`.
- `running` -> `409 RUN_NOT_CANCELLABLE`: a synchronously executing
  run cannot be force-killed; the in-flight execution timeout remains
  the bound.
- terminal (`completed`/`refused`/`failed`) -> `409 RUN_TERMINAL`: a
  terminal run is never silently restarted.

## 8. Event / evidence access

- `GET /runs/{id}/events` — deterministic projection folded from the
  ledger (`collect_events`). Replaying the same ledger yields the same
  list. Synthetic context events are marked `"synthetic": true`.
- `GET /runs/{id}/evidence` — the persisted JSONL records, verbatim.
- `GET /runs/{id}/artifacts` — `{name, size}` descriptors (no
  absolute paths).
- `GET /runs/{id}/gate` — the **last persisted** QualityGate record,
  or `null` if none. The HTTP layer does not compute a verdict.
- `GET /runs/{id}/seal` — `{ok, reason}` from `verify_seal`. A fresh
  run has no sidecar seal yet and reports
  `{"ok": false, "reason": "missing-seal"}` (honest, never faked).
  The HTTP layer never writes seals.

## 9. Governance boundary

- All routes call `harness.api`; discovery reads the single
  authoritative `CapabilityRegistry`.
- No route calls `execute_capability`, `capabilities._write`, the
  Broker, Policy, Runtime, the QualityGate, `subprocess`, or writes
  evidence/seals.
- No route constructs `GateVerdict.COMPLETE`; completion remains the
  QualityGate's sole authority.
- No route creates a second model loop or second provider:
  `POST /runs/model` uses `make_model_adapter` + `start_model_run`,
  i.e. the existing provider adapter and the existing
  `run_model_mission` loop. The model only proposes; every proposal is
  validated and submitted through Runtime -> Broker -> Policy.
- Static boundary checks live in
  `tests/test_m15_1_http_api.py::GovernanceStatic` (W/X/Y/Z).

## 10. Security limitations

- **Auth is optional and minimal.** With `RAPHAEL_API_KEY` unset the
  interface is unauthenticated; intended for loopback/demo. There is
  no IAM, RBAC, or multi-tenancy (deferred).
- **No TLS.** The server speaks plain HTTP. Do not expose it beyond
  loopback without a TLS-terminating proxy and an API key.
- **Arbitrary workspace paths.** `GET /workspaces/{workspace_id}`
  describes any directory path supplied (read-only: `is_dir` +
  associations + declared capability allow-list). It does not execute
  anything, but it does confirm directory existence. Bind to loopback.
- **No probe over HTTP.** `/runs/model` does not accept a caller
  probe (the probe is a Python callable owned by the caller; the HTTP
  layer must not spawn subprocesses). A live mission whose gate
  requires an independent behavior probe will therefore be REFUSEd
  over HTTP — honest, and a deliberate boundary.
- **Synchronous model runs.** `POST /runs/model` blocks until the run
  terminates; the request timeout bounds it. No background queue.
- **Live model output is sampled.** The provider occasionally returns
  empty or malformed JSON (despite `response_format: json_object`),
  which the Harness surfaces as `terminal: "model-error"` with a
  redacted `terminal_reason` (`StructuredProposalError` / `ProviderError`).
  This affects the direct API and HTTP paths identically — see §13.
- **Provider session routing.** OpenCode Go routes on the
  `x-opencode-session` header (the Harness `session_id`). Reusing one
  session id across independent runs shares the provider's server-side
  conversation state; use a fresh session per run for clean
  comparisons. Generic OpenAI-compatible endpoints do not receive this
  header.

## 11. Local demo usage

```bash
# start the server (loopback, no auth) from the repo root
PYTHONPATH=. python3 -m raphael_ibm_bob.http --port 8787

# with auth enabled
RAPHAEL_API_KEY=secret PYTHONPATH=. python3 -m raphael_ibm_bob.http

# then, in another shell:
curl -s localhost:8787/health
```

Programmatic start (used by tests and the smoke script):

```python
from raphael_ibm_bob.http.app import RaphaelHTTPConfig, create_server
config = RaphaelHTTPConfig(sessions_root="sessions", runs_root="runs",
                           host="127.0.0.1", port=8787)
server = create_server(config)   # returns the server; call serve_forever()
```

`dispatch(request, config)` is transport-independent and always
returns a `Response`, so in-process callers behave exactly like HTTP
clients.

## 12. Verified smoke result

Real HTTP smoke against the running server (stdlib client):

- `GET /health` 200; session created; authkit mission submitted;
  one Runner-driven run started and inspected (run, events, evidence,
  gate, tasks, seal); discovery (`/roles`, `/skills`).
- Deterministic run: `20260915T170614_02d4fe` (`Gate: REFUSE` — the
  Runner path has no independent probe; honest).
- **Live** DeepSeek V4.1 Flash model run through `POST /runs/model`:
  run `20260915T170615_8aa105`, terminal `model-error` after 7
  governed turns, `Gate: REFUSE` (no probe over HTTP — §10). Selected
  skills observed: `read-file` (investigator), `run-test`
  (test_analyst), `write-file` (remediation_planner) — all mediated by
  Runtime -> Broker -> Policy.

The `model-error` above was investigated in M15.2 (§13); it is a live
model-output failure, not an HTTP-layer defect.

## 13. Direct / HTTP parity (M15.2)

**`POST /runs/model` is the same governed operation as
`harness.api.start_model_run()`.** The route builds the provider with
`api.make_model_adapter(provider)` (the same env factory the direct
caller uses) and calls `api.start_model_run(...)` — no second model
loop, no second provider, no bypass of Runtime/Broker/Policy.

Proven deterministically (`tests/test_m15_2_parity.py`, stub provider,
real adapter + real loop + real core): direct and HTTP runs produce
**byte-identical provider request bodies** (mission summary, skills
catalog, roles, active task, workspace files, recent turns), identical
config fields (`model`, `max_tokens`, `temperature`,
`response_format`), identical terminal states and terminal reasons, and
governed evidence (`request`/`decision`/`result`).

**Single shared default.** The turn bound now has one source of truth,
`harness.model_run.DEFAULT_MAX_TURNS = 14`, referenced by
`api.start_model_run`, `run_model_mission`, and
`RaphaelHTTPConfig.default_max_turns`. Before M15.2 the HTTP layer
defaulted to 8 while the Harness defaulted to 14 — a configuration
inconsistency for an omitted `max_turns` (fixed; not the cause of the
observed `model-error`).

**Error parity.** Provider/structured failures surface identically:
both paths end `terminal: "model-error"` with a redacted
`terminal_reason` (e.g. `ProviderError:provider HTTP 500`,
`StructuredProposalError:empty model response`). The HTTP response
includes `terminal_reason`.

**Live paired evidence (DeepSeek V4.1 Flash, fresh session per path,
identical mission/config, no probe):** across several pairs both paths
produced a mix of `done`, `max-turns`, and `StructuredProposalError`;
in one instrumented pair the HTTP path ran 6 clean turns
(`max-turns`, no model error) while the direct path hit
`StructuredProposalError:missing purpose` (10 provider calls, **zero**
empty responses). The initial HTTP `model-error` was a provider/model
output failure, present on the direct path too — **not** an
HTTP-specific bug.

Parity is about *semantics and configuration*, not about both runs
happening to complete. Over HTTP there is no caller probe, so even a
clean `done` yields `Gate: REFUSE`; that is a deliberate boundary, not
a parity gap.

