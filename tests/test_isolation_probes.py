"""tests.test_isolation_probes — safe isolation-contract probes.

These probes are STATIC: they inspect the constructed sandbox contract and
never launch bwrap or the provider.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.isolation_substrate import (  # noqa: E402
    FIXTURE_SHA256,
    PROVIDER_PIN,
    SubstrateConfigError,
    FixtureRef,
    ProviderRef,
    SandboxSpec,
    build_bwrap_argv,
    cgroup_plan,
    network_contract,
    pid_starttime,
    process_contract,
    termination_observed,
    validate_fixture_root,
    validate_sandbox_spec,
)


def _spec(tmp: str):
    root = Path(tmp)
    provider_root = root / "provider_root"
    (provider_root / "node_modules").mkdir(parents=True)
    (provider_root / ".git").mkdir()
    (provider_root / ".git" / "HEAD").write_text(PROVIDER_PIN)
    fixture_root = root / "fixture_root"
    fixture_root.mkdir()
    fixture = fixture_root / "sink.bin"
    fixture.write_bytes(b"RAPHAEL-FIXTURE\n")
    spec = SandboxSpec(
        provider=ProviderRef(root=str(provider_root),
                             node_modules=str(provider_root / "node_modules")),
        fixture=FixtureRef(root=str(fixture_root), path=str(fixture)),
    )
    return spec


class SandboxProbes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c1a_iso_")
        self.addCleanup(self.tmp.cleanup)
        self.spec = _spec(self.tmp.name)

    def test_spec_validates(self):
        validate_sandbox_spec(self.spec)
        validate_fixture_root(self.spec)

    def test_bwrap_denies_network(self):
        argv = build_bwrap_argv(self.spec)
        self.assertIn("--unshare-net", argv)

    def test_bwrap_drops_all_caps_and_is_nonroot(self):
        argv = build_bwrap_argv(self.spec)
        self.assertIn("--cap-drop", argv)
        self.assertIn("ALL", argv)
        self.assertIn("--unshare-user", argv)
        self.assertIn("--unshare-pid", argv)

    def test_bwrap_binds_exact_fixture_file_only(self):
        argv = list(build_bwrap_argv(self.spec))
        dest = "/fixture/" + Path(self.spec.fixture.path).name
        self.assertIn(dest, argv)
        # The fixture ROOT directory is never bound as a tree.
        self.assertNotIn(self.spec.fixture.root, argv)

    def test_bwrap_has_no_scratch_tmpfs(self):
        argv = build_bwrap_argv(self.spec)
        self.assertNotIn("--tmpfs", argv)

    def test_bwrap_unsets_proxy_env(self):
        argv = list(build_bwrap_argv(self.spec))
        self.assertIn("--unsetenv", argv)
        self.assertIn("HTTP_PROXY", argv)

    def test_seccomp_fd_is_injected(self):
        argv = list(build_bwrap_argv(self.spec, seccomp_fd=7))
        idx = argv.index("--seccomp")
        self.assertEqual(argv[idx + 1], "7")

    def test_seccomp_fd_below_stdio_rejected(self):
        for bad in (0, 1, 2, True, "7"):
            with self.assertRaises(SubstrateConfigError):
                build_bwrap_argv(self.spec, seccomp_fd=bad)

    def test_network_contract_is_denied(self):
        contract = network_contract(self.spec)
        self.assertTrue(contract["unshare_net"])
        self.assertFalse(contract["host_interfaces"])
        self.assertFalse(contract["share_host_netns"])

    def test_process_contract_is_hardened(self):
        contract = process_contract(self.spec)
        self.assertTrue(contract["cap_drop_all"])
        self.assertTrue(contract["no_new_privs_required"])
        self.assertTrue(contract["non_root"])
        self.assertTrue(contract["die_with_parent"])

    def test_root_uid_rejected(self):
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(SandboxSpec(
                provider=self.spec.provider, fixture=self.spec.fixture, uid=0))

    def test_fixture_root_with_extra_file_rejected(self):
        (Path(self.spec.fixture.root) / "extra.txt").write_text("x")
        with self.assertRaises(SubstrateConfigError):
            validate_fixture_root(self.spec)

    def test_termination_observed_parsing(self):
        self.assertTrue(termination_observed("populated 0\n"))
        self.assertFalse(termination_observed("populated 1\n"))
        self.assertFalse(termination_observed("garbage\n"))

    def test_pid_starttime_parsing(self):
        stat = "1234 (node) S 1 1234 1234 0 -1 4194560 1 0 0 0 0 0 0 0 20 0 1 0 98765"
        self.assertEqual(pid_starttime(stat), 98765)

    def test_cgroup_plan_bounded(self):
        plan = cgroup_plan(self.spec, "c1a-run-1")
        self.assertEqual(plan.memory_max, self.spec.memory_max)
        self.assertEqual(plan.pids_max, self.spec.pids_max)
        with self.assertRaises(SubstrateConfigError):
            cgroup_plan(self.spec, "bad/name")

    def test_fixture_pin_is_hex64(self):
        self.assertEqual(len(FIXTURE_SHA256), 64)
        int(FIXTURE_SHA256, 16)


if __name__ == "__main__":
    unittest.main()
