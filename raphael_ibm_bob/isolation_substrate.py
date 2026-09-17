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

#: The future RAPHAEL-owned launcher entry (read-only); NOT executed here.
LAUNCHER_ENTRY = "/provider/c1a_launcher.js"

#: Non-root identity inside the user namespace.
SANDBOX_UID = 65534
SANDBOX_GID = 65534

#: Scratch bounds (B1).
DEFAULT_SCRATCH_BYTES = 16 * 1024 * 1024
MAX_SCRATCH_BYTES = 256 * 1024 * 1024

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
# Sandbox specification + validation (fail-closed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxSpec:
    """Concrete first-proof sandbox. Constructed, never launched here."""
    provider: ProviderRef
    fixture: FixtureRef
    node_runtime: str = NODE_RUNTIME
    launcher_entry: str = LAUNCHER_ENTRY
    scratch_bytes: int = DEFAULT_SCRATCH_BYTES
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
    _finite_positive(spec.scratch_bytes, "scratch_bytes",
                     maximum=MAX_SCRATCH_BYTES)
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

#: Scratch property claims and their ACTUAL state (B1). Only `size` is
#: enforced in the argv; the rest are residual/unproven.
SCRATCH_FLAGS = {
    "size": "ENFORCED",
    "noexec": "RESIDUAL_UNPROVEN",
    "nosuid": "RESIDUAL_UNPROVEN",
    "nodev": "RESIDUAL_UNPROVEN",
}


def mount_contract(spec: SandboxSpec) -> Tuple[Dict[str, Any], ...]:
    """Read-only mounts + the single bounded scratch + pinned runtime.

    The fixture is bound as the EXACT single file (B5C), not the whole root.
    """
    return (
        {"kind": "ro-bind", "src": spec.provider.root, "dest": "/provider",
         "mode": "ro"},
        {"kind": "ro-bind", "src": spec.provider.node_modules,
         "dest": "/provider/node_modules", "mode": "ro"},
        {"kind": "ro-bind", "src": spec.fixture.path,
         "dest": "/fixture/" + os.path.basename(spec.fixture.path),
         "mode": "ro"},
        {"kind": "ro-bind", "src": spec.node_runtime,
         "dest": spec.node_runtime, "mode": "ro"},
        {"kind": "dev", "src": "dev", "dest": "/dev", "mode": "minimal"},
        {"kind": "proc", "src": "proc", "dest": "/proc", "mode": "private"},
        {"kind": "tmpfs", "src": "tmpfs", "dest": "/tmp",
         "size": spec.scratch_bytes, "flags": dict(SCRATCH_FLAGS)},
    )


def network_contract(spec: SandboxSpec) -> Dict[str, Any]:
    return {"unshare_net": True, "host_interfaces": False,
            "dns_config": False, "host_routes": False,
            "share_host_netns": False}


def process_contract(spec: SandboxSpec) -> Dict[str, Any]:
    return {"unshare_user": True, "uid": spec.uid, "gid": spec.gid,
            "non_root": True, "cap_drop_all": True,
            "no_new_privs_required": True,
            "no_new_privs_state": "NOT_YET_PROVEN",
            "die_with_parent": True, "new_session": True,
            "unshare_pid": True, "unshare_ipc": True, "unshare_uts": True}


def command_argv(spec: SandboxSpec) -> Tuple[str, ...]:
    """The pinned, deterministic, non-caller-controllable executable (B3)."""
    return (spec.node_runtime, spec.launcher_entry)


def build_bwrap_argv(spec: SandboxSpec) -> Tuple[str, ...]:
    """Concrete, auditable bwrap argv. NOT executed by this module."""
    validate_sandbox_spec(spec)
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
        # sized tmpfs (B1): --size applies to the next --tmpfs
        "--size", str(spec.scratch_bytes),
        "--tmpfs", "/tmp",
        "--chdir", "/provider",
        "--",
    ]
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

#: NNP is REQUIRED by contract; its OBSERVED state inside the sandbox is not
#: yet proven and must be read from /proc/self/status before any live run.
NNP_REQUIRED = True
NNP_STATE = "NOT_YET_PROVEN"


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
    "DEFAULT_SCRATCH_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "FIXTURE_SHA256",
    "FixtureRef",
    "LAUNCHER_ENTRY",
    "LauncherContract",
    "MAX_SCRATCH_BYTES",
    "MISSING_CANDIDATES",
    "NODE_RUNTIME",
    "NNP_REQUIRED",
    "NNP_STATE",
    "PROVIDER_PIN",
    "ProviderRef",
    "SANDBOX_GID",
    "SANDBOX_UID",
    "SCRATCH_FLAGS",
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
    "observe_no_new_privs",
    "pid_starttime",
    "process_contract",
    "seccomp_curation_methodology",
    "seccomp_install_description",
    "termination_observed",
    "validate_fixture_root",
    "validate_sandbox_spec",
]
