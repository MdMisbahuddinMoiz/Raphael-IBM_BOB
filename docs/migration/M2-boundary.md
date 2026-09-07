# M2 — Controlled Execution Boundary

This document captures the M2 implementation in `raphael_bob/`.

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | dataclass / enum / Protocol / class defined and importable |
| `PHYSICALLY VERIFIED` | exercised by tests in `tests/test_seam_*.py` and `tests/test_m2_*.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M2)

```
raphael_bob/
├── __init__.py            # public API
├── contracts.py           # M1 — frozen dataclasses + enums
├── seams.py               # M1 — Protocol interfaces
├── workspace.py           # M2 — Workspace with realpath containment
├── policy.py              # M2 — BOBPolicy (fail-closed)
├── capabilities.py        # M2 — READ/LIST/SEARCH/WRITE/RUN_TEST
├── broker.py              # M2 — BOBBroker (mediation, sequencing, audit)
├── runtime.py             # M2 — BOBRuntime (agent-facing boundary)
└── adapters/
    ├── __init__.py
    └── legacy.py          # AdapterSpec index (M2 status annotated)
```

## Execution path

```
ActionRequest
   ↓
BOBRuntime.submit
   ↓
BOBBroker.submit
   ↓
BOBPolicy.consult          ← always invoked
   ↓
ALLOW  → execute_capability → ExecutionResult
DENY   → PolicyDecision (no capability invocation)
```

The Broker is the **only** component that calls `execute_capability`. Verified by `tests.test_m2_boundary.BypassIsBlocked`.

## Capabilities (MVP)

| Capability | Implementation | Network | Process |
|---|---|---|---|
| READ | `Path.read_text` | NO | NO |
| LIST | `Path.iterdir` | NO | NO |
| SEARCH | `re` over `Path.rglob` | NO | NO |
| WRITE | `Path.write_text` | NO | NO |
| RUN_TEST | `subprocess.run(['python3', '-m', 'unittest', module])` | NO | YES (scoped) |

No other capability is reachable. A `Capability.NETWORK` enum value cannot exist (Python enum subclass restriction); a string masquerading as a Capability is rejected by `BOBPolicy.consult`.

## Policy grammar (BOBPolicy)

```
ALLOW iff:
    capability in {READ, LIST, SEARCH, WRITE, RUN_TEST}
    and target resolves inside the workspace
    and (mission.scope is empty or mission.scope in target)
    and capability-specific path invariant holds

DENY otherwise, with reason in:
    capability-not-allowed:<cap>
    target-empty-or-invalid
    target-outside-workspace
    scope-mismatch
    read-target-missing
    read-target-not-file
    list-target-missing
    list-target-not-directory
    search-target-missing
    search-target-not-directory
    write-target-is-directory
    write-parent-missing
    run_test-target-missing
    run_test-target-not-file
    run_test-name-pattern
```

Policy is **fail-closed**. Every check is required; any missing/failed check returns DENY.

## Legacy modules adapted

Per `raphael_bob/adapters/legacy.py` M2-status field:

| Seam | Legacy module | M2 status |
|---|---|---|
| Broker | `src/orchestrator/brain/capability_broker.py` | IMPLEMENTED (BOBBroker, behavior rebuilt from contract; legacy offensive-RoE code is ISOLATE) |
| Broker | `src/orchestrator/hardening/action_receipt.py` | NOT IMPLEMENTED (BOB emits its own EvidenceReceipt) |
| Policy | `src/orchestrator/brain/scope_parser.py` | IMPLEMENTED (BOBPolicy preserves fail-closed semantics) |
| Policy | `src/orchestrator/brain/rate_limiter.py` | NOT IMPLEMENTED (no MVP rate limit) |
| Evidence | `src/orchestrator/brain/evidence.py` | NOT IMPLEMENTED (M3 owns JSONL) |
| Evidence | `src/orchestrator/brain/trust.py` | ISOLATE |
| Runtime | `(none)` | IMPLEMENTED (BOBRuntime) |
| Runner | `src/raphael/main.py` | ISOLATE (Wave 1 cognitive loop) |
| Replanner | `(none)` | NOT IMPLEMENTED (M5) |
| QualityGate | `(none)` | NOT IMPLEMENTED (M6) |
| Falsifier | `src/orchestrator/brain/contradiction.py` | NOT IMPLEMENTED (M4) |
| Verifier | `src/raphael/verifier/core.py` | NOT IMPLEMENTED (M4) |
| Planner | `src/orchestrator/brain/action.py` | NOT IMPLEMENTED (M5) |
| Planner | `src/orchestrator/brain/world.py` | NOT IMPLEMENTED (M5) |
| Planner | `src/raphael/cognitive/planner.py` | NOT IMPLEMENTED (M5) |

## Remaining limitations at M2

- Audit log is in-memory; JSONL append-only EvidenceLedger is M3.
- No retry policy at the Runtime.
- No scheduler; Runtime is single-request synchronous.
- No rate limiting (MVP does not require it).
- No behavior probe or quality gate yet.
- No replanner yet.
- No verifier / falsifier yet.

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary
```

| Suite | Tests | Result |
|---|---|---|
| test_seam_contracts (M1 + M2 anti-claim updates) | 32 | OK |
| test_m2_boundary (M2 new) | 21 | OK |
| **total** | **53** | **OK** |

The M2 suite covers all 9 §9 minimum proofs plus the §10 boundary test, plus extra LIST/SEARCH/RUN_TEST coverage for capability completeness.