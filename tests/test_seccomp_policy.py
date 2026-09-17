"""tests.test_seccomp_policy — Phase 2C G2/Gate C/D policy tests.

Verifies the CURATED policy is deny-by-default, minimally justified, and that
the BPF can actually be built with the installed libseccomp. No sandbox is
launched here and T3MP3ST is never involved.
"""
from __future__ import annotations

import unittest

from raphael_ibm_bob.seccomp_policy import (
    ARG_FILTERED,
    AUDIT_ARCH_X86_64,
    CURATED_ALLOWLIST,
    DENIED_SYSCALLS,
    ENOSYS,
    EPERM,
    SPECIAL_ACTIONS,
    Libseccomp,
    build_policy,
    allowed_syscall_names,
    scmp_errno,
)

#: Families that MUST remain denied even though Node may probe them.
FORBIDDEN_ALWAYS = (
    "socket", "socketpair", "connect", "bind", "listen", "accept", "sendto",
    "recvfrom", "setsockopt", "getsockopt",
    "ptrace", "process_vm_readv", "process_vm_writev",
    "mount", "umount2", "pivot_root", "chroot",
    "unshare", "setns", "open_tree", "move_mount", "fsopen", "fsmount",
    "fspick", "mount_setattr",
    "bpf", "perf_event_open", "userfaultfd",
    "io_uring_setup", "io_uring_enter", "io_uring_register",
    "kexec_load", "init_module", "finit_module", "delete_module",
    "keyctl", "add_key", "request_key",
    "landlock_create_ruleset", "open_by_handle_at", "name_to_handle_at",
    "memfd_create", "execveat", "openat2",
    "setuid", "setgid", "setgroups", "capset", "seccomp", "clone3",
)


class CuratedPolicy(unittest.TestCase):
    def test_1_deny_by_default_actions(self):
        self.assertEqual(scmp_errno(EPERM), 0x00050001)
        self.assertEqual(SPECIAL_ACTIONS["clone3"], ENOSYS)

    def test_2_forbidden_families_not_allowed(self):
        allowed = set(allowed_syscall_names())
        for name in FORBIDDEN_ALWAYS:
            self.assertNotIn(name, allowed, f"{name} must not be allowed")

    def test_3_denied_list_covers_forbidden_families(self):
        denied = set(DENIED_SYSCALLS)
        for name in ("socket", "ptrace", "mount", "unshare", "bpf",
                     "io_uring_setup", "memfd_create", "execveat", "keyctl",
                     "perf_event_open", "userfaultfd", "openat2", "setns",
                     "clone3", "open_tree", "move_mount", "landlock_restrict_self"):
            self.assertIn(name, denied)

    def test_4_every_allow_entry_is_justified(self):
        for entry in CURATED_ALLOWLIST:
            self.assertTrue(entry.classification)
            self.assertTrue(entry.reason)
            self.assertTrue(entry.evidence)

    def test_5_arg_filters_present_for_privileged_multiplexers(self):
        kinds = {(s, a, k) for (s, a, k, _v, _e) in ARG_FILTERED}
        self.assertIn(("clone", 0, "masked_eq"), kinds)
        self.assertIn(("prctl", 0, "eq"), kinds)
        self.assertIn(("ioctl", 1, "eq"), kinds)

    def test_6_clone_requires_thread_bits(self):
        clone = [f for f in ARG_FILTERED if f[0] == "clone"][0]
        _s, _a, kind, datum_a, datum_b = clone
        self.assertEqual(kind, "masked_eq")
        self.assertEqual(datum_a, datum_b)          # (flags & VM|THREAD) == VM|THREAD
        self.assertNotEqual(datum_a, 0)

    def test_7_wait4_allowed_for_bwrap_init(self):
        self.assertIn("wait4", allowed_syscall_names())

    def test_8_policy_builds_and_hashes(self):
        digests = build_policy()
        self.assertEqual(digests.arch, AUDIT_ARCH_X86_64)
        self.assertGreater(digests.bpf_bytes, 0)
        self.assertEqual(len(digests.bpf_sha256), 64)
        self.assertEqual(len(digests.allowlist_sha256), 64)
        self.assertEqual(digests.syscalls, len(CURATED_ALLOWLIST))

    def test_9_bpf_is_deterministic(self):
        first = build_policy()
        second = build_policy()
        self.assertEqual(first.bpf_sha256, second.bpf_sha256)
        self.assertEqual(first.allowlist_sha256, second.allowlist_sha256)

    def test_10_arch_is_x86_64_only(self):
        self.assertEqual(Libseccomp().arch_native(), AUDIT_ARCH_X86_64)


if __name__ == "__main__":
    unittest.main()
