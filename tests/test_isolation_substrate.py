"""tests.test_isolation_substrate — Phase 2C substrate static tests (B1-B5).

Static/structural only. NO bwrap launch, NO cgroup creation, NO seccomp
load, NO Node/provider execution, NO M1/M2/M5 probes.

Security properties that must exist in the ACTUAL construction are asserted
against `build_bwrap_argv(...)`, never against metadata strings alone.
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
    LAUNCHER_ENTRY,
    MISSING_CANDIDATES,
    NODE_CLOSURE_LIBS,
    NODE_INTERPRETER,
    NODE_RUNTIME,
    NNP_STATE,
    PROVIDER_PIN,
    SYSTEM_LIBRARY_PREFIXES,
    SANDBOX_GID,
    SANDBOX_UID,
    SCRATCH_FLAGS,
    ArbitraryInputError,
    FixtureRef,
    NodeRuntimeClosure,
    ProviderRef,
    SandboxSpec,
    SubstrateConfigError,
    build_bwrap_argv,
    build_seccomp_policy,
    cgroup_plan,
    command_argv,
    ensure_fixture_literal,
    ensure_tool_literal,
    launcher_contract,
    mount_contract,
    network_contract,
    nnp_requirement,
    node_runtime_closure,
    observe_no_new_privs,
    pid_starttime,
    process_contract,
    seccomp_curation_methodology,
    seccomp_install_description,
    termination_observed,
    validate_fixture_root,
    validate_node_closure,
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
    froot = base / "fixture_root"
    froot.mkdir()
    fx = froot / "raphael_c1a_fixture.txt"
    fx.write_bytes(b"RAPHAEL C1A FIXTURE TEST\n")
    sha = hashlib.sha256(fx.read_bytes()).hexdigest()
    return base, provider, froot, fx, sha


def _spec(provider, froot, fx, sha, **over):
    data = dict(
        provider=ProviderRef(root=str(provider),
                             node_modules=str(provider / "node_modules")),
        fixture=FixtureRef(root=str(froot), path=str(fx), sha256=sha))
    data.update(over)
    return SandboxSpec(**data)


class SubstrateStatic(unittest.TestCase):
    def setUp(self) -> None:
        self.base, self.provider, self.froot, self.fx, self.sha = _tree(self)
        self.spec = _spec(self.provider, self.froot, self.fx, self.sha)

    # --- B1: tmpfs must match the claims --------------------------------

    def test_1_tmpfs_size_enforced_in_actual_argv(self):
        argv = list(build_bwrap_argv(self.spec))
        i = argv.index("--tmpfs")
        self.assertEqual(argv[i], "--tmpfs")
        self.assertEqual(argv[i + 1], "/tmp")
        self.assertEqual(argv[i - 2], "--size")
        self.assertEqual(argv[i - 1], str(self.spec.scratch_bytes))

    def test_2_tmpfs_flags_observed_state_not_claimed_in_argv(self):
        joined = " ".join(build_bwrap_argv(self.spec))
        # bwrap --tmpfs cannot express per-mount noexec/nosuid/nodev in argv.
        for flag in ("noexec", "nosuid", "nodev"):
            self.assertNotIn(flag, joined, f"{flag} must not be claimed")
        # GATE 4 observed the real kernel state; noexec is NOT enforced.
        self.assertEqual(SCRATCH_FLAGS["size"], "OBSERVED_ENFORCED")
        self.assertEqual(SCRATCH_FLAGS["noexec"], "OBSERVED_NOT_ENFORCED")
        self.assertEqual(SCRATCH_FLAGS["nosuid"], "OBSERVED_ENFORCED")
        self.assertEqual(SCRATCH_FLAGS["nodev"], "OBSERVED_ENFORCED")

    def test_3_scratch_bounds_preserved(self):
        self.assertEqual(self.spec.scratch_bytes, 16 * 1024 * 1024)
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(_spec(self.provider, self.froot, self.fx,
                                        self.sha,
                                        scratch_bytes=256 * 1024 * 1024 + 1))

    # --- B2: seccomp DRAFT ----------------------------------------------

    def test_4_seccomp_is_marked_draft(self):
        policy = build_seccomp_policy()
        self.assertEqual(policy.status, "DRAFT_NOT_PROVEN")
        self.assertFalse(policy.is_production_ready)
        self.assertTrue(policy.default_action.startswith("SCMP_ACT_ERRNO"))
        for denied in ("socket", "ptrace", "mount", "unshare", "bpf"):
            self.assertIn(denied, policy.denied)

    def test_5_seccomp_draft_documents_missing_runtime_syscalls(self):
        self.assertGreater(len(MISSING_CANDIDATES), 0)
        for name in ("epoll_wait", "eventfd2", "clone", "getdents64"):
            self.assertIn(name, MISSING_CANDIDATES)
        desc = seccomp_install_description()
        self.assertEqual(desc["status"], "DRAFT_NOT_PROVEN")
        self.assertIn("missing_candidate_syscalls", desc)
        self.assertGreaterEqual(len(seccomp_curation_methodology()), 4)
        self.assertIn("does_not_prove", desc)

    # --- B3: executable + runtime ---------------------------------------

    def test_6_argv_has_pinned_executable(self):
        argv = list(build_bwrap_argv(self.spec))
        self.assertEqual(argv[-1], LAUNCHER_ENTRY)
        self.assertEqual(argv[-2], NODE_RUNTIME)
        self.assertTrue(argv[-2].startswith("/"))
        self.assertEqual(command_argv(self.spec),
                         (NODE_RUNTIME, LAUNCHER_ENTRY))
        self.assertTrue(len(command_argv(self.spec)) == 2)

    def test_7_argv_has_runtime_readonly_bind(self):
        argv = list(build_bwrap_argv(self.spec))
        for idx, token in enumerate(argv):
            if token == "--ro-bind" and argv[idx + 1] == NODE_RUNTIME:
                self.assertEqual(argv[idx + 2], NODE_RUNTIME)
                break
        else:
            self.fail("runtime read-only bind missing from argv")

    def test_8_executable_not_caller_controllable(self):
        bad = _spec(self.provider, self.froot, self.fx, self.sha,
                    node_runtime="/bin/sh")
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(bad)
        with self.assertRaises(SubstrateConfigError):
            build_bwrap_argv(bad)

    # --- GATE 1: Node runtime closure -----------------------------------

    def test_8a_every_closure_path_bound_explicitly_readonly(self):
        closure = node_runtime_closure()
        argv = list(build_bwrap_argv(self.spec))
        pairs = {}
        for idx, token in enumerate(argv):
            if token == "--ro-bind":
                pairs[argv[idx + 1]] = argv[idx + 2]
        self.assertIn(NODE_RUNTIME, pairs)
        self.assertIn(NODE_INTERPRETER, pairs)
        for lib in NODE_CLOSURE_LIBS:
            self.assertIn(lib, pairs)
            self.assertEqual(pairs[lib], lib)
        self.assertEqual(len(NODE_CLOSURE_LIBS), len(set(NODE_CLOSURE_LIBS)))
        self.assertIn("/usr/lib/x86_64-linux-gnu/libnode.so.127",
                      closure.libraries)

    def test_8b_no_library_tree_is_bound(self):
        argv = list(build_bwrap_argv(self.spec))
        for idx, token in enumerate(argv):
            if token == "--ro-bind":
                src = argv[idx + 1]
                self.assertNotIn(src, ("/usr/lib", "/lib", "/lib64", "/usr"),
                                 f"tree bind leaked: {src}")

    def test_8c_closure_paths_reject_caller_input(self):
        for bad in ("libnode.so.127", "/opt/evil.so",
                    "/usr/lib/x86_64-linux-gnu/../evil.so"):
            with self.assertRaises(SubstrateConfigError):
                validate_node_closure(NodeRuntimeClosure(
                    runtime=NODE_RUNTIME, interpreter=NODE_INTERPRETER,
                    libraries=(bad,)))
        with self.assertRaises(SubstrateConfigError):
            validate_node_closure(NodeRuntimeClosure(
                runtime=NODE_RUNTIME, interpreter=NODE_INTERPRETER,
                libraries=("/usr/lib/x86_64-linux-gnu/libc.so.6",) * 2))
        for prefix in SYSTEM_LIBRARY_PREFIXES:
            self.assertTrue(prefix.startswith("/"))

    # --- B4: no_new_privs requirement vs observation --------------------

    def test_9_nnp_requirement_distinct_from_observation(self):
        req = nnp_requirement()
        self.assertTrue(req["required"])
        # GATE 3 observed NoNewPrivs: 1 inside the probe sandbox.
        self.assertEqual(req["state"], "OBSERVED_INSIDE_SANDBOX")
        self.assertEqual(NNP_STATE, "OBSERVED_INSIDE_SANDBOX")
        proc = process_contract(self.spec)
        self.assertTrue(proc["no_new_privs_required"])
        self.assertEqual(proc["no_new_privs_state"], "OBSERVED_INSIDE_SANDBOX")

    def test_10_nnp_observation_parser(self):
        self.assertTrue(observe_no_new_privs("Name:\tnode\nNoNewPrivs:\t1\n"))
        self.assertFalse(observe_no_new_privs("NoNewPrivs:\t0\n"))
        self.assertFalse(observe_no_new_privs("Name:\tnode\n"))

    # --- B5: containment + numeric + parsing ----------------------------

    def test_11_numeric_validation_fail_closed(self):
        for bad in (True, False, float("nan"), float("inf"), float("-inf"),
                    0, -1, "5"):
            with self.assertRaises(SubstrateConfigError):
                validate_sandbox_spec(_spec(self.provider, self.froot,
                                            self.fx, self.sha,
                                            timeout_seconds=bad))
            with self.assertRaises(SubstrateConfigError):
                validate_sandbox_spec(_spec(self.provider, self.froot,
                                            self.fx, self.sha,
                                            scratch_bytes=bad))

    def test_12_node_modules_containment(self):
        outside = self.base / "outside_modules"
        outside.mkdir()
        bad = SandboxSpec(
            provider=ProviderRef(root=str(self.provider),
                                 node_modules=str(outside)),
            fixture=FixtureRef(root=str(self.froot), path=str(self.fx),
                               sha256=self.sha))
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(bad)

    def test_13_fixture_bound_as_exact_file(self):
        mounts = mount_contract(self.spec)
        binds = [m for m in mounts if m["kind"] == "ro-bind"
                 and m["dest"].startswith("/fixture")]
        self.assertEqual(len(binds), 1)
        self.assertEqual(binds[0]["src"], str(self.fx))
        self.assertEqual(binds[0]["dest"],
                         "/fixture/" + self.fx.name)

    def test_14_fixture_root_must_be_exactly_one_file(self):
        validate_fixture_root(self.spec)
        extra = self.froot / "extra.txt"
        extra.write_text("x")
        with self.assertRaises(SubstrateConfigError):
            validate_fixture_root(self.spec)

    def test_15_pid_parser_adversarial_comm(self):
        tokens = ["S", "1"] + [str(1000 + i) for i in range(19)]
        tokens[19] = "123456789"
        stat = "4242 (node (worker) [x]) " + " ".join(tokens)
        self.assertEqual(pid_starttime(stat), 123456789)

    def test_16_pid_parser_error_normalized(self):
        for bad in ("no-paren", "1 (x) S short", "1 (x) S " + " ".join(
                ["S"] + ["z"] * 25)):
            with self.assertRaises(SubstrateConfigError):
                pid_starttime(bad)

    # --- structural / existing contract ---------------------------------

    def test_17_exact_mount_specification(self):
        mounts = mount_contract(self.spec)
        closure = node_runtime_closure()
        expected = [("ro-bind", "/provider"),
                    ("ro-bind", "/provider/node_modules"),
                    ("ro-bind", "/fixture/" + self.fx.name),
                    ("ro-bind", NODE_RUNTIME)]
        expected += [("ro-bind", p)
                     for p in (closure.interpreter,) + closure.libraries]
        expected += [("dev", "/dev"), ("proc", "/proc"), ("tmpfs", "/tmp")]
        self.assertEqual([(m["kind"], m["dest"]) for m in mounts], expected)

    def test_18_provider_and_node_modules_read_only(self):
        mounts = mount_contract(self.spec)
        self.assertEqual([m["mode"] for m in mounts
                          if m["dest"] in ("/provider",
                                           "/provider/node_modules")],
                         ["ro", "ro"])
        argv = list(build_bwrap_argv(self.spec))
        self.assertNotIn("--bind", argv)

    def test_19_no_host_home_or_docker_socket(self):
        home = str(Path.home())
        joined = " ".join(build_bwrap_argv(self.spec))
        self.assertNotIn(home, joined)
        self.assertNotIn("docker.sock", joined.lower())
        for m in mount_contract(self.spec):
            self.assertNotIn("docker", str(m.get("src", "")).lower())

    def test_20_network_namespace_specification(self):
        net = network_contract(self.spec)
        self.assertFalse(net["host_interfaces"])
        self.assertFalse(net["dns_config"])
        self.assertFalse(net["share_host_netns"])
        self.assertIn("--unshare-net", build_bwrap_argv(self.spec))

    def test_21_process_uid_gid_caps(self):
        proc = process_contract(self.spec)
        self.assertEqual((proc["uid"], proc["gid"]),
                         (SANDBOX_UID, SANDBOX_GID))
        self.assertTrue(proc["non_root"] and proc["cap_drop_all"])
        self.assertTrue(proc["die_with_parent"] and proc["new_session"])
        argv = list(build_bwrap_argv(self.spec))
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")

    def test_22_cgroup_limits_and_kill_order(self):
        plan = cgroup_plan(self.spec, "c1a-proof-1")
        self.assertEqual(plan.write_files(),
                         {"memory.max": self.spec.memory_max,
                          "pids.max": self.spec.pids_max,
                          "cpu.max": self.spec.cpu_max})
        order = CGROUP_TEARDOWN_STEPS
        self.assertLess(order.index("write cgroup.kill (LOAD-BEARING)"),
                        order.index("wait for cgroup.events populated=0"))
        self.assertIn("only then cancellation_acknowledged=true", order)

    def test_23_fail_closed_malformed_configuration(self):
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(_spec(self.provider, self.froot, self.fx,
                                        self.sha, uid=0))
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(SandboxSpec(
                provider=ProviderRef(root="relative", node_modules=str(
                    self.provider / "node_modules")),
                fixture=self.spec.fixture))
        with self.assertRaises(SubstrateConfigError):
            validate_sandbox_spec(SandboxSpec(
                provider=ProviderRef(root=str(self.provider),
                                     node_modules=str(self.provider /
                                                      "node_modules"),
                                     pin="short"),
                fixture=self.spec.fixture))

    def test_24_forbidden_arbitrary_path_and_tool(self):
        with self.assertRaises(ArbitraryInputError):
            ensure_fixture_literal(self.spec, "/etc/hostname")
        self.assertEqual(ensure_tool_literal(C1A_TOOL), C1A_TOOL)
        for bad in ("nmap", "shell", ""):
            with self.assertRaises(ArbitraryInputError):
                ensure_tool_literal(bad)

    def test_25_provider_pin_and_fixture_sha(self):
        ref = self.spec.provider
        self.assertEqual(ref.verify_pin(), (True, PROVIDER_PIN))
        (self.provider / ".git" / "HEAD").write_text("0" * 40 + "\n")
        self.assertFalse(ref.verify_pin()[0])
        self.assertEqual(self.spec.fixture.verify(), (True, self.sha))
        self.assertEqual(FIXTURE_SHA256,
                         "c033fda6e893ed965de8496ad170628d33ce69817c6ad0"
                         "5bbb63bcb5e1010bd1")

    def test_26_launcher_seam_contract(self):
        c = launcher_contract(self.spec, "PS-1", "INV-1")
        self.assertEqual(c.tool, C1A_TOOL)
        self.assertEqual(c.fixture_path, str(self.fx))
        self.assertEqual(c.command, (NODE_RUNTIME, LAUNCHER_ENTRY))
        self.assertFalse(c.to_dict()["generic_dispatcher"])
        self.assertEqual(c.call_id, launcher_contract(
            self.spec, "PS-1", "INV-1").call_id)
        with self.assertRaises(SubstrateConfigError):
            launcher_contract(self.spec, "", "")

    def test_27_termination_observation_parser(self):
        self.assertTrue(termination_observed("populated 0\nfrozen 0\n"))
        self.assertFalse(termination_observed("populated 1\n"))
        self.assertFalse(termination_observed("frozen 0\n"))


if __name__ == "__main__":
    unittest.main()
