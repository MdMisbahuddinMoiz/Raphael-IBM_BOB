# C1A Runbook

All commands assume the repository root as the working directory.

## Run the C1A test suites

```bash
PYTHONPATH=. python3 -m unittest \
  tests.test_c1a_authorization tests.test_c1a_identity \
  tests.test_c1a_transport tests.test_c1a_timeout \
  tests.test_c1a_launcher_contract tests.test_c1a_receipt \
  tests.test_c1a_lifecycle tests.test_c1a_evidence \
  tests.test_c1a_verification tests.test_c1a_falsification \
  tests.test_c1a_replay tests.test_c1a_gate \
  tests.test_c1a_end_to_end tests.test_isolation_probes \
  tests.test_quality_gate_scope tests.test_search_hardening \
  tests.test_run_test_env_scrub tests.test_live_proof_gate
```

## Run the end-to-end demo (inert provider)

```bash
PYTHONPATH=. python3 demos/c1a_live_hero.py
```

Expected: an unauthorized C1A is DENYed; the governed C1A path produces
untrusted provider evidence; the QualityGate returns `COMPLETE`; the demo
prints `Live proof: BLOCKED`.

## Run the live-proof gate

```bash
PYTHONPATH=. python3 scripts/c1a_live_proof.py
echo $?   # 2 = BLOCKED
```

Expected blockers: `live_proof_authorized` (false) and
`t3mp3st_provider_present` (absent). The gate never claims M1/M2/M5.

## Real provider (external dependency, not present)

The real T3MP3ST provider is an external dependency. When it is provisioned
and vetted, the live proof additionally requires:

1. The pinned provider checkout at the declared `PROVIDER_PIN`.
2. The pinned fixture at `FIXTURE_SHA256`.
3. The network-denied `bwrap` + cgroup v2 + curated seccomp substrate.
4. Explicit operator authorization (set `LIVE_PROOF_AUTHORIZED = True` in
   `scripts/c1a_live_proof.py`) — do NOT flip without authorization.

Until then the correct status is **BLOCKED**.
