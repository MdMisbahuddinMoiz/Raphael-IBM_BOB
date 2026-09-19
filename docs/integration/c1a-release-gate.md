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

## Real T3MP3ST integration (provider execution verified locally)

When the compiled pinned checkout is present, the canonical path

```
RAPHAEL -> bwrap -> RAPHAEL bridge -> binarySinkScanTool.handler()
```

executes the REAL provider in the sandbox. Observed:

- `provider_execution = VERIFIED` (local, pinned revision
  `29824d5625ede419ac8cdae418c8f4c72c6270f7`).
- The real `approvedLocalPath()` accepts the root/valid child and rejects
  sibling prefix, traversal, outside path, and `fixture_evil`.
- `--unshare-net` denies network; `--remount-ro /` leaves no writable
  filesystem (the fixture and root are read-only).
- The bridge excludes T3MP3ST's `findings` (severity/cwe/title/details);
  RAPHAEL's closed schema independently rejects authority fields.
- Node `v22.22.1` meets T3MP3ST's `>=22.19.0`.

## Still blocked / not claimed

- `live_proof_authorized = FALSE` (unchanged).
- M1 / M2 / M5 are **NOT VERIFIED** — no kernel-observed M5 teardown probe
  or production seccomp policy has been run. `seccomp_status` remains
  `NOT_EXECUTED`.
- The live proof is not marked successful. `scripts/c1a_live_proof.py`
  returns `BLOCKED` while unauthorized.

## Release decision rule

The C1A implementation may be described as **provider-execution verified**
(real T3MP3ST ran in the sandbox) while the **live proof** remains BLOCKED
and M1/M2/M5 remain NOT VERIFIED. Do not mark the live proof as passing, and
do not mark M1/M2/M5 verified, until the corresponding probes pass and the
operator explicitly authorizes the live proof.
