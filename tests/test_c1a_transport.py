"""tests.test_c1a_transport — bounded transport behavior."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.c1a_transport import (  # noqa: E402
    BoundedTransport,
    TransportError,
)


class TransportBasics(unittest.TestCase):
    def setUp(self):
        self.transport = BoundedTransport()

    def test_clean_receipt(self):
        result = self.transport.execute(
            [sys.executable, "-c",
             "import sys; sys.stdout.write('hello'); "
             "sys.stderr.write('diag')"],
            timeout_seconds=10.0)
        self.assertEqual(result.stdout_bytes, b"hello")
        self.assertEqual(result.stderr_bytes, b"diag")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.late_output)
        self.assertTrue(result.process_exited)
        self.assertTrue(result.receipt_ok())

    def test_nonzero_exit_is_not_ok(self):
        result = self.transport.execute(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            timeout_seconds=10.0)
        self.assertEqual(result.exit_code, 3)
        self.assertFalse(result.receipt_ok())

    def test_stderr_is_separate(self):
        result = self.transport.execute(
            [sys.executable, "-c",
             "import sys; sys.stdout.write('OUT'); sys.stderr.write('ERR')"],
            timeout_seconds=10.0)
        self.assertNotIn(b"ERR", result.stdout_bytes)
        self.assertNotIn(b"OUT", result.stderr_bytes)

    def test_stdout_truncation_recorded(self):
        transport = BoundedTransport(max_stdout_bytes=16)
        result = transport.execute(
            [sys.executable, "-c",
             "import sys; sys.stdout.write('x' * 1000)"],
            timeout_seconds=10.0)
        self.assertTrue(result.stdout_truncated)
        self.assertLessEqual(len(result.stdout_bytes), 16)
        self.assertFalse(result.receipt_ok())

    def test_env_is_passed(self):
        result = self.transport.execute(
            [sys.executable, "-c",
             "import os,sys; sys.stdout.write(os.environ.get('C1A_FLAG',''))"],
            timeout_seconds=10.0, env={"C1A_FLAG": "on"})
        self.assertEqual(result.stdout_bytes, b"on")

    def test_cwd_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.transport.execute(
                [sys.executable, "-c", "import os,sys; sys.stdout.write(os.getcwd())"],
                timeout_seconds=10.0, cwd=tmp)
            self.assertEqual(result.stdout_bytes.decode(), str(Path(tmp)))

    def test_invalid_argv_rejected(self):
        with self.assertRaises(TransportError):
            self.transport.execute([], timeout_seconds=1.0)
        with self.assertRaises(TransportError):
            self.transport.execute(["", "x"], timeout_seconds=1.0)

    def test_invalid_timeout_rejected(self):
        for bad in (0, -1.0, float("nan"), float("inf"), True):
            with self.assertRaises(TransportError):
                self.transport.execute([sys.executable, "-c", "pass"],
                                       timeout_seconds=bad)

    def test_missing_binary_fails_closed(self):
        with self.assertRaises(TransportError):
            self.transport.execute(["/no/such/binary-xyz"], timeout_seconds=1.0)


if __name__ == "__main__":
    unittest.main()
