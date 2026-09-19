# C1A Evidence Contract

Provider output is **evidence**, never authority. This contract is
enforced in code by `raphael_ibm_bob.provider_runtime` and
`raphael_ibm_bob.c1a_evidence`.

## Closed provider schema

A provider receipt may contain only these top-level keys:

```
results, artifacts, provider_message, operation_id, result_hash, truncated
```

Any other key is rejected. Any **authority** key is rejected by normalized
name (case/separator/Unicode folded), including but not limited to:

```
verifyGate, verdict, conclusion, validated, verified, refuted,
severity, assertedSeverity, risk, priority, impact, cvss,
confidence, confidence_score, score, probability, certainty, trust,
authorized, approved, approval, permission, policy, gate_pass, gatePass,
complete, COMPLETE, done, recommendation(s), next_steps, directives
```

Result items accept only the scalar keys `path`, `kind`, `offset`, `size`,
`hash`; nested objects/arrays are rejected. Every result `path` must equal
the exact fixture literal.

## Untrusted marker

Every provider-derived payload written to the ledger carries
`provider_untrusted: True` and is appended with `producer="provider"`.
Provider evidence can never imply a verified finding or a completed
mission (`c1a_evidence.evidence_implies_verified/complete` return False).

## Evidence kinds

| Producer | Kind / payload | Meaning |
|----------|----------------|---------|
| `provider` | `kind="provider-result"` | Bounded provider outcome (untrusted) |
| `verifier` | `kind="c1a-retest"` | Independent reproduction attempt |
| `falsifier` | `kind="c1a-challenge"` | Independent contradiction attempt |
| `falsifier` | `kind="c1a-counterexample"` | Result-hash contradiction found |

## Authority boundary

- The provider boundary produces `ProviderResult` only (no gate/verdict/
  authorization).
- The Verifier transitions `UNVERIFIED -> VERIFIED` only when an
  independent reproduction succeeds AND its provider `result_hash` matches
  the expected hash.
- The Falsifier transitions `VERIFIED -> REFUTED` only on a real
  contradiction (two differing result hashes).
- Only the QualityGate can return `COMPLETE`.

## Real T3MP3ST provider

When the compiled pinned T3MP3ST checkout is present, the RAPHAEL bridge
(`provider/t3mp3st_bridge.js`) runs the real `binarySinkScanTool.handler()`
in the sandbox. The bridge emits only `success`/`output`/`error`/`tool`;
T3MP3ST's `findings` array (`severity`/`cwe`/`title`/`details`) is excluded
before it can reach RAPHAEL, and the closed schema rejects any authority
field independently. `result_hash` is a deterministic SHA-256 of the
bounded output — UNTRUSTED metadata used for independent-reproduction
comparison, never a verdict. See `docs/integration/t3mp3st-integration.md`.
