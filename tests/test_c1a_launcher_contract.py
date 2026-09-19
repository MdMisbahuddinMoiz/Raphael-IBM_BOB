"""tests.test_c1a_launcher_contract — launcher contract (CORRECTION 4).

The launcher is NOT the T3MP3ST provider; it is a pinned single-purpose
executable whose receipt is validated against the closed provider schema.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.c1a_transport import BoundedTransport  # noqa: E402
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    ALLOWED_PAYLOAD_KEYS,
    _normalize_key,
    _DENIED_NORMALIZED,
)

LAUNCHER = ROOT_DIR / "provider" / "c1a_launcher.js"
NODE = shutil.which("node")


def _identity_env(fixture: Path, **over):
    env = {
        "RAPHAEL_RUN_ID": "run-1",
        "RAPHAEL_INVOCATION_ID": "INV-1",
        "RAPHAEL_PROOF_SESSION_ID": "PS-1",
        "RAPHAEL_FIXTURE_PATH": str(fixture),
    }
    env.update(over)
    return env


@unittest.skipUnless(NODE, "node is not installed")
class LauncherContract(unittest.TestCase):
    def setUp(self):
        self.transport = BoundedTransport()
        self.tmp = tempfile.TemporaryDirectory(prefix="c1a_launcher_")
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name) / "sink.bin"
        self.fixture.write_bytes(b"hello\x00\x00world\nopen( x + y )\n")

    def _run(self, env):
        return self.transport.execute(
            [NODE, str(LAUNCHER)], timeout_seconds=10.0, env=env)

    def test_receipt_is_closed_schema(self):
        result = self._run(_identity_env(self.fixture))
        self.assertEqual(result.exit_code, 0, msg=result.stderr_bytes)
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertTrue(set(receipt).issubset(ALLOWED_PAYLOAD_KEYS))
        for key in receipt:
            self.assertNotIn(_normalize_key(key), _DENIED_NORMALIZED)

    def test_receipt_path_equals_fixture_literal(self):
        result = self._run(_identity_env(self.fixture))
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertTrue(receipt["results"])
        for item in receipt["results"]:
            self.assertEqual(item["path"], str(self.fixture))

    def test_missing_identity_fails_closed(self):
        result = self._run(_identity_env(self.fixture, RAPHAEL_RUN_ID=""))
        self.assertEqual(result.exit_code, 1)
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertEqual(receipt["provider_message"], "missing_identity")

    def test_relative_path_rejected(self):
        env = _identity_env(self.fixture, RAPHAEL_FIXTURE_PATH="sink.bin")
        result = self._run(env)
        self.assertEqual(result.exit_code, 1)
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertEqual(receipt["provider_message"], "invalid_fixture_path")

    def test_traversal_path_rejected(self):
        env = _identity_env(self.fixture,
                            RAPHAEL_FIXTURE_PATH="/tmp/../etc/passwd")
        result = self._run(env)
        self.assertEqual(result.exit_code, 1)
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertEqual(receipt["provider_message"], "invalid_fixture_path")

    def test_missing_fixture_fails_closed(self):
        env = _identity_env(self.fixture)
        env["RAPHAEL_FIXTURE_PATH"] = self.tmp.name + "/nope.bin"
        result = self._run(env)
        self.assertEqual(result.exit_code, 1)
        receipt = json.loads(result.stdout_bytes.decode())
        self.assertEqual(receipt["provider_message"], "fixture_unreadable")

    def test_source_has_no_child_process_or_network(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        for forbidden in ("child_process", "require('net')", 'require("net")',
                          "http", "https", "eval("):
            self.assertNotIn(forbidden, text,
                             f"launcher must not reference {forbidden!r}")


if __name__ == "__main__":
    unittest.main()
