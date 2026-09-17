# Phase 2C — Probe-Stage Evidence (Gates 0–7)

- Date: 2026-09-17
- Executor: DeepSeek V4.1 Flash (Primary Executor)
- Authorization: probe-stage provisioning + host validation **only**.
  This is NOT authorization for live provider proof.
- RAPHAEL HEAD at probe start: `c99399be042fbbd25e2b87d51136c2ccdeb5c0e8`
- Substrate code commit (Gate 1 closure): `9c7cb06f7d86fcf552b67294db8945f740de52a3`
- Provider: `/home/moiz/audit-repos/T3MP3ST` @ `29824d5625ede419ac8cdae418c8f4c72c6270f7`
  (clean tree; **not executed**).

No T3MP3ST / Arsenal / `binary_sink_scan` / C1A / provider code was run in any
gate below. All probes are host-level, non-provider workloads.

## Gate 0 — Pre-flight

Status: **PASS** (with two hard capability gaps recorded).

| Check | Observed |
|---|---|
| RAPHAEL HEAD | `c99399be042fbbd25e2b87d51136c2ccdeb5c0e8` (expected) |
| T3MP3ST HEAD | `29824d5625ede419ac8cdae418c8f4c72c6270f7`; tree clean (0 changed) |
| Fixture sha256 | `c033fda6e893ed965de8496ad170628d33ce69817c6ad05bbb63bcb5e1010bd1` |
| bwrap | `/usr/bin/bwrap` — bubblewrap 0.11.1 |
| user+net namespaces | `USERNET_OK` (`unshare --user --map-root-user --net true`) |
| cgroup v2 | mounted `cgroup2 on /sys/fs/cgroup ... rw,nosuid,nodev,noexec,relatime,nsdelegate`; controllers `cpuset cpu io memory hugetlb pids rdma`; current cgroup `0::/init.scope` |
| cgroup writability | **`CGROUP_NOT_WRITABLE`** (mkdir `/sys/fs/cgroup/rbs_probe` denied for uid 1000 — no delegation) |
| seccomp kernel | `actions_avail = kill_process kill_thread trap errno user_notif trace log allow`; current `Seccomp: 0` |
| libseccomp (python) | **absent** — `ModuleNotFoundError: No module named 'seccomp'` |
| strace | **absent** — `NO_STRACE` |
| binutils | `readelf`, `objdump`, `ldd` present |
| node | `/usr/bin/node` — v22.22.1 |
| bwrap smoke | `BWRAP_SMOKE_OK` (`--unshare-all` + ro-binds ran `/usr/bin/true`) |

Pre-flight gaps that gate later gates:
- **No `strace` and no libseccomp bindings** → empirical seccomp curation and
  filter loading cannot be performed safely (Gate 2).
- **Root cgroup is not writable/delegated** to the executing user → no cgroup
  creation, `cgroup.kill`, or `cgroup.events populated=0` observation (Gate 7).

## Gate 1 — Node runtime closure

Status: **PASS** (static enumeration + generated-argv live smoke).

`readelf -l /usr/bin/node` → interpreter `/lib64/ld-linux-x86-64.so.2`
(`-> ../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2`).
`readelf -d` → `NEEDED: libnode.so.127, libc.so.6`.
`ldd` resolves a 23-library transitive closure:

```
libnode.so.127 libc.so.6 libz.so.1 libllhttp.so.9.3 libuv.so.1
libada-url0.so.3 libsimdjson.so.29 libsimdutf.so.31 libbrotlidec.so.1
libbrotlienc.so.1 libbrotlicommon.so.1 libcares.so.2 libnghttp2.so.14
libsqlite3.so.0 libzstd.so.1 libcrypto.so.3 libssl.so.3 libicui18n.so.78
libicuuc.so.78 libicudata.so.78 libstdc++.so.6 libm.so.6 libgcc_s.so.1
```

All under `/usr/lib/x86_64-linux-gnu/`. `libnode.so.127` is the real Node
library dependency; `libstdc++`/`libgcc_s` are present.

Read-only mounts: every closure path (runtime + interpreter + 23 libs) is bound
**individually** `--ro-bind <path> <path>`; **no `/usr/lib`, `/lib`, `/lib64`
or `/usr` tree is bound**. Enforced in code by `validate_node_closure()` +
`SYSTEM_LIBRARY_PREFIXES`, and asserted in tests `test_8a/8b/8c`.

Evidence — live smoke of the **actual generated bwrap argv** (launcher argument
substituted with `--version`; provider never invoked):

```
argv len: 115
rc: 0
stdout: v22.22.1
GENERATED_ARGV_SMOKE_OK
```

## Gate 2 — Seccomp curation (plain Node only)

Status: **BLOCKED / OPEN** (fail-closed).

Cannot be performed safely in this environment:
- `strace` is not installed and no syscall-tracing facility (audit/ptrace) is
  available → the observed-syscall trace required for empirical curation
  cannot be collected.
- libseccomp Python bindings are absent (`import seccomp` fails) → a curated
  filter cannot be loaded/verified without hand-rolling raw BPF via ctypes,
  which is neither instrumentable nor independently verifiable here.

Per the fail-closed rule, no policy was curated, no filter was loaded, and no
Node-under-seccomp smoke test was claimed. `SeccompPolicy` remains
`DRAFT_NOT_PROVEN` / `is_production_ready == False`.

## Gate 3 — NoNewPrivs observation

Status: **PASS**.

Sandbox command (non-provider):

```
bwrap --unshare-all --ro-bind /usr /usr --ro-bind /lib /lib \
      --ro-bind /lib64 /lib64 --ro-bind /bin /bin \
      --proc /proc --dev /dev -- \
      /bin/grep -E "NoNewPrivs|Seccomp:" /proc/self/status
```

Observed **inside** the sandbox:

```
NoNewPrivs:	1
Seccomp:	0
```

Recorded as `NNP_STATE = "OBSERVED_INSIDE_SANDBOX"` (Gate 3). The RAPHAEL
launcher must still read and require this before any provider import.

## Gate 4 — tmpfs scratch probe

Status: **PASS** (kernel-visible state recorded; one property NOT enforced).

Kernel-visible mount options read from `/proc/mounts` inside the sandbox:

| Config | Observed `/tmp` options |
|---|---|
| `--size 16777216 --tmpfs /tmp` | `rw,nosuid,nodev,relatime,size=16384k,mode=755,uid=1000,gid=1000` |
| `--tmpfs /tmp` (no size) | `rw,nosuid,nodev,relatime,mode=755,...` (no `size=`) |
| `--size 1048576 --tmpfs /tmp` | `rw,nosuid,nodev,relatime,size=1024k,mode=755,...` |

| Property | Observed |
|---|---|
| size | **ENFORCED** (`size=16384k` / `size=1024k`; absent when `--size` omitted) |
| nosuid | **ENFORCED** (`nosuid` present) |
| nodev | **ENFORCED** (`nodev` present) |
| noexec | **NOT ENFORCED** — `noexec` is absent; scratch remains executable |

`SCRATCH_FLAGS` updated to `OBSERVED_*`. The `noexec` residual is now
empirically **disproven for scratch**: code can execute from `/tmp` inside the
sandbox. This does not widen the intended boundary (the command is still the
pinned executable and `no_new_privs` is set), but it is recorded truthfully and
must not be described as `noexec`.

## Gate 5 — M1 escape probe suite

Status: **NOT STARTED**.

Sequencing rule: "Only begin M1 after Gates 1–4 are successful." Gate 2 is
BLOCKED, so Gates 1–4 are not all successful and M1 was not begun.
Fail-closed: M1 remains **NOT_READY**; no escape probe was run.

## Gate 6 — M2 egress probe suite

Status: **NOT STARTED**.

Sequencing rule: "Only begin M2 after M1 is accepted." M1 not started.
M2 remains **NOT_READY**; no egress probe was run.

## Gate 7 — M5 live teardown observation

Status: **BLOCKED / OPEN**.

Sequencing rule: "Only after M1 and M2 are accepted." Additionally the hard
prerequisite is missing: the root cgroup is **not writable/delegated**
(`CGROUP_NOT_WRITABLE`), so a cgroup cannot be created, `cgroup.kill` cannot be
issued, and `cgroup.events populated=0` cannot be observed. M5 remains
**NOT_READY**; no teardown observation was performed.

## Unchanged readiness (must stay false)

- `C1A-TRANSPORT = NOT_READY` (adapter still fails closed UNAVAILABLE)
- `B4-LIFECYCLE = NOT_READY`
- `live_proof = NOT_READY`
- `live_proof_authorized = false`
- Provider remains unauthorized; nothing provider-side was executed.
