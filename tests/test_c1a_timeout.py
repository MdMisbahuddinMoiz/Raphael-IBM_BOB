"""tests.test_c1a_timeout — timeout / late-output never becomes SUCCESS."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.c1a_transport import BoundedTransport  # noqa: E402

_SLEEP = "import time; time.sleep(5)"
_SLEEP_THEN_WRITE = (
    "import sys, time; time.sleep(0.4); sys.stdout.write('late')")
_STREAM = (
    "import sys, time\n"
    "for _ in range(1000):\n"
    "    sys.stdout.write('x'); sys.stdout.flush(); time.sleep(0.01)\n")


class TimeoutNeverSucceeds(unittest.TestCase):
    def setUp(self):
        self.transport = BoundedTransport(drain_timeout_seconds=2.0)

    def test_timeout_is_not_success(self):
        result = self.transport.execute(
            [sys.executable, "-c", _SLEEP], timeout_seconds=0.1)
        self.assertTrue(result.timed_out)
        self.assertTrue(result.killed)
        self.assertFalse(result.receipt_ok())
        self.assertNotEqual(result.exit_code, 0)

    def test_timeout_kills_and_drains(self):
        result = self.transport.execute(
            [sys.executable, "-c", _SLEEP], timeout_seconds=0.1)
        self.assertTrue(result.process_exited)
        self.assertTrue(result.drain_completed)

    def test_late_output_never_succeeds(self):
        result = self.transport.execute(
            [sys.executable, "-c", _SLEEP_THEN_WRITE], timeout_seconds=0.1)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.receipt_ok())
        # Even if bytes arrived, they can never be a success receipt.
        self.assertFalse(result.receipt_ok())

    def test_streaming_timeout_flags_late_output(self):
        result = self.transport.execute(
            [sys.executable, "-c", _STREAM], timeout_seconds=0.2)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.receipt_ok())
        # Continuous output after the deadline must be flagged (conservative).
        self.assertTrue(result.late_output or result.stdout_truncated)


if __name__ == "__main__":
    unittest.main()
