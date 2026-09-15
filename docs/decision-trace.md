# M15.3 — Decision Trace (read-only operator screen)

The first operator-facing RAPHAEL screen. It explains **how an
operation progressed** from mission to Quality Gate verdict, using only
observable, persisted, auditable data.

```text
GET /operations/{run_id}/decision-trace   (text/html)
```

Read-only: `HTTP → harness.api → existing Harness`. The screen renders
a string from data the JSON API already exposes. It has **no execution
authority** — it cannot invoke a capability, call the Broker/Policy
directly, write evidence, manufacture a finding, or produce a gate
verdict.

## It is NOT a chain-of-thought viewer

The page shows the **observable decision and evidence chain** — mission,
the structured model proposal (capability/target/purpose/requester),
selected skill/role, the IBM BOB policy decision, execution result,
evidence records, finding state, verification, falsification, replan,
independent probe, and the gate record. It never reads, stores, or
displays hidden model reasoning, reasoning tokens, or deliberation.

## Data sources (existing API only)

`GET /runs/{id}`, `/events`, `/evidence`, `/gate`, `/tasks`, `/seal`,
plus `/roles`, `/skills` and the persisted session (model/provider
labels). All access goes through `harness.api`; there is no second
backend, event store, or evidence store.

## What it renders

1. **Operation header** — run id, mission, target, workspace, model,
   provider, status (`COMPLETE` / `REFUSE`).
2. **Persistent pipeline** — INVESTIGATE · REPRODUCE · REMEDIATE ·
   VERIFY · FALSIFY · INDEPENDENT PROBE · QUALITY GATE, coloured by
   authoritative state (a phase is never shown complete unless the
   data says so).
3. **Decision trace** — 12 dense rows (mission → gate). Selecting a row
   swaps the detail pane without leaving the operation.
4. **IBM BOB control plane** — the governance chain `ACTION REQUEST →
   BOB RUNTIME → BOB BROKER → BOB POLICY → ALLOW/DENY → EXECUTION`,
   with the actual persisted decision and reason (DENY reasons are the
   real recorded reasons, never fabricated).
5. **Quality Gate** — `N/7 conditions satisfied`, per-condition
   pass/fail from the persisted gate record, and the final verdict.
   The language is `REFUSE`, never `FAILED`.
6. **Governance attribution** — IBM BOB (Runtime/Broker/Policy) vs the
   RAPHAEL verification layer (Evidence/Verifier/Falsifier/Replanner/
   Quality Gate).

## Design

Dark expert console: near-black `#080A0D`, graphite panels, electric
blue `#5B7FE0`, green `#35B77A` / amber `#D7A044` / red `#D34F61`
state colours, Inter UI + JetBrains Mono for identifiers. Dense tables,
thin dividers, compact type, minimal decoration. Status is never
colour-only (always paired with a glyph and label). Desktop-first
(1440/1920); collapses to one column on narrow widths. The stale
"Findings Intelligence" mock in the Stitch project is a superseded
design artifact; the implemented screen is authoritative.

## Governance boundary

- Route + view import only `harness.api`.
- Static checks (`tests/test_m15_3_decision_trace.py::Governance`)
  assert no `execute_capability`, no Broker/Policy/Runtime/QualityGate
  imports, no `subprocess`/`socket`/`urllib`, no `GateVerdict`, no
  `write_seal` in the new sources.
- Rendering is verified read-only: the ledger record count is unchanged
  by a GET.
- A missing run returns `404 RUN_NOT_FOUND`.

## Live updates (M15.4)

The Decision Trace page is now **live**: it subscribes to
`GET /runs/{run_id}/events/stream` (SSE over the existing event
projection) and updates the pipeline, gate panel, and evidence counts in
place — no full-page refresh. It shares a single client renderer with
the live Operations Console (`docs/http-api.md` §2b/2c). The page still
renders correctly without JavaScript (server-rendered snapshot).

## Limitations

- Presentation only — no live push/streaming (no WebSocket/SSE).
- The screen is a snapshot of persisted state at render time.
- The mission/context item shows bounded, available fields; fields the
  run does not persist are shown as `—`, never invented.
