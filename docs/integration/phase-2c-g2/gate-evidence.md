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

> Note (B2): the earlier probe-stage record of `argv length 115` /
> `GENERATED_ARGV_SMOKE_OK` was produced by a superseded builder. The current
> builder output is documented under Gate E (`argv length 131`,
> `SUBSTRATE_ARGV_SMOKE_OK_CURRENT_BUILDER`).

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
(sha256 `33b2fe92c93eec3e0bc761e985d67bf2632783934c2ba3fb8dfadc4ccff0a080`
— corrected B1 revision).

- **46 allow entries**, each with classification, reason, and trace evidence.
- Default action `SCMP_ACT_ERRNO(EPERM)`; x86_64 native arch only.
- **Corrected mechanism (B1 + R1).** `clone` is **argument-filtered only** — no
  unconditional clone allow exists (the B1 defect listed `clone` in both tables,
  which libseccomp collapsed into an unconditional allow; that entry was
  removed). The single clone rule is one masked comparison:
  `SCMP_ACT_ALLOW` for `(flags & (CLONE_THREAD_BITS | CLONE_NEWMASK_FULL)) == CLONE_THREAD_BITS`,
  where `CLONE_THREAD_BITS = CLONE_VM|CLONE_THREAD` and `CLONE_NEWMASK_FULL`
  covers the full Linux family (`CLONE_NEWTIME|NEWNS|NEWCGROUP|NEWUTS|NEWIPC|NEWUSER|NEWPID|NEWNET`).
  So the intended thread-compatible bits are REQUIRED and **every CLONE_NEW*
  bit is explicitly denied by the filter** (a clone carrying NEW* fails even
  when VM|THREAD are also set — kernel-side rejection is not relied upon).
  `fork`-like clones (no thread bits) are denied. `prctl` (only `PR_SET_NAME`)
  and `ioctl` (only `FIONBIO`, `TCGETS2`) are likewise argument-filtered.
  (One combined mask, not two comparisons: libseccomp returns EINVAL for more
  than one `MASKED_EQ` on the same argument, and separate ALLOW rules OR.)
- Special: `clone3` → **ENOSYS** (so glibc falls back to `clone`), handled
  separately from `clone`.
- The exported pseudo filter code (PFC) was inspected directly to prove the
  corrected shape and to evaluate the clone predicate — see the PFC regression
  tests (R1 tests 16–21 derive the allow/reject decision from the exported mask
  and datum itself).
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
| BPF bytes | 592 |
| BPF sha256 | `d1574a64643907e6c95ccafbfc74e7f04977781014ade214011e57994cb65242` (R1 revision) |
| curated-allowlist.json sha256 | `8a7efc6f4d11bea59b60a9099dd88e287b8f46f300ba158befd6c922fb0ddaf2` (R1 revision) |
| clone rule (PFC) | `if ($a0.lo32 & 0x7e030180 == 65792)` → mask `0x7e030180` = THREAD_BITS\|NEWMASK_FULL, datum `65792` = `0x10100` = CLONE_VM\|CLONE_THREAD |

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

**B1 fixed-policy re-run:** trace sha256
`d87cd99c32f36418b799286d4d282a29a5f6317c69e15802ac332534834270ce`; only
EPERM = `io_uring_setup` (intended); `clone3`→ENOSYS (1) → `clone` (6, thread
flags) allowed.

**Substrate argv smoke (current builder, regenerated B2):** the argv produced
by the CURRENT `build_bwrap_argv(spec, seccomp_fd=3)` is **length 131**
(replacing the stale G1-era length 115), with 34 `--ro-bind` pairs,
`--seccomp 3` at index 34 (before `--` at index 128), tail
`/provider -- /usr/bin/node /provider/c1a_launcher.js`, unshare flags
user/pid/ipc/uts/net, `--die-with-parent --new-session --cap-drop ALL
--dev /dev --proc /proc`, uid/gid 65534, and **no `--tmpfs`/`--size`
(NO_SCRATCH)**. It ran `node --version` → `v22.22.1`, rc 0 →
**`SUBSTRATE_ARGV_SMOKE_OK_CURRENT_BUILDER`**.

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

## R1 — clone NEW* exclusion (corrected)

Rebuilt after adding the explicit `CLONE_NEW*` exclusion (see Gate C). New BPF
sha256 `d1574a64…` (592 B); allowlist sha256 `8a7efc6f…`.

- PFC: `if ($a0.lo32 & 0x7e030180 == 65792)` — the mask includes the full
  `CLONE_NEW*` family, the datum requires `CLONE_VM|CLONE_THREAD`.
- R1 regression tests 16–21 derive the decision from the exported mask/datum:
  a thread-compatible clone reaches ALLOW; clones carrying `CLONE_NEWNS`,
  any other single NEW* bit, or multiple NEW* bits are rejected; a clone
  without thread bits (or fork-style `SIGCHLD`) is rejected; no unconditional
  clone ALLOW; `clone3` remains `ERRNO(38)`.
- Positive smoke re-run: loader `RAPHAEL_OK` and io_shape `RAPHAEL_IO {...}`
  both exit 0; **no unexpected EPERM**; `clone3`→ENOSYS→`clone` still works.

## R2 — non-provider C1A launcher-shape smoke

A harmless, deterministic nested CommonJS module tree mirrors the future C1A
launcher shape (no provider code, no T3MP3ST import, no fixture, no network,
no child_process, no dynamic command execution):

```
main.js → lib/scanner.js → {lib/util/parse.js, lib/util/io.js, lib/util/index.js,
                            lib/pkg/index.js (resolved via lib/pkg/package.json)}
```

It exercises nested `require()`, `index.js`/`package.json` resolution, multi-file
stat/read, parse, and module init, emitting
`RAPHAEL_SHAPE {"pkg":"raphael-smoke-pkg","rows":3,"sum":7,"keys":["alpha","beta","gamma"],"hasUtil":true}`.

| run | result |
|---|---|
| without seccomp (strace) | exit 0, exact output |
| with current curated policy (`--seccomp 3`) | exit 0, identical output |

Trace sha256 `0af2fd637b1eb191757697679e1c09bb1ed75e909b64944b9a07d6eba9c2fbde`;
shape inventory `launcher-shape-inventory.json`
(sha256 `a999436bab60168b56450b19235a4d4c8828a64ce5089162cd748cec3dc06c9c`).

**Delta vs the plain-Node inventory: NO new syscalls.** 49 unique syscalls, of
which 47 are allowed/arg-filtered and 2 (`io_uring_setup`, `io_uring_enter`)
are the intentional denials that libuv falls back from (exit 0 proves the
fallback). `getdents64` did NOT appear — module resolution resolved explicit
paths and `package.json` without directory listing. No allowlist entries were
added; the policy is unchanged by R2.

## Gate H — scratch decision (D1)

Neither trace accessed `/tmp` (`/tmp` occurrences: 0 in both). **D1 adopted:
scratch eliminated entirely.**

- `--tmpfs /tmp` and `--size` removed from the generated argv.
- `scratch_bytes` removed from `SandboxSpec`; `SCRATCH_MODE = "NO_SCRATCH"`;
  `SCRATCH_FLAGS` now reports `NO_SCRATCH` / `NOT_APPLICABLE`.
- No writable filesystem exists in the sandbox; the previously observed
  `noexec` gap is moot.
- No privileged tmpfs helper introduced.
