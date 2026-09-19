# C1A Release Gate

The C1A release gate separates what is actually verified from what remains
blocked. No claim is made beyond observed evidence.

## Verified on this tree

- C1A is a first-class capability and never aliases `READ`.
- Authorization binding covers the full identity and is single-use; all
  field mutations, replays, and foreign identities are rejected.
- Scope authorization and QualityGate Condition E share one canonical
  component-boundary containment helper; sibling prefixes, traversal,
  outside paths, relative ambiguity, and malformed paths fail closed.
- Bounded transport: timeout and late output never become success;
  truncation is recorded.
- The pinned launcher emits a closed-schema receipt; a digest mismatch
  fails closed.
- Provider output is untrusted evidence and cannot create
  VERIFIED/REFUTED/COMPLETE.
- The inert-provider end-to-end path reaches `Gate: COMPLETE` through the
  real QualityGate.
- `LIVE_PROOF_AUTHORIZED = False`.

## Blocked (external dependency)

- Real T3MP3ST provider execution.
- M1/M2/M5 live verification and the production isolation substrate.
- `scripts/c1a_live_proof.py` returns `BLOCKED` until the provider is
  provisioned, vetted, and explicitly authorized.

## Release decision rule

The C1A **implementation** may be released as an inert-provider-verified
package while the **live proof** remains BLOCKED. Do not describe the live
proof as passing, and do not mark M1/M2/M5 verified, until the gate reports
`READY` on a real run.
