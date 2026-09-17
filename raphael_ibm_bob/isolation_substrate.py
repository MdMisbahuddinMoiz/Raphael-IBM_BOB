"""raphael_ibm_bob.isolation_substrate — Phase 2C isolation substrate.

Concrete, auditable **construction layer** for the C1A first-proof sandbox.

    RAPHAEL core -> ProviderRuntime -> RAPHAEL launcher
      -> SEPARATE sandbox OS process (bwrap + userns + netns + cgroup v2 + seccomp)
      -> T3MP3ST -> bounded transcript -> receipt parser -> B4 -> gate

This module BUILDS and statically VALIDATES the construction (bwrap argv,
mount table, cgroup plan, seccomp policy, launcher seam). It performs **no
execution**: no bwrap launch, no namespace/cgroup creation, no seccomp load,
no provider/Node run, no probes.

Truth discipline (B1-B5 corrections):

    CONFIGURATION CLAIM  !=  ACTUAL KERNEL/MOUNT EFFECT.
    Tests assert the ACTUAL ARGV, never metadata strings.

Recorded state (honest):

    tmpfs size      ENFORCED in argv (--size before --tmpfs)
    tmpfs flags     noexec/nosuid/nodev = RESIDUAL / UNPROVEN (bwrap --tmpfs
                    gives no per-mount flag control; deferred to a host-level
                    probe or a pre-mounted tmpfs)
    seccomp         status = DRAFT_NOT_PROVEN (allowlist must be curated from
                    an empirical Node trace before provider execution)
    no_new_privs    REQUIRED by contract; observed state NOT_YET_PROVEN
                    (must be read from /proc/self/status inside the sandbox)
    M1/M2/M5        NOT CLOSED (no probes run)
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: The single authorized capability/tool (hardcoded; never caller-supplied).
C1A_TOOL = "binary_sink_scan"

#: Pinned provider identity.
PROVIDER_PIN = "29824d5625ede419ac8cdae418c8f4c72c6270f7"

#: Fixture identity.
FIXTURE_SHA256 = ("c033fda6e893ed965de8496ad170628d33ce69817c6ad0"
                  "5bbb63bcb5e1010bd1")

#: Pinned, deterministic Node runtime (absolute; never caller-supplied).
NODE_RUNTIME = "/usr/bin/node"

#: GATE 1 — explicit read-only runtime closure for the pinned Node runtime.
#: Enumerated STATICALLY with `readelf`/`ldd` against the pinned runtime
#: (no Node execution). The runtime links `libnode.so.127` + libc directly
#: and pulls the icu/ssl/uv/... closure transitively. Every path below is
#: bound INDIVIDUALLY read-only; no `/usr/lib` or `/lib` TREE is ever bound.
NODE_INTERPRETER = "/lib64/ld-linux-x86-64.so.2"
NODE_CLOSURE_LIBS: Tuple[str, ...] = (
    "/usr/lib/x86_64-linux-gnu/libada-url0.so.3",
    "/usr/lib/x86_64-linux-gnu/libbrotlicommon.so.1",
    "/usr/lib/x86_64-linux-gnu/libbrotlidec.so.1",
    "/usr/lib/x86_64-linux-gnu/libbrotlienc.so.1",
    "/usr/lib/x86_64-linux-gnu/libc.so.6",
    "/usr/lib/x86_64-linux-gnu/libcares.so.2",
    "/usr/lib/x86_64-linux-gnu/libcrypto.so.3",
    "/usr/lib/x86_64-linux-gnu/libgcc_s.so.1",
    "/usr/lib/x86_64-linux-gnu/libicudata.so.78",
    "/usr/lib/x86_64-linux-gnu/libicui18n.so.78",
    "/usr/lib/x86_64-linux-gnu/libicuuc.so.78",
    "/usr/lib/x86_64-linux-gnu/libllhttp.so.9.3",
    "/usr/lib/x86_64-linux-gnu/libm.so.6",
    "/usr/lib/x86_64-linux-gnu/libnghttp2.so.14",
    "/usr/lib/x86_64-linux-gnu/libnode.so.127",
    "/usr/lib/x86_64-linux-gnu/libsimdjson.so.29",
    "/usr/lib/x86_64-linux-gnu/libsimdutf.so.31",
    "/usr/lib/x86_64-linux-gnu/libsqlite3.so.0",
    "/usr/lib/x86_64-linux-gnu/libssl.so.3",
    "/usr/lib/x86_64-linux-gnu/libstdc++.so.6",
    "/usr/lib/x86_64-linux-gnu/libuv.so.1",
    "/usr/lib/x86_64-linux-gnu/libz.so.1",
    "/usr/lib/x86_64-linux-gnu/libzstd.so.1",
)

#: GATE B (observed): Ubuntu's Node EXTERNALIZES several builtins to data
#: files. Without these the pinned runtime aborts at startup ("Cannot load
#: externalized builtin"), so they are part of the runtime closure. Enumerated
#: with: strings libnode.so.127 | grep /usr/share/nodejs
NODE_BUILTIN_ASSETS: Tuple[str, ...] = (
    "/usr/share/nodejs/acorn-walk/dist/walk.js",
    "/usr/share/nodejs/acorn/dist/acorn.js",
    "/usr/share/nodejs/cjs-module-lexer/dist/lexer.js",
    "/usr/share/nodejs/cjs-module-lexer/lexer.js",
    "/usr/share/nodejs/minimatch/dist/cjs/index.bundle.js",
    "/usr/share/nodejs/undici/undici-fetch.js",
)

#: The ONLY prefixes a closure path may live under (GATE 1). This forbids
#: binding arbitrary host trees or caller-supplied runtime locations.
SYSTEM_LIBRARY_PREFIXES: Tuple[str, ...] = (
    "/usr/bin",
    "/usr/lib/x86_64-linux-gnu",
    "/lib/x86_64-linux-gnu",
    "/lib64",
    "/usr/share/nodejs",
)

#: The future RAPHAEL-owned launcher entry (read-only); NOT executed here.
LAUNCHER_ENTRY = "/provider/c1a_launcher.js"

#: Non-root identity inside the user namespace.
SANDBOX_UID = 65534
SANDBOX_GID = 65534

#: Gate H (D1): scratch ELIMINATED. Plain-Node traces (loader + IO-shape,
#: `/tmp` access count = 0) proved no writable scratch is required, so no
#: tmpfs is mounted; the sandbox has no writable filesystem at all.
SCRATCH_MODE = "NO_SCRATCH"

#: Timeout bound.
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 600.0

#: cgroup v2 limits.
DEFAULT_MEMORY_MAX = "256M"
DEFAULT_PIDS_MAX = "64"
DEFAULT_CPU_MAX = "50000 100000"

#: bwrap program (never executed by this module).
BWRAP = "bwrap"


class SubstrateConfigError(Exception):
    """Fail-closed configuration error for the isolation substrate."""


class ArbitraryInputError(SubstrateConfigError):
    """A caller supplied a tool/path outside the hardcoded contract."""


def _canonical(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _abs(path: str) -> bool:
    return isinstance(path, str) and bool(path) and \
        os.path.isabs(path) and _canonical(path) == path


def _finite_positive(value: Any, name: str,
                     maximum: Optional[float] = None) -> float:
    """Reject bool/NaN/inf/non-numeric/non-positive (B5A)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SubstrateConfigError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SubstrateConfigError(f"{name} must be numeric") from None
    if not math.isfinite(number) or number <= 0:
        raise SubstrateConfigError(f"{name} must be finite and positive")
    if maximum is not None and number > maximum:
        raise SubstrateConfigError(f"{name} must be <= {maximum}")
    return number


def _is_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and \
        all(ch in "0123456789abcdef" for ch in value)


# ---------------------------------------------------------------------------
# References + identity (static verification only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderRef:
    """Pinned provider checkout (source + node_modules read-only)."""
    root: str
    node_modules: str
    pin: str = PROVIDER_PIN

    def contained(self) -> bool:
        """node_modules must live INSIDE the provider root (B5B)."""
        try:
            root = _canonical(self.root)
            nm = _canonical(self.node_modules)
            return os.path.commonpath([root, nm]) == root and nm != root
        except ValueError:
            return False

    def head_sha(self) -> str:
        """Resolve git HEAD without invoking git (no subprocess)."""
        head = os.path.join(self.root, ".git", "HEAD")
        with open(head, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        if value.startswith("ref:"):
            ref_path = os.path.join(self.root, ".git",
                                    value.split(":", 1)[1].strip())
            with open(ref_path, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        return value

    def verify_pin(self) -> Tuple[bool, str]:
        try:
            head = self.head_sha()
        except OSError as exc:
            return False, f"unreadable:{type(exc).__name__}"
        return head == self.pin, head


@dataclass(frozen=True)
class FixtureRef:
    """The one RAPHAEL-owned fixture file."""
    root: str
    path: str
    sha256: str = FIXTURE_SHA256

    def actual_sha256(self) -> Optional[str]:
        try:
            with open(self.path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return None

    def verify(self) -> Tuple[bool, str]:
        actual = self.actual_sha256()
        if actual is None:
            return False, "unreadable"
        return actual == self.sha256, actual

    def root_contents(self) -> List[str]:
        try:
            return sorted(os.listdir(self.root))
        except OSError:
            return []


# ---------------------------------------------------------------------------
# Node runtime closure (GATE 1 — static enumeration, no execution)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeRuntimeClosure:
    """Explicit, read-only runtime closure for the pinned Node runtime."""
    runtime: str
    interpreter: str
    libraries: Tuple[str, ...]
    assets: Tuple[str, ...] = ()

    def all_paths(self) -> Tuple[str, ...]:
        return ((self.runtime, self.interpreter) + tuple(self.libraries)
                + tuple(self.assets))

    def to_dict(self) -> Dict[str, Any]:
        return {"runtime": self.runtime, "interpreter": self.interpreter,
                "libraries": list(self.libraries), "assets": list(self.assets),
                "mode": "ro", "tree_binds": [], "closure_size": len(self.all_paths())}


def node_runtime_closure() -> NodeRuntimeClosure:
    """Return the pinned static closure. No discovery, no execution."""
    return NodeRuntimeClosure(runtime=NODE_RUNTIME,
                              interpreter=NODE_INTERPRETER,
                              libraries=NODE_CLOSURE_LIBS,
                              assets=NODE_BUILTIN_ASSETS)


def validate_node_closure(closure: NodeRuntimeClosure) -> None:
    """Every closure path must be an explicit canonical file under a known
    system prefix. No duplicates, no directory trees, no caller paths."""
    paths = closure.all_paths()
    if len(set(paths)) != len(paths):
        raise SubstrateConfigError("node closure contains duplicate paths")
    for path in paths:
        if not _abs(path):
            raise SubstrateConfigError(
                f"node closure path must be canonical absolute: {path!r}")
        if not any(path.startswith(prefix + "/")
                   for prefix in SYSTEM_LIBRARY_PREFIXES):
            raise SubstrateConfigError(
                f"node closure path outside system prefixes: {path!r}")


# ---------------------------------------------------------------------------
# Sandbox specification + validation (fail-closed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxSpec:
    """Concrete first-proof sandbox. Constructed, never launched here."""
    provider: ProviderRef
    fixture: FixtureRef
    node_runtime: str = NODE_RUNTIME
    launcher_entry: str = LAUNCHER_ENTRY
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_max: str = DEFAULT_MEMORY_MAX
    pids_max: str = DEFAULT_PIDS_MAX
    cpu_max: str = DEFAULT_CPU_MAX
    uid: int = SANDBOX_UID
    gid: int = SANDBOX_GID
    cgroup_root: str = "/sys/fs/cgroup"


def validate_sandbox_spec(spec: SandboxSpec) -> None:
    """Fail closed on any configuration that could widen the boundary."""
    if not _abs(spec.provider.root):
        raise SubstrateConfigError("provider.root must be canonical absolute")
    if not _abs(spec.provider.node_modules):
        raise SubstrateConfigError("node_modules must be canonical absolute")
    if not spec.provider.contained():
        raise SubstrateConfigError(
            "node_modules must be contained within provider.root (B5B)")
    if not _abs(spec.fixture.root) or not _abs(spec.fixture.path):
        raise SubstrateConfigError("fixture paths must be canonical absolute")
    if os.path.dirname(spec.fixture.path) != spec.fixture.root:
        raise SubstrateConfigError(
            "fixture must be a direct child of fixture.root (no traversal)")
    if not _is_hex(spec.provider.pin, 40):
        raise SubstrateConfigError("provider pin must be a 40-char sha")
    if not _is_hex(spec.fixture.sha256, 64):
        raise SubstrateConfigError("fixture sha256 must be 64 hex chars")
    if not spec.cgroup_root.startswith("/sys/fs/cgroup"):
        raise SubstrateConfigError("cgroup_root must be under /sys/fs/cgroup")
    _finite_positive(spec.timeout_seconds, "timeout_seconds",
                     maximum=MAX_TIMEOUT_SECONDS)
    if spec.uid == 0 or spec.gid == 0:
        raise SubstrateConfigError("sandbox uid/gid must be non-root")
    for name, value in (("memory_max", spec.memory_max),
                        ("pids_max", spec.pids_max),
                        ("cpu_max", spec.cpu_max)):
        if not isinstance(value, str) or not value.strip():
            raise SubstrateConfigError(f"cgroup {name} must be set")
    # B3 — pinned, absolute, non-caller-controllable executable.
    if spec.node_runtime != NODE_RUNTIME:
        raise SubstrateConfigError(
            f"node_runtime must be the pinned {NODE_RUNTIME!r}")
    if not _abs(spec.launcher_entry):
        raise SubstrateConfigError("launcher_entry must be canonical absolute")


def validate_fixture_root(spec: SandboxSpec) -> None:
    """The fixture root must expose EXACTLY the one expected regular file (B5C)."""
    entries = spec.fixture.root_contents()
    expected = [os.path.basename(spec.fixture.path)]
    if entries != expected:
        raise SubstrateConfigError(
            f"fixture.root must contain exactly {expected}, got {entries}")
    if os.path.islink(spec.fixture.path):
        raise SubstrateConfigError("fixture must not be a symlink")


def ensure_tool_literal(tool: str) -> str:
    if tool != C1A_TOOL:
        raise ArbitraryInputError(
            f"tool {tool!r} is outside the C1A contract")
    return tool


def ensure_fixture_literal(spec: SandboxSpec, path: str) -> str:
    if path != spec.fixture.path:
        raise ArbitraryInputError(
            f"path {path!r} is not the exact fixture literal")
    return path


# ---------------------------------------------------------------------------
# bwrap contract
# ---------------------------------------------------------------------------

#: Gate H (D1): scratch is NOT mounted at all. The G4 observation (noexec
#: absent) is therefore moot: there is no writable filesystem in the sandbox.
SCRATCH_FLAGS = {
    "tmpfs": "NO_SCRATCH",
    "size": "NOT_APPLICABLE",
    "noexec": "NOT_APPLICABLE",
    "nosuid": "NOT_APPLICABLE",
    "nodev": "NOT_APPLICABLE",
}


def mount_contract(spec: SandboxSpec) -> Tuple[Dict[str, Any], ...]:
    """Read-only mounts + the single bounded scratch + pinned runtime closure.

    The fixture is bound as the EXACT single file (B5C), not the whole root.
    Every Node runtime path (GATE 1) is bound individually read-only.
    """
    closure = node_runtime_closure()
    mounts = [
        {"kind": "ro-bind", "src": spec.provider.root, "dest": "/provider",
         "mode": "ro"},
        {"kind": "ro-bind", "src": spec.provider.node_modules,
         "dest": "/provider/node_modules", "mode": "ro"},
        {"kind": "ro-bind", "src": spec.fixture.path,
         "dest": "/fixture/" + os.path.basename(spec.fixture.path),
         "mode": "ro"},
        {"kind": "ro-bind", "src": spec.node_runtime,
         "dest": spec.node_runtime, "mode": "ro"},
    ]
    for path in ((closure.interpreter,) + closure.libraries
                 + closure.assets):
        mounts.append({"kind": "ro-bind", "src": path, "dest": path,
                       "mode": "ro"})
    mounts += [
        {"kind": "dev", "src": "dev", "dest": "/dev", "mode": "minimal"},
        {"kind": "proc", "src": "proc", "dest": "/proc", "mode": "private"},
    ]
    return tuple(mounts)


def network_contract(spec: SandboxSpec) -> Dict[str, Any]:
    return {"unshare_net": True, "host_interfaces": False,
            "dns_config": False, "host_routes": False,
            "share_host_netns": False}


def process_contract(spec: SandboxSpec) -> Dict[str, Any]:
    return {"unshare_user": True, "uid": spec.uid, "gid": spec.gid,
            "non_root": True, "cap_drop_all": True,
            "no_new_privs_required": True,
            "no_new_privs_state": NNP_STATE,
            "die_with_parent": True, "new_session": True,
            "unshare_pid": True, "unshare_ipc": True, "unshare_uts": True}


def command_argv(spec: SandboxSpec) -> Tuple[str, ...]:
    """The pinned, deterministic, non-caller-controllable executable (B3)."""
    return (spec.node_runtime, spec.launcher_entry)


def build_bwrap_argv(spec: SandboxSpec,
                     seccomp_fd: Optional[int] = None) -> Tuple[str, ...]:
    """Concrete, auditable bwrap argv. NOT executed by this module.

    ``seccomp_fd`` is an inherited file descriptor holding the curated BPF
    blob (see :mod:`raphael_ibm_bob.seccomp_policy`); when given it is passed
    as ``--seccomp <fd>`` so bwrap applies the filter to the sandboxed process
    BEFORE the pinned Node command is exec'd.
    """
    validate_sandbox_spec(spec)
    if seccomp_fd is not None:
        if isinstance(seccomp_fd, bool) or not isinstance(seccomp_fd, int):
            raise SubstrateConfigError("seccomp_fd must be an integer fd")
        if seccomp_fd < 3:
            raise SubstrateConfigError("seccomp_fd must be >= 3 (not stdio)")
    argv: List[str] = [
        BWRAP,
        "--unshare-user", "--uid", str(spec.uid), "--gid", str(spec.gid),
        "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--die-with-parent", "--new-session",
        "--cap-drop", "ALL",
        "--dir", "/provider", "--dir", "/fixture",
        "--ro-bind", spec.provider.root, "/provider",
        "--ro-bind", spec.provider.node_modules, "/provider/node_modules",
        # exact single fixture file (B5C)
        "--ro-bind", spec.fixture.path,
        "/fixture/" + os.path.basename(spec.fixture.path),
        # pinned runtime (B3)
        "--ro-bind", spec.node_runtime, spec.node_runtime,
        "--dev", "/dev",
        "--proc", "/proc",
        # Gate H (D1): NO scratch tmpfs mounted.
        "--chdir", "/provider",
        "--",
    ]
    if seccomp_fd is not None:
        argv[argv.index("--chdir"):argv.index("--chdir")] = [
            "--seccomp", str(seccomp_fd)]
    # GATE 1: explicit read-only runtime closure binds (no tree binds).
    closure = node_runtime_closure()
    validate_node_closure(closure)
    binds: List[str] = []
    for path in ((closure.interpreter,) + closure.libraries
                 + closure.assets):
        binds += ["--ro-bind", path, path]
    argv[argv.index("--chdir"):argv.index("--chdir")] = binds
    argv.extend(command_argv(spec))
    return tuple(argv)


# ---------------------------------------------------------------------------
# cgroup v2 contract
# ---------------------------------------------------------------------------

CGROUP_TEARDOWN_STEPS: Tuple[str, ...] = (
    "detect stop/timeout",
    "stop accepting success",
    "bounded drain window (RAPHAEL timer)",
    "write cgroup.kill (LOAD-BEARING)",
    "wait for cgroup.events populated=0",
    "independently verify termination (pid starttime/pidfd + cgroup empty)",
    "only then cancellation_acknowledged=true",
    "cleanup cgroup directory",
)


@dataclass(frozen=True)
class CgroupPlan:
    name: str
    root: str
    memory_max: str
    pids_max: str
    cpu_max: str

    def path(self) -> str:
        return os.path.join(self.root, self.name)

    def write_files(self) -> Dict[str, str]:
        return {"memory.max": self.memory_max,
                "pids.max": self.pids_max,
                "cpu.max": self.cpu_max}

    def teardown_order(self) -> Tuple[str, ...]:
        return CGROUP_TEARDOWN_STEPS


def cgroup_plan(spec: SandboxSpec, name: str) -> CgroupPlan:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name or ""):
        raise SubstrateConfigError("cgroup name must be a safe token")
    return CgroupPlan(name=name, root=spec.cgroup_root,
                      memory_max=spec.memory_max, pids_max=spec.pids_max,
                      cpu_max=spec.cpu_max)


def termination_observed(events_text: str) -> bool:
    for line in events_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "populated":
            return parts[1] == "0"
    return False


def pid_starttime(stat_line: str) -> int:
    """Field 22 (starttime) from /proc/<pid>/stat (B5D: robust to comm noise)."""
    if not isinstance(stat_line, str):
        raise SubstrateConfigError("stat line must be a string")
    rparen = stat_line.rfind(")")
    if rparen < 0:
        raise SubstrateConfigError("malformed /proc/<pid>/stat")
    fields = stat_line[rparen + 1:].split()
    if len(fields) < 20:
        raise SubstrateConfigError("short /proc/<pid>/stat")
    try:
        return int(fields[19])
    except (TypeError, ValueError):
        raise SubstrateConfigError(
            "starttime field is not an integer") from None


# ---------------------------------------------------------------------------
# no_new_privs (B4)
# ---------------------------------------------------------------------------

#: NNP is REQUIRED by contract. GATE 3 probe observed `NoNewPrivs: 1` from
#: INSIDE the sandbox (`/proc/self/status` under bwrap 0.11.1). This proves
#: NNP for the probe sandbox shape; the RAPHAEL launcher must still read and
#: require it before any provider import.
NNP_REQUIRED = True
NNP_STATE = "OBSERVED_INSIDE_SANDBOX"


def nnp_requirement() -> Dict[str, Any]:
    return {
        "required": NNP_REQUIRED,
        "state": NNP_STATE,
        "mechanism": ("bwrap --cap-drop ALL plus a no_new_privs apply step "
                      "in the RAPHAEL launcher before provider import"),
        "observation": ("read /proc/self/status 'NoNewPrivs:' inside the "
                        "sandbox and require 1; the checklist MUST NOT mark "
                        "the sandbox live-ready without this observation"),
    }


def observe_no_new_privs(status_text: str) -> bool:
    """Parse /proc/self/status; true iff NoNewPrivs: 1 (observation)."""
    for line in (status_text or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "NoNewPrivs":
            return value.strip() == "1"
    return False


# ---------------------------------------------------------------------------
# seccomp policy (DRAFT — B2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeccompPolicy:
    status: str
    default_action: str
    arch: str
    allowed: Tuple[str, ...]
    denied: Tuple[str, ...]

    @property
    def is_production_ready(self) -> bool:
        return False   # never; must be curated + verified first

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "default_action": self.default_action,
                "arch": self.arch, "allowed": list(self.allowed),
                "denied": list(self.denied),
                "is_production_ready": self.is_production_ready}


#: INCOMPLETE draft allowlist (Node requires more; see MISSING_CANDIDATES).
_SECCOMP_ALLOWED: Tuple[str, ...] = (
    "read", "write", "openat", "close", "fstat", "newfstatat", "lseek",
    "mmap", "mprotect", "munmap", "brk", "rt_sigaction", "rt_sigprocmask",
    "rt_sigreturn", "ioctl", "pread64", "getpid", "getuid", "geteuid",
    "getgid", "getegid", "futex", "clock_gettime", "exit", "exit_group",
    "execve", "arch_prctl", "set_tid_address", "set_robust_list",
    "prlimit64", "uname", "readlink", "getrandom",
)

#: Explicitly denied escape / lateral channels.
_SECCOMP_DENIED: Tuple[str, ...] = (
    "socket", "connect", "bind", "listen", "accept", "sendto", "recvfrom",
    "ptrace", "process_vm_readv", "process_vm_writev", "mount", "umount2",
    "pivot_root", "chroot", "unshare", "setns", "kexec_load", "bpf",
    "io_uring_setup", "userfaultfd", "perf_event_open", "open_by_handle_at",
    "init_module", "finit_module", "delete_module", "keyctl", "add_key",
)

#: Node/runtime syscalls KNOWN to be missing from the draft allowlist.
MISSING_CANDIDATES: Tuple[str, ...] = (
    "epoll_create1", "epoll_ctl", "epoll_wait", "eventfd2", "pipe2", "dup",
    "dup2", "fcntl", "clone", "clone3", "getdents64", "statx", "timerfd_create",
    "timerfd_settime", "nanosleep", "sched_getaffinity", "sigaltstack",
)


def build_seccomp_policy() -> SeccompPolicy:
    return SeccompPolicy(
        status="DRAFT_NOT_PROVEN",
        default_action="SCMP_ACT_ERRNO(EPERM)",
        arch="SCMP_ARCH_X86_64",
        allowed=_SECCOMP_ALLOWED, denied=_SECCOMP_DENIED)


def seccomp_curation_methodology() -> Tuple[str, ...]:
    """Future empirical curation (NOT performed in this task)."""
    return (
        "run plain Node only, OUTSIDE T3MP3ST, under an instrumented "
        "environment (strace/audit)",
        "collect the syscalls Node actually requires at startup + runtime",
        "distinguish startup/runtime syscalls from unsafe capabilities",
        "convert the result into an explicit audited allowlist (deny default "
        "retained)",
        "perform a Node loader smoke test under the curated policy BEFORE any "
        "provider execution",
    )


def seccomp_install_description() -> Dict[str, Any]:
    return {
        "status": "DRAFT_NOT_PROVEN",
        "install": ("no_new_privs must be set BEFORE loading; the filter is "
                    "loaded by the RAPHAEL launcher (libseccomp/PR_SET_SECCOMP) "
                    "inside the sandbox, before provider import"),
        "denies": list(_SECCOMP_DENIED),
        "missing_candidate_syscalls": list(MISSING_CANDIDATES),
        "curation_methodology": list(seccomp_curation_methodology()),
        "does_not_prove": ("not a kernel-escape guarantee; not proven "
                           "Node-compatible; attempts are refused, not "
                           "prevented upstream"),
    }


# ---------------------------------------------------------------------------
# Launcher seam
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LauncherContract:
    tool: str
    fixture_path: str
    call_id: str
    command: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "fixture_path": self.fixture_path,
                "call_id": self.call_id, "command": list(self.command),
                "generic_dispatcher": False}


def launcher_contract(spec: SandboxSpec, proof_session_id: str,
                      invocation_id: str) -> LauncherContract:
    if not proof_session_id or not invocation_id:
        raise SubstrateConfigError("proof_session_id and invocation_id required")
    seed = f"{proof_session_id}:{invocation_id}:{C1A_TOOL}:{spec.fixture.path}"
    call_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    return LauncherContract(tool=C1A_TOOL, fixture_path=spec.fixture.path,
                            call_id=call_id, command=command_argv(spec))


__all__ = [
    "ArbitraryInputError",
    "BWRAP",
    "C1A_TOOL",
    "CGROUP_TEARDOWN_STEPS",
    "CgroupPlan",
    "DEFAULT_TIMEOUT_SECONDS",
    "FIXTURE_SHA256",
    "FixtureRef",
    "LAUNCHER_ENTRY",
    "LauncherContract",
    "MISSING_CANDIDATES",
    "NODE_BUILTIN_ASSETS",
    "NODE_CLOSURE_LIBS",
    "NODE_INTERPRETER",
    "NODE_RUNTIME",
    "NNP_REQUIRED",
    "NNP_STATE",
    "NodeRuntimeClosure",
    "SYSTEM_LIBRARY_PREFIXES",
    "PROVIDER_PIN",
    "ProviderRef",
    "SANDBOX_GID",
    "SANDBOX_UID",
    "SCRATCH_FLAGS",
    "SCRATCH_MODE",
    "SandboxSpec",
    "SeccompPolicy",
    "SubstrateConfigError",
    "build_bwrap_argv",
    "build_seccomp_policy",
    "cgroup_plan",
    "command_argv",
    "ensure_fixture_literal",
    "ensure_tool_literal",
    "launcher_contract",
    "mount_contract",
    "network_contract",
    "nnp_requirement",
    "node_runtime_closure",
    "observe_no_new_privs",
    "pid_starttime",
    "process_contract",
    "seccomp_curation_methodology",
    "seccomp_install_description",
    "termination_observed",
    "validate_fixture_root",
    "validate_node_closure",
    "validate_sandbox_spec",
]
