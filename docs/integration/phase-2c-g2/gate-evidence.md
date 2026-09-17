# Phase 2C — G2 Seccomp + Cgroup Verification Evidence

- Date: 2026-09-17
- Executor: GLM 5.3 (Primary Executor lane)
- Scope: Phase 2C Gates A–H (strace curation, curated policy, filtered positive +
  negative smokes, cgroup prerequisite verification, scratch decision).
- T3MP3ST was **never executed**; no provider code, Arsenal, `binary_sink_scan`,
  c1a fixture, M1/M2/M5 probe, or live proof was run.

## Gate A — tooling

| Tool | Version / state |
|---|---|
| strace | 6.19 (`/usr/bin/strace`) — installed by the user |
| libseccomp | `/usr/lib/x86_64-linux-gnu/libseccomp.so.2.6.0` (already present) |
| bwrap | bubblewrap 0.11.1, supports `--seccomp FD` and `--add-seccomp-fd FD` |
| node | v22.22.1 (`/usr/bin/node`, binds system `libuv.so.1`) |

## Gate B — plain Node syscall curation

Two deterministic, non-networked workloads were run **inside the exact sandbox
shape** (same userns/pid/ipc/uts/net, uid 65534, cap-drop ALL, same ro binds),
traced with `strace -f` from inside the sandbox (strace bound read-only, trace
written to a rw host bind).

- workload 1 (loader): `node -e 'process.stdout.write("RAPHAEL_OK")'`
- workload 2 (IO-shape): read a dummy JSON file (`/smoke/dummy.json`, **not** the
  c1a fixture), `JSON.parse`, deterministic stdout.

Results: `RAPHAEL_OK` (exit 0) and
`RAPHAEL_IO {"name":"raphael-g2","count":5,"sum":14,"ok":true}` (exit 0).

Traces (sha256):

| trace | sha256 |
|---|---|
| loader | `a5c52a5f41e98fbd5b0310e1dbeb2727d909576cd3861481a8e8c843dff4c4a3` |
| io_shape | `1aad8e17eaad52ae5bc32850455e09931a6ca202031f9e7ece8b8b41f68d6922` |

Inventory: `syscall-inventory.json`
(sha256 `48bc29c41cb4ed6512ab9601726a70cec7d2c398d5c5f5e43ab566fb4ae4bb1f`).

**2675 syscall records, 50 unique syscalls**, errnos observed:
ENOENT 83, EBADF 26, ENOTTY 10, EAGAIN 2. **No EPERM on the positive path.**

### Runtime closure incompleteness discovered (Gate B)

The pinned Ubuntu Node **aborts at startup** under the G1 closure (libs only):
`Cannot load externalized builtin: internal/deps/cjs-module-lexer/lexer`.
`strings libnode.so.127 | grep /usr/share/nodejs` enumerates 6 externalized
builtin assets that MUST be part of the closure:

```
/usr/share/nodejs/acorn-walk/dist/walk.js
/usr/share/nodejs/acorn/dist/acorn.js
/usr/share/nodejs/cjs-module-lexer/dist/lexer.js
/usr/share/nodejs/cjs-module-lexer/lexer.js
/usr/share/nodejs/minimatch/dist/cjs/index.bundle.js
/usr/share/nodejs/undici/undici-fetch.js
```

These are now `NODE_BUILTIN_ASSETS` in the substrate and are bound individually
read-only. This closes Muse's "Node runtime closure forward obligation".

## Gate C — curated deny-by-default policy

`curated-allowlist.json`
(sha256 `4c61fa6406da745a13c6f609eaa31feb75b4275eb02ef4d14102f2754159fa5e`).

- **47 allow entries**, each with classification, reason, and trace evidence.
- Default action `SCMP_ACT_ERRNO(EPERM)`; x86_64 native arch only.
- Arg-filtered: `clone` (requires `(flags & CLONE_VM|CLONE_THREAD) == CLONE_VM|CLONE_THREAD`;
  any `CLONE_NEW*` or fork-style flags denied), `prctl` (only `PR_SET_NAME`),
  `ioctl` (only `FIONBIO`, `TCGETS2`).
- Special: `clone3` → **ENOSYS** (so glibc falls back to `clone`).
- Denied families documented in `DENIED_SYSCALLS` (socket/connect, ptrace,
  process_vm_*, mount API incl. `open_tree`/`move_mount`/`fsopen`/`fsmount`/
  `fspick`/`mount_setattr`, unshare/setns, bpf, perf_event_open, userfaultfd,
  io_uring_*, kexec/init_module/delete_module, keyctl/add_key/request_key,
  landlock_*, open_by_handle_at/name_to_handle_at, memfd_create, execveat,
  openat2, pidfd_*, setuid/setgid/setgroups/capset, seccomp, clone3, inotify_*,
  waitid, vmsplice, ...).
- Amended on evidence: `wait4` allowed (bwrap PID-1 sandbox init reaps the
  command; observed `bwrap: init wait(): Operation not permitted` without it).

## Gate D — filter built with existing libseccomp

A small auditable ctypes wrapper (`raphael_ibm_bob/seccomp_policy.py`) over the
already-installed `libseccomp.so.2` builds the filter and exports raw BPF via
`seccomp_export_bpf`. No package was installed.

| digest | value |
|---|---|
| BPF bytes | 544 |
| BPF sha256 | `2a8ca0f732f25d0d90d889f7ff8307fca045de923828d2191c36ff30e056ab67` |
| module allowlist sha256 | `fcf0beeef99ddfc44b0bf7a6520e63e89ac09b66d01c1a3c0d73e1bcfb392668` |

The blob is committed as `raphael_c1a_policy.bpf`. Integration: the substrate
emits `--seccomp <FD>` (fd >= 3) so bwrap applies the filter to the sandboxed
process before the pinned Node command is exec'd. Seccomp is NOT loaded inside
the future Node launcher.

## Gate E — positive smoke under the policy

Both plain-Node workloads re-run under `bwrap --seccomp 3`:

- loader → `RAPHAEL_OK`, exit 0
- IO-shape → `RAPHAEL_IO {...}`, exit 0

Host-side strace of the filtered run shows the **only EPERM** is the intended
`io_uring_setup` (2×) — libuv fell back gracefully (exit 0, exact output).
`clone3` → ENOSYS (1×) → glibc fell back to `clone` with thread flags (6×,
allowed). No unexpected EPERM on any allowed syscall.

**Substrate argv smoke:** the argv produced by
`build_bwrap_argv(spec, seccomp_fd=3)` (full closure incl. the 6 assets, no
tmpfs, `--seccomp 3`) ran `node --version` → `v22.22.1`, rc 0 →
`SUBSTRATE_ARGV_SMOKE_OK`.

## Gate F — negative Node-reachable probes (all under the policy)

| probe | observed |
|---|---|
| `net.connect(80,"127.0.0.1")` | `NET_ERR code=EPERM errno=-1` |
| `dns.resolve4("example.com")` | `DNS_ERR code=ECONNREFUSED` (c-ares "cannot contact DNS servers"); traced evidence: `socket(AF_INET, SOCK_DGRAM, IPPROTO_IP) = -1 EPERM` (4×) |
| `child_process.execFileSync("/bin/true")` | `SPAWN_ERR code=EPERM errno=-1` (clone without thread flags denied) |
| `fs.watch("/smoke")` | `WATCH_ERR code=EPERM errno=-1` (inotify denied) |

No external destination was contacted. Honest limitation: negative probes are
limited to JS-reachable syscalls; mount/ptrace/execveat rejection is proven by
BPF source review + design, not by an in-sandbox raw-syscall prober.

## Gate G — cgroup v2 prerequisite verification

Delegation confirmed: `/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service`
is owned by uid 1000 with `cgroup.subtree_control = "cpu memory pids"`.

Verified via `systemd-run --user --scope`:

| step | result |
|---|---|
| create | scope created: `.../user@1000.service/app.slice/raphael-probe-<ts>.scope` |
| limits | `memory.max=268435456`, `pids.max=64`, `cpu.max=50000 100000` (read back) |
| member | `cgroup.procs` contained the workload; `cgroup.events` = `populated 1` |
| cgroup.kill | written successfully |
| termination | workload pid GONE; `/proc/<pid>` absent; unit `inactive` |
| cleanup | cgroup removed (systemd reaped the scope) |

**Limitation (reported honestly):** `populated=0` was **not directly polled**
because systemd removes the scope cgroup on termination. A direct manual
sibling cgroup was created, limits written and read back, created/removed, but
process migration into it failed (`EINVAL`/`EPERM`) — automation runs in
`init.scope` (root-owned source cgroup), so only systemd-managed scopes can
host processes here. **M5 prerequisite is substantially verified (create,
limits, kill, termination, cleanup) but `populated=0` observation remains a
forward obligation for the M5 teardown design.**

## Gate H — scratch decision (D1)

Neither trace accessed `/tmp` (`/tmp` occurrences: 0 in both). **D1 adopted:
scratch eliminated entirely.**

- `--tmpfs /tmp` and `--size` removed from the generated argv.
- `scratch_bytes` removed from `SandboxSpec`; `SCRATCH_MODE = "NO_SCRATCH"`;
  `SCRATCH_FLAGS` now reports `NO_SCRATCH` / `NOT_APPLICABLE`.
- No writable filesystem exists in the sandbox; the previously observed
  `noexec` gap is moot.
- No privileged tmpfs helper introduced.
