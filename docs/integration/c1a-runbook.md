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
  tests.test_run_test_env_scrub tests.test_live_proof_gate \
  tests.test_t3mp3st_integration
```

`tests.test_t3mp3st_integration` runs the REAL pinned T3MP3ST provider when
a compiled checkout is present (default `/home/moiz/audit-repos/T3MP3ST/dist`,
override with `T3MP3ST_PROVIDER_DIST`). Without it the module SKIPs — it is
never replaced by a fabricated fallback.

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

The gate reports `provider_status` from the REAL checkout state. When the
compiled provider is present it is `AVAILABLE`; the status is still
`BLOCKED` while `live_proof_authorized` is false. The gate never claims
M1/M2/M5.

## Real T3MP3ST provider

Canonical execution path (only):

```
RAPHAEL -> bwrap -> RAPHAEL bridge -> binarySinkScanTool.handler()
```

The bridge (`provider/t3mp3st_bridge.js`) imports ONLY the compiled
`dist/arsenal/binary.js` direct handler, avoiding the full CLI/arsenal
dispatcher and its network-capable import chain.

### Provisioning

1. Clone the pinned provider at `PROVIDER_PIN`
   (`29824d5625ede419ac8cdae418c8f4c72c6270f7`).
2. `npm ci && npm run build` → produces `dist/`.
3. Node must be >= 22.19.0 (T3MP3ST `engines`).
4. Point RAPHAEL at it: `T3MP3ST_PROVIDER_DIST=/path/to/T3MP3ST/dist`.

The provider source is mounted READ-ONLY and is never modified.

### Sandbox contract

The bwrap argv (`isolation_substrate.build_t3mp3st_bwrap_argv`) mounts, all
read-only: each Node runtime closure path individually, `<dist>` at
`/t3mp3st/dist`, the bridge at `/provider/t3mp3st_bridge.js`, and the exact
fixture file at `/fixture`. It unsets the network namespace
(`--unshare-net`), unshares user/pid/ipc/uts, drops all capabilities, runs
as uid/gid 65534, and applies `--remount-ro /` so the sandbox has NO
writable filesystem. `T3MP3ST_SOURCE_ROOT` is fixed to `/fixture`.

### Path validation

T3MP3ST's own `approvedLocalPath()` is exercised by the integration tests
for root, valid child, sibling prefix, traversal, outside path, and
`fixture_evil`; the last four are rejected by the real provider.

### Authority boundary

The bridge emits only `success`/`output`/`error`/`tool`; T3MP3ST's
`findings` array (severity/cwe/title/details) is deliberately excluded.
RAPHAEL independently rejects any authority field through its closed
schema, and provider output remains UNTRUSTED evidence that can never
create VERIFIED or COMPLETE.

### Live proof

Live proof requires explicit operator authorization
(`LIVE_PROOF_AUTHORIZED = True` in `scripts/c1a_live_proof.py`) — do NOT
flip without authorization. Until then the correct status is **BLOCKED**.
