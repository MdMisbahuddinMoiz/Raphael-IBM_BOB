"""raphael_ibm_bob.seccomp_policy — curated deny-by-default seccomp (G2).

Phase 2C Gate C/D. A MINIMAL, evidence-backed allowlist curated from plain
Node traces (loader + IO-shape smoke) taken inside the exact sandbox shape.
Nothing here is "Node might need it": every allowed syscall is present in the
recorded trace (or is a justified fallback, marked as such). Everything else
stays denied by the kernel via ``SCMP_ACT_ERRNO(EPERM)``.

The filter is exported as raw BPF with the ALREADY-INSTALLED
``libseccomp.so.2`` through a small, auditable ctypes wrapper that uses only
the documented symbols below. The BPF is handed to ``bwrap --seccomp FD`` so
the kernel applies it to the sandboxed process BEFORE the pinned Node command
is exec'd. This module never loads the filter itself and never runs anything.

Evidence:
- traces: ``/tmp/raphael_g2/out/{loader,io_shape}.trace`` (sha256 recorded in
  ``docs/integration/phase-2c-g2/``)
- inventory: ``docs/integration/phase-2c-g2/syscall-inventory.json``
"""
from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- libseccomp constants (documented ABI) --------------------------------
SCMP_ACT_KILL_PROCESS = 0x80000000
SCMP_ACT_ALLOW = 0x7FFF0000
_SCMP_ACT_ERRNO_BASE = 0x00050000

SCMP_CMP_EQ = 4
SCMP_CMP_MASKED_EQ = 7

#: Preferred library names, in order.
LIBSECCOMP_NAMES: Tuple[str, ...] = ("libseccomp.so.2", "libseccomp.so")

#: x86_64 audit arch (libseccomp native on this host).
AUDIT_ARCH_X86_64 = 0xC000003E

EPERM = 1
ENOSYS = 38

#: CLONE_NEW* bits that MUST NOT appear in a clone() flags argument.
CLONE_NEWMASK = (0x00020000 | 0x02000000 | 0x04000000 | 0x08000000 |
                 0x10000000 | 0x20000000 | 0x40000000)   # NS CGROUP UTS IPC USER PID NET
CLONE_VM = 0x00000100
CLONE_THREAD = 0x00010000

PR_SET_NAME = 15
IOCTL_FIONBIO = 0x5421
IOCTL_TCGETS2 = 0x802C542A


def scmp_errno(errno: int) -> int:
    return _SCMP_ACT_ERRNO_BASE | (errno & 0xFFFF)


class SeccompError(Exception):
    """Fail-closed seccomp construction error."""


class ScmpArgCmp(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]


@dataclass(frozen=True)
class AllowedSyscall:
    name: str
    classification: str
    reason: str
    evidence: str

    def to_dict(self) -> Dict[str, str]:
        return {"syscall": self.name, "classification": self.classification,
                "reason": self.reason, "evidence": self.evidence}


#: Curated allowlist. Every entry observed in the plain-Node traces unless the
#: evidence says "fallback" (justified, not observed).
CURATED_ALLOWLIST: Tuple[AllowedSyscall, ...] = (
    AllowedSyscall("execve", "loader", "bwrap execs the pinned Node binary after applying the filter", "loader.trace"),
    AllowedSyscall("brk", "memory", "heap growth", "loader.trace"),
    AllowedSyscall("mmap", "memory", "V8/loader mappings incl. JIT code space", "loader.trace"),
    AllowedSyscall("mprotect", "memory", "V8 JIT W^X transitions", "loader.trace"),
    AllowedSyscall("munmap", "memory", "mapping teardown", "loader.trace"),
    AllowedSyscall("madvise", "memory", "V8 heap advice", "loader.trace"),
    AllowedSyscall("arch_prctl", "loader", "glibc TLS/FS base setup", "loader.trace"),
    AllowedSyscall("set_tid_address", "loader", "glibc thread bookkeeping", "loader.trace"),
    AllowedSyscall("set_robust_list", "loader", "glibc robust futex list", "loader.trace"),
    AllowedSyscall("rseq", "loader", "glibc restartable sequences", "loader.trace"),
    AllowedSyscall("prlimit64", "loader", "glibc resource limit query", "loader.trace"),
    AllowedSyscall("futex", "threading", "libuv/V8 synchronization", "loader.trace"),
    AllowedSyscall("clone", "threading", "FALLBACK: glibc thread creation when clone3 returns ENOSYS (arg-filtered to CLONE_VM|CLONE_THREAD only, so fork() is denied)", "fallback-justified"),
    AllowedSyscall("wait4", "loader", "bwrap PID-1 sandbox init reaps the executed command (observed: bwrap init wait() EPERM without it)", "amended-observed"),
    AllowedSyscall("sched_getaffinity", "threading", "V8/libuv CPU count probe", "loader.trace"),
    AllowedSyscall("getpid", "identity-read", "process id query", "loader.trace"),
    AllowedSyscall("gettid", "identity-read", "thread id query", "loader.trace"),
    AllowedSyscall("getuid", "identity-read", "uid query (non-root sandbox identity)", "loader.trace"),
    AllowedSyscall("geteuid", "identity-read", "effective uid query", "loader.trace"),
    AllowedSyscall("getgid", "identity-read", "gid query", "loader.trace"),
    AllowedSyscall("getegid", "identity-read", "effective gid query", "loader.trace"),
    AllowedSyscall("capget", "info", "read-only capability query by V8/libuv; cannot change identity", "loader.trace"),
    AllowedSyscall("uname", "info", "kernel/arch probe", "loader.trace"),
    AllowedSyscall("getrandom", "info", "CSPRNG seeding", "loader.trace"),
    AllowedSyscall("getcwd", "info", "cwd query during module resolution", "loader.trace"),
    AllowedSyscall("statx", "io", "glibc stat on modern kernels (module resolution)", "io_shape.trace"),
    AllowedSyscall("newfstatat", "io", "stat of candidate module paths", "loader.trace"),
    AllowedSyscall("fstat", "io", "fd stat", "loader.trace"),
    AllowedSyscall("access", "io", "existence probe during module resolution", "loader.trace"),
    AllowedSyscall("openat", "io", "open scripts/data/libs (read-only mounts only)", "loader.trace"),
    AllowedSyscall("read", "io", "read fds/files", "loader.trace"),
    AllowedSyscall("pread64", "io", "positional read", "loader.trace"),
    AllowedSyscall("write", "io", "stdout/stderr emission", "loader.trace"),
    AllowedSyscall("lseek", "io", "fd seek", "loader.trace"),
    AllowedSyscall("close", "io", "fd close", "loader.trace"),
    AllowedSyscall("fcntl", "io", "fd flag management (glibc/libuv)", "loader.trace"),
    AllowedSyscall("readlink", "io", "symlink resolution (/proc/self/exe etc.)", "loader.trace"),
    AllowedSyscall("readlinkat", "io", "symlink resolution during module lookup", "loader.trace"),
    AllowedSyscall("pipe2", "io", "libuv internal pipe", "loader.trace"),
    AllowedSyscall("eventfd2", "io", "libuv async wakeup", "loader.trace"),
    AllowedSyscall("epoll_create1", "io", "libuv event loop", "loader.trace"),
    AllowedSyscall("epoll_ctl", "io", "libuv event loop registration", "loader.trace"),
    AllowedSyscall("epoll_pwait", "io", "libuv event loop wait", "loader.trace"),
    AllowedSyscall("rt_sigaction", "signals", "signal handler installation", "loader.trace"),
    AllowedSyscall("rt_sigprocmask", "signals", "signal mask management", "loader.trace"),
    AllowedSyscall("exit", "exit", "thread exit", "loader.trace"),
    AllowedSyscall("exit_group", "exit", "process exit", "loader.trace"),
)

#: Arg-filtered allows: (syscall, arg_index, kind, datum_a, datum_b).
#: ``eq`` matches (arg == datum_a). ``masked_eq`` matches
#: (arg & datum_a) == datum_b. clone requires the thread bits and forbids the
#: CLONE_NEW* namespace bits, so fork()/unshare-style clones are denied.
ARG_FILTERED: Tuple[Tuple[str, int, str, int, int], ...] = (
    ("clone", 0, "masked_eq", CLONE_VM | CLONE_THREAD, CLONE_VM | CLONE_THREAD),
    ("prctl", 0, "eq", PR_SET_NAME, 0),
    ("ioctl", 1, "eq", IOCTL_FIONBIO, 0),
    ("ioctl", 1, "eq", IOCTL_TCGETS2, 0),
)

#: Denied explicitly (documented intent). All are already denied by the
#: default action; listing them keeps the review auditable.
DENIED_SYSCALLS: Tuple[str, ...] = (
    "socket", "socketpair", "connect", "bind", "listen", "accept", "sendto",
    "recvfrom", "recvmsg", "sendmsg", "setsockopt", "getsockopt",
    "ptrace", "process_vm_readv", "process_vm_writev",
    "mount", "umount2", "pivot_root", "chroot", "open_tree", "move_mount",
    "fsopen", "fsmount", "fspick", "mount_setattr", "statmount", "listmount",
    "unshare", "setns", "clone3",
    "bpf", "perf_event_open", "userfaultfd",
    "io_uring_setup", "io_uring_enter", "io_uring_register",
    "kexec_load", "kexec_file_load", "init_module", "finit_module",
    "delete_module", "keyctl", "add_key", "request_key",
    "landlock_create_ruleset", "landlock_add_rule", "landlock_restrict_self",
    "open_by_handle_at", "name_to_handle_at", "memfd_create", "execveat",
    "pidfd_open", "pidfd_getfd", "pidfd_send_signal", "openat2",
    "setuid", "setgid", "setgroups", "setresuid", "setresgid", "capset",
    "seccomp", "inotify_init", "inotify_init1", "inotify_add_watch",
    "waitid", "sched_setaffinity", "setpriority", "vmsplice",
)

#: Special actions (deny with a specific, fallback-friendly errno).
SPECIAL_ACTIONS: Dict[str, int] = {"clone3": ENOSYS}


def allowed_syscall_names() -> Tuple[str, ...]:
    return tuple(entry.name for entry in CURATED_ALLOWLIST)


@dataclass(frozen=True)
class PolicyDigests:
    allowlist_sha256: str
    bpf_sha256: str
    bpf_bytes: int
    syscalls: int
    arch: int

    def to_dict(self) -> Dict[str, Any]:
        return {"allowlist_sha256": self.allowlist_sha256,
                "bpf_sha256": self.bpf_sha256, "bpf_bytes": self.bpf_bytes,
                "syscalls": self.syscalls, "arch": hex(self.arch)}


def allowlist_json() -> str:
    import json
    return json.dumps(
        {"allow": [e.to_dict() for e in CURATED_ALLOWLIST],
         "arg_filtered": [{"syscall": s, "arg": a, "kind": k,
                           "value": v, "extra": x}
                          for (s, a, k, v, x) in ARG_FILTERED],
         "denied": list(DENIED_SYSCALLS),
         "special": dict(SPECIAL_ACTIONS)},
        indent=2, sort_keys=True)


class Libseccomp:
    """Minimal ctypes wrapper over the already-installed libseccomp."""

    def __init__(self, library: Optional[str] = None) -> None:
        path = library or self._find()
        self.lib = ctypes.CDLL(path)
        self._bind()

    @staticmethod
    def _find() -> str:
        for name in LIBSECCOMP_NAMES:
            found = ctypes.util.find_library(name)
            if found:
                return found
            if os.path.exists("/usr/lib/x86_64-linux-gnu/" + name):
                return "/usr/lib/x86_64-linux-gnu/" + name
        raise SeccompError("libseccomp not available")

    def _bind(self) -> None:
        lib = self.lib
        lib.seccomp_init.argtypes = [ctypes.c_uint32]
        lib.seccomp_init.restype = ctypes.c_void_p
        lib.seccomp_release.argtypes = [ctypes.c_void_p]
        lib.seccomp_release.restype = None
        lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
        lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
        lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                         ctypes.c_int, ctypes.c_uint]
        lib.seccomp_rule_add.restype = ctypes.c_int
        lib.seccomp_rule_add_array.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
            ctypes.POINTER(ScmpArgCmp)]
        lib.seccomp_rule_add_array.restype = ctypes.c_int
        lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.seccomp_export_bpf.restype = ctypes.c_int
        lib.seccomp_arch_native.argtypes = []
        lib.seccomp_arch_native.restype = ctypes.c_uint32

    def arch_native(self) -> int:
        return int(self.lib.seccomp_arch_native())

    def resolve(self, name: str) -> int:
        nr = int(self.lib.seccomp_syscall_resolve_name(name.encode()))
        if nr < 0:
            raise SeccompError(f"libseccomp cannot resolve syscall {name!r}")
        return nr

    def build_bpf(self) -> bytes:
        lib = self.lib
        ctx = lib.seccomp_init(scmp_errno(EPERM))
        if not ctx:
            raise SeccompError("seccomp_init failed")
        try:
            for entry in CURATED_ALLOWLIST:
                rc = lib.seccomp_rule_add(ctx, SCMP_ACT_ALLOW,
                                          self.resolve(entry.name), 0)
                if rc != 0:
                    raise SeccompError(f"allow {entry.name} rc={rc}")
            for name, errno in SPECIAL_ACTIONS.items():
                rc = lib.seccomp_rule_add(ctx, scmp_errno(errno),
                                          self.resolve(name), 0)
                if rc != 0:
                    raise SeccompError(f"special {name} rc={rc}")
            for (name, arg, kind, value, extra) in ARG_FILTERED:
                op = SCMP_CMP_MASKED_EQ if kind == "masked_eq" else SCMP_CMP_EQ
                cmp = ScmpArgCmp(arg=arg, op=op, datum_a=value,
                                 datum_b=extra)
                rc = lib.seccomp_rule_add_array(
                    ctx, SCMP_ACT_ALLOW, self.resolve(name), 1,
                    ctypes.byref(cmp))
                if rc != 0:
                    raise SeccompError(f"arg filter {name} rc={rc}")
            fd, path = tempfile.mkstemp(prefix="raphael_bpf_")
            try:
                os.close(fd)
                out = os.open(path, os.O_WRONLY | os.O_TRUNC)
                try:
                    rc = lib.seccomp_export_bpf(ctx, out)
                finally:
                    os.close(out)
                if rc != 0:
                    raise SeccompError(f"seccomp_export_bpf rc={rc}")
                with open(path, "rb") as fh:
                    return fh.read()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        finally:
            lib.seccomp_release(ctx)


def build_policy(export_path: Optional[str] = None) -> PolicyDigests:
    """Export the curated BPF (optionally to a file) and return its digests."""
    wrapper = Libseccomp()
    arch = wrapper.arch_native()
    if arch != AUDIT_ARCH_X86_64:
        raise SeccompError(f"unexpected native arch {hex(arch)}")
    bpf = wrapper.build_bpf()
    if not bpf:
        raise SeccompError("empty BPF")
    if export_path:
        with open(export_path, "wb") as fh:
            fh.write(bpf)
    return PolicyDigests(
        allowlist_sha256=hashlib.sha256(allowlist_json().encode()).hexdigest(),
        bpf_sha256=hashlib.sha256(bpf).hexdigest(),
        bpf_bytes=len(bpf), syscalls=len(CURATED_ALLOWLIST), arch=arch)


__all__ = [
    "AllowedSyscall", "ARG_FILTERED", "AUDIT_ARCH_X86_64", "CLONE_NEWMASK",
    "CURATED_ALLOWLIST", "DENIED_SYSCALLS", "IOCTL_FIONBIO", "IOCTL_TCGETS2",
    "Libseccomp", "PR_SET_NAME", "PolicyDigests", "SPECIAL_ACTIONS",
    "SeccompError", "allowlist_json", "allowed_syscall_names", "build_policy",
    "scmp_errno",
]
