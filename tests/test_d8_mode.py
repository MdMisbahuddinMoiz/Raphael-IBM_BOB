"""tests.test_d8_mode — D8 product mode + HTB testing profile tests.

Deterministic and offline. The mode model is pure; the HTTP API is
exercised through the real router/dispatch; the UI is exercised by
calling the real view renderers.

The mode layer is configuration only: no test here starts a VPN, a
subprocess, or any network activity.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    dispatch,
)
from raphael_ibm_bob.http.views.command_center import render_command
from raphael_ibm_bob.http.views.operations_console import render_index
from raphael_ibm_bob.mode import (
    Mode,
    ModeError,
    ModeManager,
    ModeState,
    TestingProfile,
)

REPO = Path(__file__).resolve().parents[1]


class _SpyVPN:
    """VPN manager stand-in that records whether connect() was called."""

    def __init__(self, state="disconnected"):
        self.connect_calls = 0
        self._state = state

    def status(self):
        return {"state": self._state, "profile_name": None,
                "interface": None, "address": None, "connected_at": None,
                "process_state": "absent", "pid": None, "error": None,
                "history": []}

    def connect(self, *args, **kwargs):
        self.connect_calls += 1
        return self.status()

    def disconnect(self):
        return self.status()


# ---------------------------------------------------------------------------
# mode model
# ---------------------------------------------------------------------------

class ModeModel(unittest.TestCase):
    def test_default_is_normal(self):
        state = ModeManager().state()
        self.assertIs(state.mode, Mode.NORMAL)
        self.assertIsNone(state.testing_profile)

    def test_testing_requires_profile(self):
        mgr = ModeManager()
        with self.assertRaises(ModeError):
            mgr.set(Mode.TESTING)

    def test_testing_htb(self):
        state = ModeManager().set("testing", "htb")
        self.assertIs(state.mode, Mode.TESTING)
        self.assertIs(state.testing_profile, TestingProfile.HTB)
        self.assertEqual(state.to_dict()["testing_profile"], "htb")

    def test_normal_clears_profile(self):
        mgr = ModeManager()
        mgr.set("testing", "htb")
        state = mgr.set("normal")
        self.assertIs(state.mode, Mode.NORMAL)
        self.assertIsNone(state.testing_profile)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ModeError):
            ModeManager().set("htb")

    def test_invalid_profile_rejected(self):
        with self.assertRaises(ModeError):
            ModeManager().set("testing", "not-a-profile")

    def test_unknown_state_serialises_cleanly(self):
        self.assertEqual(ModeState().to_dict()["mode"], "normal")

    def test_no_network_or_execution_imports(self):
        # The mode layer is configuration only: it must not import an
        # execution/network module or the Mission contract.
        for rel in ("raphael_ibm_bob/mode.py",
                    "raphael_ibm_bob/http/routes/mode.py"):
            text = (REPO / rel).read_text(encoding="utf-8")
            for needle in ("import subprocess", "import socket",
                           "from raphael_ibm_bob.contracts",
                           "from raphael_ibm_bob import contracts",
                           "subprocess.", "socket.", "os.system",
                           "shell=True", "import openvpn"):
                self.assertNotIn(needle, text, f"{rel}: {needle}")


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

class ModeAPI(unittest.TestCase):
    def setUp(self):
        self.mgr = ModeManager()
        self.vpn = _SpyVPN()
        self.cfg = RaphaelHTTPConfig(mode_manager=self.mgr,
                                     vpn_manager=self.vpn)
        self.router = build_router()

    def call(self, method, path, body=None):
        return dispatch(Request(method=method, path=path, body=body),
                        self.cfg, self.router)

    def test_get_default_normal(self):
        resp = self.call("GET", "/mode")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body["mode"], "normal")
        self.assertIsNone(resp.body["testing_profile"])

    def test_post_testing_htb(self):
        resp = self.call("POST", "/mode",
                         body={"mode": "testing",
                               "testing_profile": "htb"})
        self.assertEqual(resp.status, 200, resp.body)
        self.assertEqual(resp.body["mode"], "testing")
        self.assertEqual(resp.body["testing_profile"], "htb")
        self.assertEqual(self.call("GET", "/mode").body["mode"], "testing")

    def test_post_testing_without_profile(self):
        resp = self.call("POST", "/mode", body={"mode": "testing"})
        self.assertEqual(resp.status, 422)
        self.assertEqual(resp.body["error"]["code"], "INVALID_INPUT")

    def test_post_normal_clears_profile(self):
        self.call("POST", "/mode",
                  body={"mode": "testing", "testing_profile": "htb"})
        resp = self.call("POST", "/mode", body={"mode": "normal"})
        self.assertEqual(resp.status, 200)
        self.assertIsNone(resp.body["testing_profile"])

    def test_post_invalid_mode(self):
        resp = self.call("POST", "/mode", body={"mode": "bogus"})
        self.assertEqual(resp.status, 422)

    def test_selecting_htb_does_not_connect_vpn(self):
        self.call("POST", "/mode",
                  body={"mode": "testing", "testing_profile": "htb"})
        self.assertEqual(self.vpn.connect_calls, 0)
        self.assertEqual(self.vpn.status()["state"], "disconnected")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class ModeUI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d8mode_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def ops(self, mode_state, vpn_status=None):
        return render_index([], runs_root=self.tmp, sessions_root=self.tmp,
                            vpn_status=vpn_status, mode_state=mode_state)

    def test_normal_hides_testing_config(self):
        html = self.ops({"mode": "normal", "testing_profile": None})
        self.assertIn("RAPHAEL MODE", html)
        self.assertIn('value="normal" checked', html)
        self.assertNotIn("HTB CONTEXT", html)
        self.assertNotIn("OPEN HTB NETWORK", html)

    def test_testing_htb_shows_context(self):
        html = self.ops({"mode": "testing", "testing_profile": "htb"},
                        {"state": "connected", "interface": "tun9",
                         "address": "10.10.14.18"})
        self.assertIn("HTB CONTEXT", html)
        self.assertIn("TESTING ENVIRONMENT", html)
        self.assertIn("OPEN HTB NETWORK", html)
        self.assertIn("CONNECTED", html)
        self.assertIn("Not configured", html)

    def test_testing_htb_does_not_duplicate_vpn_strip(self):
        html = self.ops({"mode": "testing", "testing_profile": "htb"},
                        {"state": "disconnected"})
        self.assertEqual(html.count("HTB VPN"), 0)
        self.assertEqual(html.count("HTB CONTEXT"), 1)

    def test_vpn_states_render(self):
        for state, label in (("disconnected", "DISCONNECTED"),
                             ("connecting", "CONNECTING"),
                             ("connected", "CONNECTED"),
                             ("failed", "FAILED")):
            with self.subTest(state=state):
                html = self.ops({"mode": "testing",
                                 "testing_profile": "htb"},
                                {"state": state})
                self.assertIn(label, html)

    def test_stale_htb_does_not_leak_into_normal(self):
        testing = self.ops({"mode": "testing", "testing_profile": "htb"},
                           {"state": "connected"})
        self.assertIn("HTB CONTEXT", testing)
        normal = self.ops({"mode": "normal", "testing_profile": None})
        self.assertNotIn("HTB CONTEXT", normal)
        self.assertNotIn("OPEN HTB NETWORK", normal)

    def test_command_center_reports_mode(self):
        html = render_command(runs_root=self.tmp, sessions_root=self.tmp,
                              mode_state={"mode": "testing",
                                          "testing_profile": "htb"},
                              vpn_status={"state": "connected"})
        self.assertIn("RAPHAEL MODE", html)
        self.assertIn("TESTING", html)
        self.assertIn("HTB", html)
        self.assertIn("CONNECTED", html)

    def test_command_center_unknown_not_fabricated(self):
        html = render_command(runs_root=self.tmp, sessions_root=self.tmp)
        self.assertIn("UNKNOWN", html)


if __name__ == "__main__":
    unittest.main()
