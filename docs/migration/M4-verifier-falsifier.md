# M4 — Verifier + Falsifier

This document captures the M4 implementation in `raphael_bob/finding.py`,
`raphael_bob/verifier.py`, and `raphael_bob/falsifier.py`.

## Status language

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | class / dataclass defined and importable |
| `PHYSICALLY VERIFIED` | exercised by tests in `tests/test_m4_*.py` and `tests/test_seam_*.py` |
| `NOT IMPLEMENTED` | reserved for downstream milestones |
| `UNKNOWN` | insufficient evidence |

## Module map (M4)

```
raphael_bob/
├── __init__.py            # re-exports M4 symbols
├── contracts.py           # Finding / FindingState dataclasses
├── seams.py               # Verifier / Falsifier Protocols
├── evidence_ledger.py     # extended: FindingRecord + finding_id linkage
├── finding.py             # NEW — FindingStore (lifecycle-aware)
├── verifier.py            # NEW — Verifier (broker-mediated retest)
├── falsifier.py           # NEW — Falsifier (broker-mediated challenge)
├── broker.py              # M2..M3 (unchanged at M4)
└── adapters/legacy.py     # Verifier / Falsifier specs marked IMPLEMENTED at M4
```

## M3 provenance gap fix

The brief §3 required a durable `finding_id -> evidence` linkage. M4 closes
the gap by:

1. Adding `finding_id: Optional[str]` to `EvidenceRecord`. The Verifier and
   Falsifier set it on every evidence receipt they emit.
2. Adding a new `FindingRecord` record kind for finding-lifecycle
   transitions. Stored fields: `finding_id`, `state`, `prev_state`,
   `summary`, `target`, `evidence_seqs`, `digest`.
3. Adding `EvidenceLedger.records_for_finding(finding_id)` which returns every
   record (FindingRecord + EvidenceRecord) carrying that `finding_id`, sorted
   by ledger sequence.

## Finding lifecycle

```
UNVERIFIED  ─retest─┐         ┌──supersedes──►  SUPERSEDED
    │                ▼         ▲
    │             VERIFIED ───┤
    │                │         ▲
    └─counter──►  REFUTED ────┘
```

`FindingStore.transition(finding_id, new_state, *, evidence_seqs=...)` is the
sole authority. Invalid transitions raise `InvalidTransitionError`. The
brief's structural rule (UNVERIFIED cannot transition directly to
SUPERSEDED) is enforced: UNVERIFIED may transition only to VERIFIED or
REFUTED.

## Verifier

`raphael_bob.verifier.Verifier.verify(finding, retest, mission)`:

1. Builds a broker-mediated `ActionRequest` carrying `finding_id`.
2. Submits via `BOBRuntime` (Runtime -> Broker -> Policy).
3. On DENY: persists a `verifier` evidence record (kind="retest", allowed=false);
   finding remains UNVERIFIED.
4. On ALLOW: examines the result payload against `RetestSpec.expected_substring`.
5. On match: persists a second `verifier` evidence record (kind="observation");
   transitions UNVERIFIED -> VERIFIED.
6. On mismatch: leaves UNVERIFIED; the result and observation evidence are
   still persisted.

`RetestSpec.capability` and `RetestSpec.target` determine what the retest does.
The default for the authkit-style fixture: READ a target file expecting a
substring.

## Falsifier

`raphael_bob.falsifier.Falsifier.challenge(finding, spec, mission)`:

1. Builds a broker-mediated `ActionRequest` carrying `finding_id`.
2. Submits via `BOBRuntime`.
3. Persists a `falsifier` evidence record (kind="challenge") regardless of
   outcome so the challenge attempt is always part of the durable trail.
4. On DENY: leaves the finding as-is (the challenge itself was denied).
5. On ALLOW: examines the result payload using `spec.predicate` first,
   then `spec.forbidden_substring`.
6. On counter-example observed: persists a second `falsifier` evidence record
   (kind="counter-example"); transitions VERIFIED -> REFUTED.
7. On no counter-example: leaves VERIFIED.

The counter-example is observed in actual evidence — not hard-coded.

## Verifier-security proof

`tests/test_m4_verifier_falsifier.py` includes:

- `VerifierCannotBypassPolicy.test_retest_outside_workspace_is_denied`
- `DeniedVerifierNoSideEffect.test_denied_retest_does_not_create_files_or_artifacts`
- `DeniedVerifierNoSideEffect.test_denied_retest_persists_policy_receipt_not_execution`

These physically demonstrate that the Verifier cannot bypass the
Broker/Policy boundary and that a denied retest leaves zero side effects
(no filesystem change, no result record, no execution evidence).

## Unverified-cannot-masquerade proof

`tests/test_m4_verifier_falsifier.py / UnverifiedCannotMasquerade`:

- `Verifier` leaves UNVERIFIED on DENY (not VERIFIED).
- `Falsifier` does NOT transition UNVERIFIED findings.
- `FindingStore.transition(UNVERIFIED -> SUPERSEDED)` raises `InvalidTransitionError`.

## Reconstructible provenance

`EvidenceLedger.records_for_finding(finding_id)` returns every record carrying
that finding_id (FindingRecord + EvidenceRecord) sorted by ledger sequence.
Tests assert that this reconstruction includes both FindingRecord rows
(transitions) and EvidenceRecord rows (retest, observation, challenge,
counter-example).

## Tests executed

```
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier
```

| Suite | Tests |
|---|---|
| test_seam_contracts (M1..M4 anti-claim updates) | 31 |
| test_m2_boundary (M2 regression) | 21 |
| test_m3_evidence (M3 regression) | 22 |
| test_m4_verifier_falsifier (M4 new) | 17 |
| **total** | **91** |

## Tests passed/failed

```
Ran 91 tests in 0.141s
OK
```

All pass; 0 failures.

## Legacy components reused/adapted

| Seam | Legacy module | M4 disposition |
|---|---|---|
| Verifier | `src/raphael/verifier/core.py` (VerificationLoop, exploit-canary) | ADAPT conceptually; **NOT imported**. M4 ships a fresh `Verifier` class with broker-mediated behavioral retest. |
| Falsifier | `src/orchestrator/brain/contradiction.py` (ContradictionManager) | ADAPT conceptually; **NOT imported**. M4 ships a fresh `Falsifier` class with broker-mediated active challenge. |
| Evidence | `src/orchestrator/brain/evidence.py` (Evidence / EvidenceGraph) | ADAPT conceptually. M3+M4 reuse the digest pattern but emit JSONL records (not in-memory DAG). |
| All other seams | unchanged from M3 | m4_status annotated as "M4: NOT IMPLEMENTED" for reserved seams. |

## Remaining gaps

- No automatic challenge-on-VERIFIED orchestration; the caller must invoke
  the Falsifier after the Verifier transitions a finding to VERIFIED. (M5
  may introduce a Runner that wires this together.)
- The Replanner (M5) must consume a `Finding` whose `state` is REFUTED
  plus its `evidence_for(...)` chain to produce a Plan B.
- The QualityGate (M6) must check that no UNVERIFIED findings remain and
  that all VERIFIED findings have a corresponding Falsifier challenge record.

## M5 readiness

M5 (Replanner + Runner) needs:
1. The ability to read REFUTED findings from `FindingStore`.
2. The ability to build a `FocusedContext` from a REFUTED finding's
   `evidence_for(...)` chain.
3. The Replanner MUST itself go through the Broker when emitting its
   follow-up retest (so it cannot bypass Policy).
4. The Runner must drive Plan A -> Verifier -> (Falsifier on conflict) ->
   Replanner -> Verifier -> Quality Gate.

The M4 evidence backbone supports all of the above:
`FindingStore.evidence_for(...)` returns the chronological record list;
the Replanner's follow-up retest can be a fresh `Verifier.verify(...)`
call wired into the same ledger.