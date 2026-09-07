# `raphael_bob` — IBM BOB MVP seam package (M1)

This package establishes the **migration boundary** between the existing
Raphael v2.1.1 implementation and the IBM BOB Hackathon Master Roadmap v1.2
target. It is *not* an implementation of the target control loop. That work
begins at M2.

## What is in M1

```
raphael_bob/
├── __init__.py          # re-exports contracts + seams
├── contracts.py         # dataclasses/enums that cross every seam boundary
├── seams.py             # Protocol interfaces for Runtime/Broker/Policy/...
├── adapters/
│   ├── __init__.py      # re-exports the AdapterSpec index
│   └── legacy.py        # legacy-module-to-seam selection index
└── README.md            # this file
```

## Conceptual target control loop

The protocols in `seams.py` represent this flow:

```
Mission -> Planner -> Plan A
              -> Runtime -> Broker -> Policy -> Capability
              -> EvidenceLedger (append)
              -> Verifier -> Finding
              -> Falsifier
              -> FocusedContext -> Replanner -> Plan B
              -> QualityGate -> COMPLETE / REFUSE
```

The protocols are deliberately small. M2..M6 will introduce concrete
implementations and JSONL evidence writers behind them.

## Capability allow-list

The MVP restricts itself to exactly five capabilities. Anything else is
OUT OF SCOPE for the BOB MVP and must be requested through a legacy
adapter explicitly marked `ISOLATE`.

| Capability | Use |
|---|---|
| `READ` | read a file under mission scope |
| `LIST` | list a directory under mission scope |
| `SEARCH` | search a corpus under mission scope |
| `WRITE` | write a file under mission scope |
| `RUN_TEST` | run a single named test under mission scope |

## Decision / Finding / Gate enums

| Enum | Values |
|---|---|
| `Decision` | `ALLOW`, `DENY` |
| `FindingState` | `UNVERIFIED`, `VERIFIED`, `REFUTED`, `SUPERSEDED` |
| `GateVerdict` | `COMPLETE`, `REFUSE` |

Structural rule (enforced at M4/M5): a Finding cannot transition directly
from `UNVERIFIED` to `SUPERSEDED`.

## ActionRequest provenance fields

| Field | Required | Purpose |
|---|---|---|
| `sequence` | yes | dense logical sequence number in the run |
| `requester` | yes | identifier of the originator |
| `capability` | yes | the Capability enum |
| `target` | yes | canonical target identifier |
| `purpose` | yes | free-text causal reference |
| `plan_id` | optional | links to the plan this action belongs to |
| `finding_id` | optional | links to the finding this action causally references |

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | dataclass / enum / Protocol defined and importable |
| `PHYSICALLY VERIFIED` | exercised by `tests/test_seam_*.py` |
| `NOT IMPLEMENTED` | concrete implementation; deferred |
| `UNKNOWN` | insufficient evidence |
| `ISOLATE` | legacy module kept reachable but not called from the seam |
| `REPLACE` | no legacy code reused; new module will be written |
| `ADAPT` | legacy module reused with contract changes |
| `REUSE` | legacy module used unmodified (none at M1) |

## Legacy module selection

See `raphael_bob/adapters/legacy.py` for the full `AdapterSpec` index.
Summary at M1:

| Seam | Module | Action |
|---|---|---|
| Broker | `src/orchestrator/brain/capability_broker.py` | ADAPT |
| Broker | `src/orchestrator/hardening/action_receipt.py` | ADAPT |
| Policy | `src/orchestrator/brain/scope_parser.py` | ADAPT |
| Policy | `src/orchestrator/brain/rate_limiter.py` | ADAPT |
| Evidence | `src/orchestrator/brain/evidence.py` | ADAPT |
| Evidence | `src/orchestrator/brain/trust.py` | ISOLATE |
| Falsifier | `src/orchestrator/brain/contradiction.py` | ADAPT |
| Verifier | `src/raphael/verifier/core.py` | ADAPT |
| Planner | `src/orchestrator/brain/action.py` | ADAPT |
| Planner | `src/orchestrator/brain/world.py` | ADAPT |
| Planner | `src/raphael/cognitive/planner.py` | REPLACE |
| Replanner | (none) | REPLACE |
| QualityGate | (none) | REPLACE |
| Runtime | (none) | REPLACE |
| Runner | `src/raphael/main.py` | ISOLATE |

## Tests

```bash
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts -v
```

Stdlib-only — does not depend on pytest. Run with the system Python 3.14.

## What is explicitly NOT in M1

- No concrete Runtime implementation.
- No concrete Broker implementation.
- No concrete Policy grammar.
- No JSONL evidence writer.
- No Verifier / Falsifier / Replanner implementations.
- No QualityGate.
- No Planner / Runner.
- No hero fixture, no baseline, no metrics, no PROVENANCE.md.
- No TEST-01..13 (those land at M9).
- No BOB integration.
- No claim of correctness for any component.

These are reserved for M2..M10.