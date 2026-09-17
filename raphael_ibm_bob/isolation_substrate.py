"""raphael_ibm_bob.isolation_substrate — Phase 2C isolation substrate.

Concrete, auditable **construction layer** for the C1A first-proof sandbox.

    RAPHAEL core -> ProviderRuntime -> RAPHAEL launcher
      -> SEPARATE sandbox OS process (bwrap + userns + netns + cgroup v2 + seccomp)
      -> T3MP3ST -> bounded transcript -> receipt parser -> B4 -> gate

This module BUILDS the contracts (bwrap argv, mount table, cgroup plan,
seccomp policy, launcher seam) and VALIDATES them statically. It performs
**no execution**: it never launches bwrap, never creates a cgroup, never
loads a seccomp filter, never spawns a provider, never runs probes.

Scope of truth (recorded honestly):

    M1 (filesystem containment)  NOT CLOSED — design only; escape probes owed.
    M2 (network denial)          NOT CLOSED — design only; egress probes owed.
    M5 (teardown observation)    NOT CLOSED — cgroup plan only; live proof owed.

No security property is claimed that bwrap/Linux does not actually provide.
"""
from __future__ import annotations

import hashlib
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

#: Non-root identity inside the user namespace.
SANDBOX_UID = 65534
SANDBOX_GID = 65534

#: Concrete default bounds.
DEFAULT_SCRATCH_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MEMORY_MAX = "256M"
DEFAULT_PIDS_MAX = "64"
DEFAULT_CPU_MAX = "50000 100000"      # 0.5 CPU (quota/period)

#: bwrap program (never executed by this module).
BWRAP = "bwrap"


class SubstrateConfigError(Exception):
    """Fail-closed configuration error for the isolation substrate."""


class ArbitraryInputError(SubstrateConfigError):
    """A caller supplied a tool/path outside the hardcoded contract."""


def _canonical(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _abs(path: str) -> bool:
    return bool(path) and os.path.isabs(path) and _canonical(path) == path


# ---------------------------------------------------------------------------
# References + identity (static verification only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderRef:
    """Pinned provider checkout (read-only inside the sandbox)."""
    root: str
    node_modules: str
    pin: str = PROVIDER_PIN

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
            return self.head_sha() == self.pin, self.head_sha()
        except OSError as exc:
            return False, f"unreadable:{type(exc).__name__}"


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


# ---------------------------------------------------------------------------
# Sandbox specification + validation (fail-closed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxSpec:
    """Concrete first-proof sandbox. Constructed, never launched here."""
    provider: ProviderRef
    fixture: FixtureRef
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
    if not _abs(spec.fixture.root) or not _abs(spec.fixture.path):
        raise SubstrateConfigError("fixture paths must be canonical absolute")
    # Fixture must be a direct child of the RAPHAEL-owned root (single file).
    if os.path.dirname(spec.fixture.path) != spec.fixture.root:
        raise SubstrateConfigError(
            "fixture must be a direct child of fixture.root (no traversal)")
    if not spec.provider.pin or len(spec.provider.pin) != 40:
        raise SubstrateConfigError("provider pin must be a 40-char sha")
    if len(spec.fixture.sha256) != 64:
        raise SubstrateConfigError("fixture sha256 must be 64 hex chars")
    if not spec.cgroup_root.startswith("/sys/fs/cgroup"):
        raise SubstrateConfigError("cgroup_root must be under /sys/fs/cgroup")
    if spec.scratch_bytes <= 0 or spec.scratch_bytes > 256 * 1024 * 1024:
        raise SubstrateConfigError("scratch_bytes must be 0 < x <= 256MiB")
    if spec.timeout_seconds <= 0 or spec.timeout_seconds > 600:
        raise SubstrateConfigError("timeout must be 0 < x <= 600s")
    if spec.uid == 0 or spec.gid == 0:
        raise SubstrateConfigError("sandbox uid/gid must be non-root")
    for name, value in (("memory_max", spec.memory_max),
                        ("pids_max", spec.pids_max),
                        ("cpu_max", spec.cpu_max)):
        if not isinstance(value, str) or not value.strip():
            raise SubstrateConfigError(f"cgroup {name} must be set")


def ensure_tool_literal(tool: str) -> str:
    """Only the hardcoded C1A tool is ever accepted."""
    if tool != C1A_TOOL:
        raise ArbitraryInputError(
            f"tool {tool!r} is outside the C1A contract")
    return tool


def ensure_fixture_literal(spec: SandboxSpec, path: str) -> str:
    """Only the exact fixture literal is ever accepted (no arbitrary paths)."""
    if path != spec.fixture.path:
        raise ArbitraryInputError(
            f"path {path!r} is not the exact fixture literal")
    return path


# ---------------------------------------------------------------------------
# bwrap contract
# ---------------------------------------------------------------------------

def mount_contract(spec: SandboxSpec) -> Tuple[Dict[str, str], ...]:
    """Read-only mounts + the single bounded writable scratch."""
    return (
        {"kind": "ro-bind", "src": spec.provider.root, "dest": "/provider",
         "mode": "ro"},
        {"kind": "ro-bind", "src": spec.provider.node_modules,
         "dest": "/provider/node_modules", "mode": "ro"},
        {"kind": "ro-bind", "src": spec.fixture.root, "dest": "/fixture",
         "mode": "ro"},
        {"kind": "dev", "src": "dev", "dest": "/dev", "mode": "minimal"},
        {"kind": "proc", "src": "proc", "dest": "/proc", "mode": "private"},
        {"kind": "tmpfs", "src": "tmpfs", "dest": "/tmp",
         "mode": f"size={spec.scratch_bytes},noexec,nosuid,nodev"},
    )


def network_contract(spec: SandboxSpec) -> Dict[str, Any]:
    """Private network namespace: no host ifaces/DNS/routes (M2 design)."""
    return {"unshare_net": True, "host_interfaces": False,
            "dns_config": False, "host_routes": False,
            "share_host_netns": False}


def process_contract(spec: SandboxSpec) -> Dict[str, Any]:
    return {"unshare_user": True, "uid": spec.uid, "gid": spec.gid,
            "non_root": True, "cap_drop_all": True, "no_new_privs": True,
            "die_with_parent": True, "new_session": True,
            "unshare_pid": True, "unshare_ipc": True, "unshare_uts": True}


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
        "--ro-bind", spec.fixture.root, "/fixture",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--chdir", "/provider",
        "--",
    ]
    return tuple(argv)


# ---------------------------------------------------------------------------
# cgroup v2 contract (M5 machinery; no live teardown proof here)
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
    """Concrete cgroup v2 limits for the sandbox workload."""
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
    """Parse cgroup.events: termination observed iff `populated 0`."""
    for line in events_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "populated":
            return parts[1] == "0"
    return False


def pid_starttime(stat_line: str) -> int:
    """Extract field 22 (starttime) from /proc/<pid>/stat (anti-reuse)."""
    rparen = stat_line.rfind(")")
    if rparen < 0:
        raise SubstrateConfigError("malformed /proc/<pid>/stat")
    fields = stat_line[rparen + 2:].split()
    if len(fields) < 20:
        raise SubstrateConfigError("short /proc/<pid>/stat")
    return int(fields[19])   # field 22 overall; 20th after comm/state


# ---------------------------------------------------------------------------
# seccomp policy (specification; compiled/loaded only at the live stage)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeccompPolicy:
    """Deterministic deny-by-default seccomp policy specification."""
    default_action: str
    arch: str
    allowed: Tuple[str, ...]
    denied: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"default_action": self.default_action, "arch": self.arch,
                "allowed": list(self.allowed), "denied": list(self.denied)}


#: Minimum syscalls for a single-file reader under node (read-only).
_SECCOMP_ALLOWED: Tuple[str, ...] = (
    "read", "write", "openat", "close", "fstat", "newfstatat", "lseek",
    "mmap", "mprotect", "munmap", "brk", "rt_sigaction", "rt_sigprocmask",
    "rt_sigreturn", "ioctl", "pread64", "getpid", "getuid", "geteuid",
    "getgid", "getegid", "futex", "clock_gettime", "exit", "exit_group",
    "execve", "arch_prctl", "set_tid_address", "set_robust_list",
    "prlimit64", "uname", "readlink", "getrandom",
)

#: Denied outright (escape / lateral channels).
_SECCOMP_DENIED: Tuple[str, ...] = (
    "socket", "connect", "bind", "listen", "accept", "sendto", "recvfrom",
    "ptrace", "process_vm_readv", "process_vm_writev", "mount", "umount2",
    "pivot_root", "chroot", "unshare", "setns", "kexec_load", "bpf",
    "io_uring_setup", "userfaultfd", "perf_event_open", "open_by_handle_at",
    "init_module", "finit_module", "delete_module", "keyctl", "add_key",
)


def build_seccomp_policy() -> SeccompPolicy:
    return SeccompPolicy(default_action="SCMP_ACT_ERRNO(EPERM)",
                         arch="SCMP_ARCH_X86_64",
                         allowed=_SECCOMP_ALLOWED, denied=_SECCOMP_DENIED)


def seccomp_install_description() -> Dict[str, Any]:
    """How the policy is installed + what it does/does not prove."""
    return {
        "install": ("no_new_privs must be set (bwrap --cap-drop ALL + "
                    "PR_SET_NO_NEW_PRIVS) BEFORE loading; filter loaded by "
                    "the RAPHAEL launcher via libseccomp/prctl(PR_SET_SECCOMP) "
                    "inside the sandbox, before provider code runs"),
        "denies": list(_SECCOMP_DENIED),
        "necessary_categories": {
            "file-read": "openat/read/fstat/newfstatat/lseek/pread64",
            "memory": "mmap/mprotect/munmap/brk",
            "runtime": "execve(to start node)/arch_prctl/futex/clock_gettime",
            "teardown": "exit/exit_group",
        },
        "does_not_prove": ("not a kernel-escape guarantee; not a proof that "
                           "the provider cannot attempt denied syscalls "
                           "(attempts are refused, not prevented upstream)"),
        "staging_trust_boundary": ("policy install happens AFTER entering the "
                                   "sandbox and BEFORE provider import; the "
                                   "staging bootstrap is RAPHAEL-owned"),
    }


# ---------------------------------------------------------------------------
# Launcher seam (contract only; not executed against T3MP3ST here)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LauncherContract:
    """Frozen contract the future RAPHAEL launcher must satisfy."""
    tool: str
    fixture_path: str
    call_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "fixture_path": self.fixture_path,
                "call_id": self.call_id,
                "generic_dispatcher": False}


def launcher_contract(spec: SandboxSpec, proof_session_id: str,
                      invocation_id: str) -> LauncherContract:
    """Synthesize the single RAPHAEL-owned call_id (deterministic)."""
    if not proof_session_id or not invocation_id:
        raise SubstrateConfigError("proof_session_id and invocation_id required")
    seed = f"{proof_session_id}:{invocation_id}:{C1A_TOOL}:{spec.fixture.path}"
    call_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    return LauncherContract(tool=C1A_TOOL, fixture_path=spec.fixture.path,
                            call_id=call_id)


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
    "LauncherContract",
    "PROVIDER_PIN",
    "ProviderRef",
    "SANDBOX_GID",
    "SANDBOX_UID",
    "SandboxSpec",
    "SeccompPolicy",
    "SubstrateConfigError",
    "build_bwrap_argv",
    "build_seccomp_policy",
    "cgroup_plan",
    "ensure_fixture_literal",
    "ensure_tool_literal",
    "launcher_contract",
    "mount_contract",
    "network_contract",
    "pid_starttime",
    "process_contract",
    "seccomp_install_description",
    "termination_observed",
    "validate_sandbox_spec",
]
