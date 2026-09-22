"""tests.test_d7_vpn — D7 HTB VPN layer tests.

Deterministic and offline: no network and no real OpenVPN. The manager is
driven by an injected process factory; the profile validator and the HTTP
API (real router + dispatch) are exercised directly.

The fake process reports ``pid=None`` so process-group signalling falls
back to ``terminate()`` and can never touch a real OS process.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    dispatch,
)
from raphael_ibm_bob.http.views.network_console import render_network
from raphael_ibm_bob.vpn import (
    VPNConflict,
    VPNExecutableNotFound,
    VPNManager,
    VPNProfileError,
    validate_profile,
)
from raphael_ibm_bob.vpn.profile import MAX_PROFILE_BYTES, ProfileError

REPO = Path(__file__).resolve().parents[1]

VALID_PROFILE = """client
dev tun
proto udp
remote vpn.example.htb 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-CBC
verb 3
<ca>
-----BEGIN CERTIFICATE-----
MIIBFAKECERT
-----END CERTIFICATE-----
</ca>
<cert>
-----BEGIN CERTIFICATE-----
MIIBFAKECERT
-----END CERTIFICATE-----
</cert>
<key>
-----BEGIN PRIVATE KEY-----
MIIBFAKEKEY
-----END PRIVATE KEY-----
</key>
"""

CONNECTED_LINES = [
    "OpenVPN 2.6.0 x86_64",
    "TUN/TAP device tun9 opened",
    "PUSH: Received control message: 'ifconfig 10.10.14.18 10.10.14.17'",
    "Initialization Sequence Completed",
]


class FakeProcess:
    """Minimal Popen stand-in. pid=None keeps signalling off the OS."""

    def __init__(self, lines=(), exit_code=None):
        self.pid = None
        self._lines = list(lines)
        self._exit = exit_code
        self._done = exit_code is not None
        self.terminated = False
        self.killed = False
        self.stdout = iter(self._lines)

    @property
    def returncode(self):
        return self._exit if self._done else None

    def poll(self):
        if self.killed:
            self._done = True
            self._exit = self._exit if self._exit is not None else -9
        return self._exit if self._done else None

    def terminate(self):
        self.terminated = True
        self._done = True
        if self._exit is None:
            self._exit = -15

    def kill(self):
        self.killed = True
        self.terminated = True
        self._done = True
        if self._exit is None:
            self._exit = -9

    def wait(self):
        return self.poll()

    def force_exit(self, code=1):
        self._done = True
        self._exit = code


class _ManagerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d7vpn_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.procs = []

    def make_manager(self, *, lines=CONNECTED_LINES, exit_code=None,
                     which=lambda name: "/usr/bin/openvpn",
                     connect_timeout=5.0, **kwargs):
        def factory(args, **popen_kwargs):
            proc = FakeProcess(lines=lines, exit_code=exit_code)
            proc._args = args
            proc._kwargs = popen_kwargs
            self.procs.append(proc)
            return proc

        return VPNManager(
            state_dir=self.tmp / "state",
            connect_timeout=connect_timeout,
            monitor_poll=0.01,
            which=which,
            popen=factory,
            **kwargs)


# ---------------------------------------------------------------------------
# profile handling
# ---------------------------------------------------------------------------

class ProfileValidation(unittest.TestCase):
    def test_valid_profile_accepted(self):
        self.assertEqual(validate_profile(VALID_PROFILE), VALID_PROFILE)

    def test_empty_profile_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile("   \n  ")

    def test_non_text_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile(b"client\n")

    def test_oversize_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile("x" * (MAX_PROFILE_BYTES + 1))

    def test_unsafe_directives_rejected(self):
        for directive in ("up /tmp/x.sh", "down /tmp/y.sh",
                          "plugin /evil.so", "script-security 2",
                          "config /etc/passwd", "auth-user-pass",
                          "route-up /tmp/z.sh", "log /tmp/leak.log"):
            with self.subTest(directive=directive):
                with self.assertRaises(ProfileError):
                    validate_profile(f"client\n{directive}\n")

    def test_unsupported_inline_block_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile("<script>\nfoo\n</script>\n")

    def test_unterminated_block_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile("<ca>\nMIIB\n")


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

class VPNLifecycle(_ManagerCase):
    def test_connect_success_detects_tunnel(self):
        mgr = self.make_manager()
        status = mgr.connect(VALID_PROFILE, "HTB-Lab.ovpn")
        self.assertEqual(status["state"], "connected")
        self.assertEqual(status["interface"], "tun9")
        self.assertEqual(status["address"], "10.10.14.18")
        self.assertEqual(status["profile_name"], "HTB-Lab.ovpn")
        self.assertIsNotNone(status["connected_at"])
        self.assertIsNone(status["error"])

    def test_duplicate_connect_conflicts(self):
        mgr = self.make_manager()
        mgr.connect(VALID_PROFILE)
        with self.assertRaises(VPNConflict):
            mgr.connect(VALID_PROFILE)

    def test_missing_executable(self):
        mgr = self.make_manager(which=lambda name: None)
        with self.assertRaises(VPNExecutableNotFound):
            mgr.connect(VALID_PROFILE)
        self.assertEqual(mgr.status()["state"], "failed")

    def test_invalid_profile_raises_profile_error(self):
        mgr = self.make_manager()
        with self.assertRaises(VPNProfileError):
            mgr.connect("client\nplugin /evil.so\n")
        self.assertEqual(mgr.status()["state"], "failed")

    def test_timeout_terminates_process(self):
        mgr = self.make_manager(lines=(), connect_timeout=0.2)
        status = mgr.connect(VALID_PROFILE)
        self.assertEqual(status["state"], "failed")
        self.assertIn("timed out", status["error"])
        self.assertTrue(self.procs[-1].terminated)

    def test_process_exits_before_handshake(self):
        mgr = self.make_manager(exit_code=1)
        status = mgr.connect(VALID_PROFILE)
        self.assertEqual(status["state"], "failed")
        self.assertIn("exited", status["error"])

    def test_status_reports_unexpected_exit(self):
        mgr = self.make_manager()
        mgr.connect(VALID_PROFILE)
        self.procs[-1].force_exit(3)
        status = mgr.status()
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["process_state"], "exited")
        self.assertTrue(any(e["event"] == "VPN_PROCESS_EXITED"
                            for e in status["history"]))

    def test_disconnect_idempotent(self):
        mgr = self.make_manager()
        first = mgr.disconnect()
        self.assertEqual(first["state"], "disconnected")
        second = mgr.disconnect()
        self.assertEqual(second["state"], "disconnected")

    def test_disconnect_terminates_and_cleans(self):
        mgr = self.make_manager()
        mgr.connect(VALID_PROFILE)
        profile_dir = mgr._profile_dir
        self.assertTrue(Path(profile_dir).is_dir())
        status = mgr.disconnect()
        self.assertEqual(status["state"], "disconnected")
        self.assertTrue(self.procs[-1].terminated)
        self.assertFalse(Path(profile_dir).exists())

    def test_status_never_leaks_profile(self):
        mgr = self.make_manager()
        mgr.connect(VALID_PROFILE)
        blob = json.dumps(mgr.status())
        self.assertNotIn("BEGIN PRIVATE KEY", blob)
        self.assertNotIn("MIIBFAKEKEY", blob)
        self.assertNotIn("client\n", blob)


# ---------------------------------------------------------------------------
# security
# ---------------------------------------------------------------------------

class VPNSecurity(_ManagerCase):
    def test_no_shell_true_in_sources(self):
        for rel in ("raphael_ibm_bob/vpn/manager.py",
                    "raphael_ibm_bob/vpn/profile.py",
                    "raphael_ibm_bob/http/routes/vpn.py"):
            text = (REPO / rel).read_text(encoding="utf-8")
            self.assertNotIn("shell=True", text, rel)
            self.assertNotIn("shell = True", text, rel)

    def test_spawn_uses_argument_array_without_shell(self):
        mgr = self.make_manager()
        mgr.connect(VALID_PROFILE)
        proc = self.procs[-1]
        self.assertIsInstance(proc._args, list)
        self.assertEqual(proc._args[0], "/usr/bin/openvpn")
        self.assertNotIn("shell", proc._kwargs)

    def test_request_cannot_override_executable(self):
        mgr = self.make_manager()
        cfg = RaphaelHTTPConfig(vpn_manager=mgr)
        router = build_router()
        req = Request(method="POST", path="/vpn/connect", body={
            "profile": VALID_PROFILE,
            "profile_name": "x.ovpn",
            "openvpn_bin": "/bin/sh",
            "executable": "/bin/sh",
        })
        resp = dispatch(req, cfg, router)
        self.assertEqual(resp.status, 201, resp.body)
        self.assertEqual(self.procs[-1]._args[0], "/usr/bin/openvpn")


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

class VPNAPIRoutes(_ManagerCase):
    def setUp(self):
        super().setUp()
        self.mgr = self.make_manager()
        self.cfg = RaphaelHTTPConfig(vpn_manager=self.mgr)
        self.router = build_router()

    def call(self, method, path, body=None):
        req = Request(method=method, path=path, body=body)
        return dispatch(req, self.cfg, self.router)

    def test_status(self):
        resp = self.call("GET", "/vpn/status")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body["state"], "disconnected")

    def test_connect_requires_profile(self):
        resp = self.call("POST", "/vpn/connect", body={})
        self.assertEqual(resp.status, 422)
        self.assertEqual(resp.body["error"]["code"], "INVALID_INPUT")

    def test_connect_success(self):
        resp = self.call("POST", "/vpn/connect",
                         body={"profile": VALID_PROFILE,
                               "profile_name": "HTB-Lab.ovpn"})
        self.assertEqual(resp.status, 201, resp.body)
        self.assertEqual(resp.body["state"], "connected")
        self.assertEqual(resp.body["interface"], "tun9")

    def test_connect_invalid_profile(self):
        resp = self.call("POST", "/vpn/connect",
                         body={"profile": "client\nplugin /evil.so\n"})
        self.assertEqual(resp.status, 422)
        self.assertEqual(resp.body["error"]["code"], "VPN_PROFILE_INVALID")

    def test_connect_missing_executable(self):
        mgr = self.make_manager(which=lambda name: None)
        cfg = RaphaelHTTPConfig(vpn_manager=mgr)
        req = Request(method="POST", path="/vpn/connect",
                      body={"profile": VALID_PROFILE})
        resp = dispatch(req, cfg, self.router)
        self.assertEqual(resp.status, 503)
        self.assertEqual(resp.body["error"]["code"], "VPN_EXECUTABLE_MISSING")

    def test_duplicate_connect_conflict(self):
        self.call("POST", "/vpn/connect", body={"profile": VALID_PROFILE})
        resp = self.call("POST", "/vpn/connect",
                         body={"profile": VALID_PROFILE})
        self.assertEqual(resp.status, 409)
        self.assertEqual(resp.body["error"]["code"], "VPN_CONFLICT")

    def test_disconnect(self):
        self.call("POST", "/vpn/connect", body={"profile": VALID_PROFILE})
        resp = self.call("POST", "/vpn/disconnect")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body["state"], "disconnected")


# ---------------------------------------------------------------------------
# UI view
# ---------------------------------------------------------------------------

class VPNNetworkPage(unittest.TestCase):
    def test_page_renders_controls(self):
        html = render_network({"state": "connected", "interface": "tun9",
                               "address": "10.10.14.18",
                               "profile_name": "HTB-Lab.ovpn",
                               "process_state": "running",
                               "history": []})
        for needle in ("HTB VPN", "CONNECTED", "tun9", "10.10.14.18",
                       'type="file"', "/vpn/connect", "/vpn/disconnect"):
            self.assertIn(needle, html)

    def test_page_renders_disconnected(self):
        html = render_network({"state": "disconnected", "history": []})
        self.assertIn("DISCONNECTED", html)

    def test_page_shows_failure_error(self):
        html = render_network({"state": "failed",
                               "error": "connection timed out after 30s",
                               "history": []})
        self.assertIn("FAILED", html)
        self.assertIn("connection timed out", html)


if __name__ == "__main__":
    unittest.main()
