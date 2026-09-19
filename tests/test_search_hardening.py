"""tests.test_search_hardening — SEARCH resource bounds."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob import capabilities  # noqa: E402
from raphael_ibm_bob.contracts import ActionRequest, Capability  # noqa: E402
from raphael_ibm_bob.workspace import Workspace  # noqa: E402


def _workspace(files):
    tmp = tempfile.TemporaryDirectory(prefix="c1a_search_")
    root = Path(tmp.name)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp, root


def _request(target, pattern="NEEDLE"):
    return ActionRequest(sequence=0, requester="t",
                         capability=Capability.SEARCH, target=str(target),
                         purpose=pattern)


class SearchBounds(unittest.TestCase):
    def test_match_cap_and_truncation(self):
        tmp, root = _workspace({"src/a.txt": "NEEDLE\nNEEDLE\nNEEDLE\n"})
        self.addCleanup(tmp.cleanup)
        ws = Workspace(root)
        with mock.patch.object(capabilities, "MAX_SEARCH_MATCHES", 2):
            result = capabilities._search(ws, _request(root / "src"))
        self.assertEqual(len(result["matches"]), 2)
        self.assertTrue(result["truncated"])

    def test_file_cap(self):
        tmp, root = _workspace({
            "src/a.txt": "NEEDLE\n", "src/b.txt": "NEEDLE\n"})
        self.addCleanup(tmp.cleanup)
        ws = Workspace(root)
        with mock.patch.object(capabilities, "MAX_SEARCH_FILES", 1):
            result = capabilities._search(ws, _request(root / "src"))
        self.assertEqual(result["scanned_files"], 1)
        self.assertTrue(result["truncated"])

    def test_large_file_skipped(self):
        tmp, root = _workspace({"src/big.txt": "x" * 5000})
        self.addCleanup(tmp.cleanup)
        ws = Workspace(root)
        with mock.patch.object(capabilities, "MAX_SEARCH_FILE_BYTES", 100):
            result = capabilities._search(ws, _request(root / "src"))
        self.assertGreaterEqual(result["skipped_files"], 1)
        self.assertEqual(result["matches"], [])

    def test_line_length_bounded(self):
        tmp, root = _workspace({"src/a.txt": "NEEDLE" + "x" * 500 + "\n"})
        self.addCleanup(tmp.cleanup)
        ws = Workspace(root)
        result = capabilities._search(ws, _request(root / "src"))
        self.assertTrue(result["matches"])
        self.assertLessEqual(len(result["matches"][0]["text"]),
                             capabilities.MAX_SEARCH_LINE)

    def test_unbounded_search_not_truncated(self):
        tmp, root = _workspace({"src/a.txt": "NEEDLE\n"})
        self.addCleanup(tmp.cleanup)
        ws = Workspace(root)
        result = capabilities._search(ws, _request(root / "src"))
        self.assertFalse(result["truncated"])


if __name__ == "__main__":
    unittest.main()
