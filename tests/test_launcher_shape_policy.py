"""tests.test_launcher_shape_policy — R2 launcher-shape coverage evidence.

Asserts that the syscalls observed in the non-provider C1A launcher-shape
smoke (nested require() module tree) are covered by the current curated
policy, or are documented deliberate denials. Reads a committed evidence
artifact; it performs no execution and never touches T3MP3ST.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from raphael_ibm_bob.seccomp_policy import (
    ARG_FILTERED,
    SPECIAL_ACTIONS,
    allowed_syscall_names,
)

INVENTORY = (Path(__file__).resolve().parents[1] / "docs" / "integration" /
             "phase-2c-g2" / "launcher-shape-inventory.json")

#: Intentionally denied: libuv falls back gracefully (proven by exit 0).
DELIBERATE_DENIALS = {"io_uring_setup", "io_uring_enter"}


class LauncherShapeCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = json.loads(INVENTORY.read_text())

    def _covered(self):
        return (set(allowed_syscall_names())
                | {n for (n, _a, _k, _v, _e) in ARG_FILTERED}
                | set(SPECIAL_ACTIONS))

    def test_1_no_new_syscalls_vs_plain_node(self):
        self.assertEqual(self.inv["delta_vs_plain_node"]["new"], [])

    def test_2_every_shape_syscall_covered_or_deliberately_denied(self):
        uncovered = sorted(set(self.inv["unique_syscalls"]) - self._covered()
                           - DELIBERATE_DENIALS)
        self.assertEqual(uncovered, [])

    def test_3_denied_shape_syscalls_are_only_io_uring(self):
        denied = set(self.inv["unique_syscalls"]) - self._covered()
        self.assertEqual(denied, DELIBERATE_DENIALS)

    def test_4_no_eprem_in_launcher_shape_trace(self):
        self.assertNotIn("EPERM", self.inv["errnos"])


if __name__ == "__main__":
    unittest.main()
