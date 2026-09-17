"""tests.test_isolation_substrate — Phase 2C substrate static tests.

Static/structural only. NO bwrap launch, NO cgroup creation, NO seccomp
load, NO provider execution, NO M1/M2/M5 probes.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.isolation_substrate import (
    C1A_TOOL,
    CGROUP_TEARDOWN_STEPS,
    FIXTURE_SHA256,
    PROVIDER_PIN,
    SANDBOX_GID,
    SANDBOX_UID,
    ArbitraryInputError,
    FixtureRef,
    ProviderRef,
    SandboxSpec,
    SubstrateConfigError,
    build_bwrap_argv,
    build_seccomp_policy,
    cgroup_plan,
    ensure_fixture_literal,
    ensure_tool_literal,
    launcher_contract,
    mount_contract,
    network_contract,
    pid_starttime,
    process_contract,
    seccomp_install_description,
    termination_observed,
    validate_sandbox_spec,
)


def _tree(tc):
    base = Path(tempfile.mkdtemp(prefix="iso_"))
    tc.addCleanup(shutil.rmtree, base, True)
    provider = base / "provider"
    (provider / ".git").mkdir(parents=True)
    (provider / ".git" / "HEAD").write_text(PROVIDER_PIN + "\n")
    (provider / "node_modules").mkdir()
    (provider / "src").mkdir()
    fixture_root = base / "fixture_root"
    fixture_root.mkdir()
    fixture = fixture_root / "raphael_c1a_fixture.txt"
    fixture.write_bytes(b"RAPHAEL C1A FIXTURE TEST\n")
    sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return base, provider, fixture_root, fixture, sha


def _spec(provider, fixture_root, fixture, sha):
    return SandboxSpec(
        provider=ProviderRef(root=str(provider),
                             node_modules=str(provider / "node_modules")),
        fixture=FixtureRef(root=str(fixture_root), path=str(fixture),
                           sha256=sha))


class SubstrateStatic(unittest.TestCase):
    def setUp(self) -> None:
        self.base, self.provider, self.froot, self.fx, self.sha = _tree(self)
        self.spec = _spec(self.provider, self.froot, self.fx, self.sha)

    def test_1_exact_mount_specification(self):
        mounts = mount_contract(self.spec)
        self.assertEqual(
            [(m["kind"], m["dest"]) for m in mounts],
            [("ro-bind", "/provider"),
             ("ro-bind", "/provider/node_modules"),
             ("ro-bind", "/fixture"),
             ("dev", "/dev"), ("proc", "/proc"), ("tmpfs", "/tmp")])

    def test_2_fixture_only_visibility(self):
        mounts = mount_contract(self.spec)
        fixture_binds = [m for m in mounts if m["dest"] == "/fixture"]
        self.assertEqual(len(fixture_binds), 1)
        self.assertEqual(fixture_binds[0]["src"], self.spec.fixture.root)
        self.assertEqual(ensure_fixture_literal(self.spec, str(self.fx)),
                         str(self.fx))

    def test_3_provider_source_read_only(self):
        p = [m for m in mount_contract(self.spec) if m["dest"] == "/provider"][0]
        self.assertEqual(p["mode"], "ro")

    def test_4_node_modules_read_only(self):
        nm = [m for m in mount_contract(self.spec)
              if m["dest"] == "/provider/node_modules"][0]
        self.assertEqual(nm["mode"], "ro")

    def test_5_scratch_size_and_flags(self):
        tmp = [m for m in mount_contract(self.spec) if m["dest"] == "/tmp"][0]
        self.assertEqual(tmp["kind"], "tmpfs")
        self.assertIn(f"size={self.spec.scratch_bytes}", tmp["mode"])
        for flag in ("noexec", "nosuid", "nodev"):
            self.assertIn(flag, tmp["mode"])

    def test_6_no_host_home_mount(self):
        home = os_home()
        for m in mount_contract(self.spec):
            self.assertNotEqual(m["src"], home)
            self.assertNotIn(home + "/", m["src"])

    def test_7_no_docker_socket(self):
        argv = " ".join(build_bwrap_argv(self.spec))
        self.assertNotIn("docker.sock", argv.lower())
        for m in mount_contract(self.spec):
            self.assertNotIn("docker", m["src"].lower())

    def test_8_network_namespace_specification(self):
        net = network_contract(self.spec)
        self.assertTrue(net["unshare_net"])
        self.assertFalse(net["host_interfaces"])
        self.assertFalse(net["dns_config"])
        self.assertFalse(net["host_routes"])
        self.assertFalse(net["share_host_netns"])
        self.assertIn("--unshare-net", build_bwrap_argv(self.spec))

    def test_9_uid_gid_configuration(self):
        proc = process_contract(self.spec)
        self.assertEqual(proc["uid"], SANDBOX_UID)
        self.assertEqual(proc["gid"], SANDBOX_GID)
        self.assertTrue(proc["non_root"])
        argv = build_bwrap_argv(self.spec)
        self.assertIn("--unshare-user", argv)
        self.assertIn(str(SANDBOX_UID), argv)

    def test_10_capability_drop_specification(self):
        argv = list(build_bwrap_argv(self.spec))
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertTrue(process_contract(self.spec)["cap_drop_all"])

    def test_11_no_new_privs_specification(self):
        self.assertTrue(process_contract(self.spec)["no_new_privs"])
        self.assertTrue(process_contract(self.spec)["die_with_parent"])
        self.assertTrue(process_contract(self.spec)["new_session"])

    def test_12_cgroup_limit_specification(self):
        plan = cgroup_plan(self.spec, "c1a-proof-1")
        self.assertEqual(plan.write_files(),
                         {"memory.max": self.spec.memory_max,
                          "pids.max": self.spec.pids_max,
                          "cpu.max": self.spec.cpu_max})
        self.assertTrue(plan.path().startswith(self.spec.cgroup_root))

    def test_13_cgroup_kill_configuration(self):
        order = CGROUP_TEARDOWN_STEPS
        self.assertIn("write cgroup.kill (LOAD-BEARING)", order)
        self.assertLess(order.index("write cgroup.kill (LOAD-BEARING)"),
                        order.index("wait for cgroup.events populated=0"))
        self.assertIn("only then cancellation_acknowledged=true", order)

    def test_14_pid_anti_reuse_metadata(self):
        # field 3 = state, field 4 = ppid, ... field 22 = starttime
        tokens = ["S", "1"] + [str(1000 + i) for i in range(19)]
        tokens[19] = "987654321"          # 20th token after comm == field 22
        stat = "4242 (node) " + " ".join(tokens)
        self.assertEqual(pid_starttime(stat), 987654321)
        with self.assertRaises(SubstrateConfigError):
            pid_starttime("garbage")

    def test_15_deterministic_timeout_configuration(self):
        self.assertEqual(self.spec.timeout_seconds, 30.0)
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(SandboxSpec(
                provider=self.spec.provider, fixture=self.spec.fixture,
                timeout_seconds=0))

    def test_16_seccomp_policy_construction(self):
        policy = build_seccomp_policy()
        self.assertTrue(policy.default_action.startswith("SCMP_ACT_ERRNO"))
        for denied in ("socket", "ptrace", "mount", "open_by_handle_at"):
            self.assertIn(denied, policy.denied)
        for allowed in ("openat", "read", "fstat"):
            self.assertIn(allowed, policy.allowed)
        desc = seccomp_install_description()
        self.assertIn("does_not_prove", desc)
        self.assertIn("no_new_privs", desc["install"])

    def test_17_fail_closed_malformed_configuration(self):
        for bad in (
            SandboxSpec(provider=ProviderRef(root="relative", node_modules=(
                self.provider / "node_modules").as_posix()),
                fixture=self.spec.fixture),
            SandboxSpec(provider=self.spec.provider,
                        fixture=FixtureRef(root=str(self.froot),
                                           path=str(self.froot), sha256=self.sha)),
            SandboxSpec(provider=self.spec.provider, fixture=self.spec.fixture,
                        scratch_bytes=0),
            SandboxSpec(provider=self.spec.provider, fixture=self.spec.fixture,
                        uid=0),
            SandboxSpec(provider=ProviderRef(root=str(self.provider),
                                             node_modules=str(
                                                 self.provider / "node_modules"),
                                             pin="short"),
                        fixture=self.spec.fixture),
        ):
            with self.assertRaises(SubstrateConfigError):
                validate_sandbox_spec(bad)

    def test_18_forbidden_arbitrary_path_input(self):
        with self.assertRaises(ArbitraryInputError):
            ensure_fixture_literal(self.spec, "/etc/hostname")
        with self.assertRaises(ArbitraryInputError):
            ensure_fixture_literal(self.spec, str(self.froot) + "/other.txt")

    def test_19_forbidden_arbitrary_tool_input(self):
        self.assertEqual(ensure_tool_literal(C1A_TOOL), C1A_TOOL)
        for bad in ("nmap", "subprocess", "shell", ""):
            with self.assertRaises(ArbitraryInputError):
                ensure_tool_literal(bad)

    def test_20_provider_pin_verification(self):
        ref = ProviderRef(root=str(self.provider),
                          node_modules=str(self.provider / "node_modules"))
        ok, head = ref.verify_pin()
        self.assertTrue(ok, head)
        self.assertEqual(head, PROVIDER_PIN)
        (self.provider / ".git" / "HEAD").write_text("0" * 40 + "\n")
        ok2, _ = ref.verify_pin()
        self.assertFalse(ok2)

    def test_21_fixture_sha_verification(self):
        ref = FixtureRef(root=str(self.froot), path=str(self.fx), sha256=self.sha)
        self.assertEqual(ref.verify(), (True, self.sha))
        wrong = FixtureRef(root=str(self.froot), path=str(self.fx),
                           sha256="0" * 64)
        self.assertFalse(wrong.verify()[0])
        self.assertEqual(FIXTURE_SHA256,
                         "c033fda6e893ed965de8496ad170628d33ce69817c6ad0"
                         "5bbb63bcb5e1010bd1")

    def test_22_no_accidental_writable_provider_paths(self):
        argv = build_bwrap_argv(self.spec)
        joined = " ".join(argv)
        self.assertNotIn("--bind", argv)          # only --ro-bind / tmpfs
        for m in mount_contract(self.spec):
            if m["dest"].startswith("/provider"):
                self.assertEqual(m["mode"], "ro")
            self.assertNotEqual(m["mode"], "rw")

    def test_launcher_seam_contract(self):
        c = launcher_contract(self.spec, "PS-1", "INV-1")
        self.assertEqual(c.tool, C1A_TOOL)
        self.assertEqual(c.fixture_path, str(self.fx))
        self.assertFalse(c.to_dict()["generic_dispatcher"])
        # deterministic single RAPHAEL-owned call_id
        self.assertEqual(c.call_id, launcher_contract(self.spec, "PS-1",
                                                      "INV-1").call_id)
        with self.assertRaises(SubstrateConfigError):
            launcher_contract(self.spec, "", "")

    def test_termination_observation_parser(self):
        self.assertTrue(termination_observed("populated 0\nfrozen 0\n"))
        self.assertFalse(termination_observed("populated 1\n"))
        self.assertFalse(termination_observed("populated 2\n"))
        self.assertFalse(termination_observed("frozen 0\n"))


def os_home() -> str:
    from pathlib import Path as _P
    return str(_P.home())


if __name__ == "__main__":
    unittest.main()
