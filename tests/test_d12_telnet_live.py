"""tests.test_d12_telnet_live — LIVE governed Telnet run against HTB Meow.

SKIPPED unless ``RAPHAEL_LIVE_MEOW=1`` is set (and the HTB VPN is connected
and the target is spawned). It performs a REAL governed Telnet session:

    RAPHAEL_LIVE_MEOW=1 \
    RAPHAEL_LIVE_MEOW_HOST=10.129.223.207 \
    PYTHONPATH=. python3 -m unittest tests.test_d12_telnet_live

The flag value is never asserted in source; the test asserts PRESENCE and
that the existing QualityGate reaches COMPLETE legitimately.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.harness.api import create_session
from raphael_ibm_bob.harness.telnet_run import run_telnet_mission
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.telnet_runtime import TelnetMediator

LIVE = os.environ.get("RAPHAEL_LIVE_MEOW") == "1"
HOST = os.environ.get("RAPHAEL_LIVE_MEOW_HOST", "10.129.223.207")
PORT = int(os.environ.get("RAPHAEL_LIVE_MEOW_PORT", "23"))
MISSION_ID = os.environ.get("RAPHAEL_LIVE_MEOW_MISSION", "M-HTB-MEOW-D12")


@unittest.skipUnless(LIVE, "set RAPHAEL_LIVE_MEOW=1 to run the live Meow test")
class LiveMeow(unittest.TestCase):
    def test_live_governed_telnet_reaches_complete(self):
        tmp = Path(tempfile.mkdtemp(prefix="d12live_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        ws = tmp / "ws"
        ws.mkdir()
        (ws / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n"
            "    def test_ok(self):\n        self.assertTrue(True)\n")

        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id=MISSION_ID, locator=HOST, allowed_ports=[PORT],
            allowed_protocols=["telnet"], scope=HOST,
            authorization_ref="HTB-AUTHORIZED-MEOW-D12"))

        mission = Mission(
            mission_id=MISSION_ID, description="live governed telnet meow",
            scope="", criteria=["obtain and verify the flag"],
            problem={
                "telnet": {
                    "username": "root", "password": "",
                    "commands": ["pwd", "ls", "cat flag.txt"],
                    "flag_command": "cat flag.txt",
                    "flag_pattern": "[0-9a-f]{32}",
                    "probe_command": "pwd",
                    "negative_control_command": "ls",
                    "timeout_seconds": 30,
                },
                "verification_tests": ["test_ok.py"],
            })

        session = create_session(
            mission=mission, workspace_root=ws, project_name="d12live",
            sessions_root=tmp / "sessions")
        result = run_telnet_mission(
            session, mission, ws, runs_root=tmp / "runs",
            sessions_root=tmp / "sessions", target_store=store,
            mediator=TelnetMediator(), timeout_seconds=30.0)

        print(f"live run_id={result.run.run_id} target={HOST}:{PORT}")
        # Flag must be PRESENT (value not printed).
        self.assertTrue(result.flag, "no flag captured from the live target")
        self.assertTrue(result.verified, "finding was not independently verified")
        self.assertEqual(result.gate_verdict, "complete",
                         f"gate={result.gate_verdict} "
                         f"reason={result.terminal_reason}")
        self.assertEqual(result.run.state, "completed")


if __name__ == "__main__":
    unittest.main()
