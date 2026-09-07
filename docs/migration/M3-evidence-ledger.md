# M3 — Evidence Ledger + Finding Provenance

This document captures the M3 implementation in `raphael_bob/evidence_ledger.py`.

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | dataclass / enum / Protocol / class defined and importable |
| `PHYSICALLY VERIFIED` | exercised by tests in `tests/test_seam_*.py` and `tests/test_m3_*.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M3)

```
raphael_bob/
├── __init__.py            # public API
├── contracts.py           # M1 — frozen dataclasses + enums
├── seams.py               # M1 — Protocol interfaces
├── workspace.py           # M2 — Workspace with realpath containment
├── policy.py              # M2 — BOBPolicy (fail-closed)
├── capabilities.py        # M2 — READ/LIST/SEARCH/WRITE/RUN_TEST
├── broker.py              # M2..M3 — BOBBroker (mediation + ledger wiring)
├── runtime.py             # M2..M3 — BOBRuntime (agent-facing boundary)
├── evidence_ledger.py     # M3 — EvidenceLedger (JSONL append-only)
└── adapters/
    ├── __init__.py
    └── legacy.py          # AdapterSpec index (M3 status annotated)
```

## Record flow

Every Broker-mediated action persists a canonical chain to the JSONL ledger:

```
ActionRequest
    ↓
RequestRecord            (kind="request",  seq=N,   requester, capability, target, ...)
    ↓
PolicyDecision
    ↓
DecisionRecord           (kind="decision", seq=N+1, request_seq, decision, reason, ...)
    ↓
PolicyEvidenceRecord     (kind="evidence", producer="policy",   request_seq, decision_seq)
    ↓
[DENY branch ends here]
[ALLOW branch continues]
    ↓
ExecutionResult
    ↓
ResultRecord             (kind="result",   seq=N+3, request_seq, decision_seq, success, artifact_ref)
    ↓
ExecutionEvidenceRecord  (kind="evidence", producer="execution", request_seq, decision_seq, result_seq)
```

DENY persists `request + decision + policy-evidence` (3 records) and **no** result or execution-evidence record. This is the canonical proof of `Failure Class 1` ("RAPHAEL does not pretend an unauthorized action happened").

## Record format

Every record is a single line of canonical JSON (sorted keys, no whitespace), terminated with `\n`. The file handle is opened in append-binary mode (`'ab'`) and `fsync`'d after every append. Records parse deterministically with `json.loads`.

Example record (one line):

```json
{"capability":"read","finding_id":null,"kind":"request","plan_id":null,"purpose":"p","requester":"agent","seq":1,"target":"src/hello.txt","ts":1788796148776929717}
```

## Sequence semantics

- Each `EvidenceLedger` owns a per-run dense sequence counter.
- Sequence numbers are dense integers starting at 1 and strictly increasing.
- The counter is held by the `LedgerWriter`; the reader never mutates state.
- Wall-clock timestamps are attached as additional metadata but are NOT the primary ordering mechanism.
- The clock is injectable so tests can pin time deterministically (`EvidenceLedger(run_dir, clock=fake_clock)`).

## Evidence identifiers

- `evidence_id` is a deterministic SHA-256 digest of a canonical payload.
- Format: `<prefix>-<16 hex chars>` where prefix is `P` (policy), `X` (execution), or `R` (result).
- Identical payloads produce identical `evidence_id`s.
- Key order does not affect the digest (canonical JSON uses `sort_keys=True`).

## Append-only invariant

- Public API has only `append_*` methods. No `update`, `delete`, `rewrite`, `truncate`, `pop`, or `remove`.
- File handle is opened in `'ab'` mode; every append is followed by `flush()` + `os.fsync()`.
- Tests prove that bytes present before a new append remain verbatim at the head of the file after the append.
- A reader that encounters a corrupt line raises `ValueError` (fail-closed); the ledger is still readable up to the first corrupt line.

## Failure modes

| Failure | Behaviour |
|---|---|
| Partial write (truncated tail) | Reader raises `ValueError`; prior records are unaffected |
| Corrupt record | Reader raises `ValueError`; no silent acceptance |
| Sequence collision | Lock-protected counter; concurrent appends produce strictly-increasing seqs |
| Duplicate `evidence_id` | Permitted as distinct appends; each gets its own seq number |
| Update attempt | No public method exists; structurally impossible |
| Delete attempt | No public method exists; structurally impossible |

## Legacy evidence adapter

`src/orchestrator/brain/evidence.py` was the M0/M1 ADAPT candidate. The BOB MVP reuses the **concept** of frozen-dataclass evidence + SHA-256 digest identifiers but does NOT import the legacy module. The legacy `EvidenceGraph` (with `derived_from / supports / contradicts` semantic relations) is replaced by flat causal links (`request_seq`, `decision_seq`, `result_seq`) inside each JSONL record. Legacy behaviour remains ISOLATE per `raphael_bob/adapters/legacy.py`.

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence
```

| Suite | Tests | Result |
|---|---|---|
| test_seam_contracts (M1 + M2 + M3 anti-claim updates) | 33 | OK |
| test_m2_boundary (M2 regression) | 21 | OK |
| test_m3_evidence (M3 new) | 22 | OK |
| **total** | **76** | **OK** |

The M3 suite covers:
1. Allowed action creates durable ledger evidence
2. Denied action creates durable denial evidence
3. request/result linkage is correct
4. evidence IDs are populated
5. sequence ordering is deterministic (with injected clock)
6. JSONL records are parseable
7. append-only behaviour is enforced (no public update/delete; corrupt tail detected)
8. prior records remain unchanged after new appends (digest stable)
9. ledger can be reopened and read
10. no execution record exists for a denied capability (and no artifact file)
11. failure modes (sequence collision under threads, corrupt record, partial write, duplicate append, public-API guard)
12. digest determinism
13. zero network (no socket/urllib/httpx/requests/aiohttp imports)

## Remaining UNKNOWN

- Whether the Verifier (M4) will read the ledger directly or use a higher-level API; both are possible.
- Whether the Replanner (M5) will index the ledger by causal link or scan linearly; the per-record `request_seq` indexing leaves both open.
- Whether the QualityGate (M6) needs an aggregation API (e.g. `by_kind`) on top of the raw reader; the M3 surface includes `records_by_kind` for this.

## M4 readiness

M4 (Verifier + Falsifier) needs:
1. The ability to read prior evidence for a Finding id.
2. The ability to write new EvidenceRecord rows that link to existing `request_seq`/`decision_seq` records.
3. The Verifier MUST itself go through the Broker (so it cannot bypass Policy).
4. The Falsifier MUST emit a `Finding` whose state is REFUTED when it finds a counter-example.

The M3 ledger supports (1) and (2) via `LedgerReader.by_request_seq` and `EvidenceLedger.append_evidence`. (3) and (4) are M4 work.