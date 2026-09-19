# Phase 2C — C1A Implementation

This document records the end-to-end C1A (`C1A_STATIC_FILE_INSPECT`)
implementation as applied on top of baseline
`dedde0d5a31209c2e131ebdf5035c7a5ae85da53`.

C1A is a first-class capability for **out-of-process** static-file
inspection through the governed provider boundary (T3MP3ST
`binary_sink_scan`). It is **not** an alias of `READ`.

## Corrections applied

1. **Authorization binding hash (CORRECTION 1).** One canonical payload
   builder (`c1a_authorization.binding_payload`) is shared by
   `create_binding` and `verify_binding`. The payload covers the complete
   authoritative identity (`run_id`, `decision_seq`, `request_seq`,
   `invocation_id`, `proof_session_id`, `lifecycle_id`, `sandbox_id`,
   `capability_id`, `provider_id`, `target`, `fixture_path`). Mutating any
   field is detected; bindings are single-use (invalidated after use) and
   replay is rejected.
2. **C1A is never READ (CORRECTION 2).** `Capability.C1A_STATIC_FILE_INSPECT`
   is distinct; `provider_runtime.validate_scope` enforces the C1A
   capability, and READ cannot masquerade as C1A (or vice versa).
3. **Canonical scope authorization (CORRECTION 3).** `c1a_scope` provides
   one component-boundary containment helper reused by the Policy and by
   QualityGate Condition E. Sibling prefixes, traversal, outside paths,
   relative ambiguity, and malformed paths all fail closed.
4. **Real provider vs test double (CORRECTION 4).** The pinned T3MP3ST
   provider is absent. `T3MP3STAdapter` remains fail-closed.
   `InertProviderDouble` is explicitly labelled test infrastructure and is
   never called "T3MP3ST". `SandboxedLauncherAdapter` runs the pinned local
   launcher and is not T3MP3ST either.
5. **Live proof (CORRECTION 5).** `scripts/c1a_live_proof.py` keeps
   `LIVE_PROOF_AUTHORIZED = False` and reports `BLOCKED` with the exact
   external blocker. No M1/M2/M5/provider-execution claim is made.

## Components

| Component | Module |
|-----------|--------|
| Capability enum | `raphael_ibm_bob/contracts.py` |
| Canonical scope | `raphael_ibm_bob/c1a_scope.py` |
| Authorization binding | `raphael_ibm_bob/c1a_authorization.py` |
| Bounded transport | `raphael_ibm_bob/c1a_transport.py` |
| Host lifecycle | `raphael_ibm_bob/c1a_lifecycle.py` |
| Provider evidence | `raphael_ibm_bob/c1a_evidence.py` |
| Independent verification | `raphael_ibm_bob/c1a_verification.py` |
| Independent falsification | `raphael_ibm_bob/c1a_falsification.py` |
| Replay/lineage | `raphael_ibm_bob/c1a_replay.py` |
| Launcher | `provider/c1a_launcher.js` |
| Launcher adapter | `raphael_ibm_bob/adapters/t3mp3st_adapter.py` |
| Live-proof gate | `scripts/c1a_live_proof.py` |
| Demo | `demos/c1a_live_hero.py` |

The Broker routes `C1A_STATIC_FILE_INSPECT` through `_execute_c1a`; every
other capability keeps the existing in-process dispatch.

## Failure semantics

- Timeout and late output never become success (`c1a_transport`).
- Provider output is untrusted evidence; it can never create
  VERIFIED/REFUTED/COMPLETE.
- An unavailable provider yields `INCONCLUSIVE` verification and the gate
  REFUSEs.
- Orphan state is preserved: teardown only advances when the host observed
  process exit (and no late output).

## Status

- Unit/integration tests for the above are in `tests/test_c1a_*.py`,
  `tests/test_isolation_probes.py`, `tests/test_quality_gate_scope.py`,
  `tests/test_search_hardening.py`, `tests/test_run_test_env_scrub.py`,
  `tests/test_live_proof_gate.py`.
- The inert-provider end-to-end path reaches `Gate: COMPLETE` through the
  real QualityGate.
- Live proof: **BLOCKED** (real T3MP3ST provider and substrate absent).
