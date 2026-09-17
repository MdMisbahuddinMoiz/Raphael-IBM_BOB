# Phase 2C — Provisioning & Isolation Preparation

Preparation only. **No provider executed. No live proof. M1/M2/M5 remain OPEN.**
This document records what exists, what is missing, and the lifecycle design for
the eventual first C1A proof. It does not provision anything.

## 1. Provider pin verification (T3MP3ST)

| item | value |
|---|---|
| clone | `/home/moiz/audit-repos/T3MP3ST` (remote `elder-plinius/T3MP3ST`) |
| pinned SHA | `29824d5625ede419ac8cdae418c8f4c72c6270f7` |
| HEAD | `29824d5625ede419ac8cdae418c8f4c72c6270f7` → **PIN MATCH** |
| working tree | **CLEAN** (0 changes) |
| `binary_sink_scan` | `src/arsenal/binary.ts:66` (`approvedLocalPath` at `:75`) |
| Arsenal `ToolExecution` | `src/arsenal/index.ts:197` |
| `getExecutions()` | `src/arsenal/index.ts:484` |
| scope helper | `src/arsenal/local-file-scope.ts` |
| deps | `package-lock.json` present; **`node_modules` ABSENT** |
| node/npm | node `v22.22.1`, npm `9.2.0` |

**Provisioning readiness: PARTIAL.** Source pin verified and unmodified. Running
the provider requires installing dependencies (`npm ci`), which needs
network/package-install authorization. **Per instruction, this was NOT done.**

## 2. Isolation substrate availability (detected, not provisioned)

| control | status | evidence |
|---|---|---|
| Docker | UNAVAILABLE | not installed |
| Podman / nerdctl / containerd / runc / crun | UNAVAILABLE | not installed |
| `unshare` | AVAILABLE | util-linux present |
| `bwrap` (bubblewrap) | AVAILABLE | present |
| `setpriv`, `capsh`, `nsenter`, `chroot`, `systemd-run` | AVAILABLE | present |
| user namespaces | AVAILABLE | `max_user_namespaces=31171`; `unshare --user --map-root-user --net` → `USERNET_NS_OK` |
| network namespace | AVAILABLE (primitives) | userns+netns functional test passed |
| cgroup v2 | AVAILABLE | `/sys/fs/cgroup` (controllers) |
| seccomp | AVAILABLE (kernel) | `actions_avail: kill_process kill_thread trap errno user_notif trace log allow`; current proc `Seccomp: 0` |
| tmpfs / overlay | AVAILABLE | `/proc/filesystems` |
| chroot | AVAILABLE | note: root-privileged |
| resource limits (ulimit/cgroup) | AVAILABLE | cgroup v2 |
| current privileges | uid 1000, groups incl. `sudo` | NOT privileged by default |

**Interpretation.** No container runtime is installed, so isolation must be built
from **user namespaces + `bwrap` + `tmpfs` + `setpriv`/`capsh` + cgroup v2**
— a viable but *unprovisioned and unverified* path. None of these are marked
`READY` for M1/M2 until the actual proof environment demonstrates the boundary.
M5 requires externally observed process reaping, which does not exist yet.

## 3. Fresh dedicated provider-instance lifecycle (design)

The B4 Option-B proof requires a dedicated, single-session provider instance with
no shared historical execution records. Designed lifecycle (NOT implemented):

```
CREATE instance            (fresh process/namespace; no history)
  → verify identity        (pin SHA + module digest)
  → bind proof_session_id  (RAPHAEL-assigned, immutable)
  → bind provider instance (dedicated; instance_id = invocation_id)
  → clear execution history (assert getExecutions() initially empty)
  → execute exactly ONE capability (binary_sink_scan, exact fixture)
  → collect boundary events (tool_call/tool_result, PRIMARY)
  → collect provider executions (getExecutions(), SECONDARY)
  → B4 attestation         (expected_calls = 1)
  → teardown               (kill + reap)
  → verify teardown        (PID gone / namespace gone; M5)
  → discard instance
```

**Minimum RAPHAEL-side seam if the provider cannot offer a fresh instance
unchanged:** a RAPHAEL-owned *instance handle* wrapping one process/namespace
whose lifetime is a single proof, plus a pre-execution assertion that
`getExecutions()` is empty. No change to the provider source is planned.

## 4. Fixture specification

| item | value |
|---|---|
| path | `fixtures/c1a_proof/raphael_c1a_fixture.txt` |
| root | `fixtures/c1a_proof` (RAPHAEL-owned) |
| bytes | 376 |
| sha256 | `c033fda6e893ed965de8496ad170628d33ce69817c6ad05bbb63bcb5e1010bd1` |
| content | deterministic, POSIX, non-secret, non-executable; single file |
| expected `binary_sink_scan` result | deterministic negative (no binary-sink definitions); to be **recorded at the first authorized proof** and frozen as golden |

The fixture is read-only during a proof; pre/post `fixture_digest` must match.

## 5. First-proof checklist

Machine-checkable: `docs/integration/phase-2c-first-proof-checklist.json`
(items G0, G0-DEPS, G2, M1, M2, M5, B4, B4-LIFECYCLE, C1A, C1A-TRANSPORT, M4,
M7 with READY / NOT_READY / UNKNOWN).

## 6. Blockers before a live proof

1. Provider dependencies absent (`node_modules`) — `npm ci` needs authorization.
2. No container runtime — isolation must be built from userns + `bwrap` + `tmpfs`
   and independently verified (escape probes for M1, egress probes for M2).
3. Out-of-process adapter transport not implemented (`T3MP3STAdapter` fails closed).
4. Dedicated fresh-instance lifecycle not implemented; `getExecutions()` emptiness
   assertion not enforced at proof time.
5. M5 teardown observation not implemented.

## 7. Status

**M1: OPEN. M2: OPEN. M5: OPEN.** No provider execution occurred; no live proof
was run; no container/namespace was provisioned; the provider tree is unmodified.
Live proof NOT AUTHORIZED.
