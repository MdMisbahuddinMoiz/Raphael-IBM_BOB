"""tests.test_m2_probe — M2 egress evidence + construction hardening.

Validates the committed M2 evidence (direct PID-attached syscall trace,
fail-closed assertions, interfaces/routes/proxy) and the substrate
proxy-unsetenv hardening. No execution; T3MP3ST is not involved.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.isolation_substrate import (
    PROXY_ENV_VARS, FixtureRef, ProviderRef, SandboxSpec, build_bwrap_argv)

EVIDENCE = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
            "phase-2c-m2" / "m2-evidence.json")
PROBE_IDS = ("M2-P1", "M2-P2", "M2-P3", "M2-P4", "M2-P5", "M2-P6", "M2-P7",
             "M2-P8", "M2-P9", "M2-P10", "M2-P11", "M2-P12", "M2-P13")
AUDITED_BPF = "d1574a64643907e6c95ccafbfc74e7f04977781014ade214011e57994cb65242"


class M2Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(EVIDENCE.read_text())

    def test_1_covers_all_probe_families(self):
        ids = {r["probe_id"] for r in self.d["records"]}
        for probe in PROBE_IDS:
            self.assertIn(probe, ids)

    def test_2_strace_return_code_asserted_zero(self):
        self.assertEqual(self.d["strace"]["exit_code"], 0)

    def test_3_node_pid_present_and_observed(self):
        self.assertIsInstance(self.d["node_pid"], int)
        self.assertGreater(self.d["node_pid"], 0)
        self.assertTrue(self.d["strace"]["assertions"]["node_pid_discovered"])

    def test_4_node_process_network_syscalls_present(self):
        self.assertTrue(self.d["strace"]["assertions"]["trace_has_node_network_syscalls"])
        self.assertGreater(self.d["strace"]["net_line_count"], 0)

    def test_5_bwrap_only_trace_rejected(self):
        self.assertFalse(self.d["strace"]["bwrap_only"])
        self.assertTrue(self.d["strace"]["assertions"]["trace_not_bwrap_only"])
        self.assertNotIn("AF_NETLINK", " ".join(self.d["strace"].get("net_lines", [])) or "")

    def test_6_proxy_unsetenv_argv_generation(self):
        base = Path(tempfile.mkdtemp(prefix="m2_"))
        self.addCleanup(shutil.rmtree, base, True)
        prov = base / "provider"
        (prov / "node_modules").mkdir(parents=True)
        froot = base / "fx"
        froot.mkdir()
        fx = froot / "f.txt"
        fx.write_text("x")
        spec = SandboxSpec(
            provider=ProviderRef(root=str(prov), node_modules=str(prov / "node_modules")),
            fixture=FixtureRef(root=str(froot), path=str(fx),
                               sha256=hashlib.sha256(b"x").hexdigest()))
        argv = list(build_bwrap_argv(spec))
        for name in PROXY_ENV_VARS:
            i = argv.index("--unsetenv")
            self.assertIn(name, argv)
            self.assertEqual(argv[argv.index(name) - 1], "--unsetenv")
        self.assertGreaterEqual(argv.count("--unsetenv"), 10)

    def test_7_proxy_variables_sanitized_in_probe(self):
        self.assertEqual(self.d["proxy_env"]["probe"], [])
        self.assertGreaterEqual(len(self.d["proxy_env"]["argv_unsetenv"]), 10)
        self.assertTrue(self.d["strace"]["assertions"]["proxy_absent_in_probe"])

    def test_8_ipv4_route_artifact(self):
        r = self.d["routes"]["ipv4"]
        self.assertIn("Destination", r)
        self.assertNotIn("00000000", r)

    def test_9_ipv6_route_artifact(self):
        v6 = self.d["routes"]["ipv6"]
        self.assertTrue(v6)
        self.assertEqual(self.d["routes"]["ipv6_default_or_nonloopback"], "NONE (all-zero)")

    def test_10_interface_rx_tx_counters(self):
        i = self.d["interfaces"]
        self.assertEqual(i["visible"], ["lo"])
        self.assertIn(i["lo_rx_bytes"], (0, "0"))
        self.assertIn(i["lo_tx_bytes"], (0, "0"))

    def test_11_direct_eperm_classification(self):
        sev = self.d["direct_syscall_evidence"]
        self.assertGreater(sev["socket"]["EPERM"], 0)
        for k in ("connect", "bind", "listen", "sendto", "recvfrom"):
            self.assertIn("BLOCKED", sev[k])
        rec = [x for x in self.d["records"] if x["probe_id"] == "M2-P12"][0]
        self.assertEqual(rec["classification"], "DIRECT")

    def test_12_blocked_dependent_classification(self):
        for x in self.d["records"]:
            self.assertIn(x["classification"], ("DIRECT", "INFERRED", "BLOCKED", "UNVERIFIED"))
            self.assertIn(x["status"], ("PASS", "FAIL", "BLOCKED"))
            self.assertTrue(x["evidence"])
        self.assertGreaterEqual(self.d["blocked"], 1)

    def test_13_final_status_and_no_egress(self):
        self.assertEqual(self.d["fail"], 0)
        self.assertEqual(self.d["fails"], [])
        self.assertTrue(self.d["no_successful_egress"])
        self.assertIn(self.d["final_status"], ("PROBED_PASS", "PARTIAL"))

    def test_14_freeze_matches_audited_construction(self):
        f = self.d["freeze"]
        self.assertEqual(f["bpf_sha256"], AUDITED_BPF)
        self.assertEqual(f["builder_argv_len"] >= 131, True)
        self.assertEqual(f["scratch_mode"], "NO_SCRATCH")
        self.assertTrue(f["unshare_net"])


if __name__ == "__main__":
    unittest.main()
