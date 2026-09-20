"""tests.test_canonical_hero — tests for the canonical judge demo runner."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demos.canonical_hero import (
    check_prerequisites,
    run_canonical_demo,
)


class CanonicalHeroTest(unittest.TestCase):
    def test_check_prerequisites_returns_valid_structure(self):
        statuses = check_prerequisites()
        self.assertTrue(len(statuses) >= 5)
        names = {s.name for s in statuses}
        self.assertIn("python_runtime", names)
        self.assertIn("node_runtime", names)
        self.assertIn("bwrap_sandbox", names)
        self.assertIn("c1a_launcher_pinned", names)
        self.assertIn("t3mp3st_bridge_pinned", names)
        self.assertIn("t3mp3st_provider_dist", names)

    def test_canonical_hero_raphael_mode_reaches_complete(self):
        exit_code = run_canonical_demo(mode="raphael")
        self.assertEqual(exit_code, 0)

    def test_canonical_hero_refuse_mode_reaches_refuse(self):
        exit_code = run_canonical_demo(mode="refuse")
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
