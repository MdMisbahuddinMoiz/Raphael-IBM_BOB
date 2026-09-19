"""tests.test_quality_gate_scope — canonical Condition E containment."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob.c1a_scope import (  # noqa: E402
    ScopePathError,
    canonical_parts,
    scope_contains,
    within_root,
)
from raphael_ibm_bob.contracts import (  # noqa: E402
    ActionRequest,
    Capability,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger  # noqa: E402
from raphael_ibm_bob.quality_gate import (  # noqa: E402
    BOBQualityGate,
    GateInputs,
)


class CanonicalScope(unittest.TestCase):
    def test_component_boundary(self):
        self.assertTrue(scope_contains("/ws/src", "/ws/src/a.py"))
        self.assertFalse(scope_contains("/ws/src", "/ws/src-evil/a.py"))
        self.assertFalse(scope_contains("/ws/src", "/ws/other/a.py"))

    def test_traversal_rejected(self):
        self.assertFalse(scope_contains("/ws/src", "/ws/src/../secret"))
        self.assertFalse(scope_contains("/ws/src", "/ws/src/../../etc/passwd"))

    def test_relative_scope_and_target(self):
        self.assertTrue(scope_contains("src/", "src/authkit/a.py"))
        self.assertFalse(scope_contains("src/store", "src/authkit/a.py"))

    def test_malformed_rejected(self):
        self.assertFalse(scope_contains("/ws", ""))
        self.assertFalse(scope_contains("/ws", "a\x00b"))
        with self.assertRaises(ScopePathError):
            canonical_parts("")
        with self.assertRaises(ScopePathError):
            canonical_parts("..")

    def test_within_root(self):
        self.assertTrue(within_root("/ws", "/ws/a/b.py"))
        self.assertFalse(within_root("/ws", "/ws-evil/a.py"))
        self.assertFalse(within_root("/ws", "relative/a.py"))

    def test_empty_scope_is_unconstrained(self):
        self.assertTrue(scope_contains("", "anything/at/all"))


class GateConditionE(unittest.TestCase):
    def _gate(self, tmp):
        ledger = EvidenceLedger(Path(tmp) / "run")
        return BOBQualityGate(ledger), ledger

    def _evaluate(self, ledger, scope):
        mission = Mission(mission_id="M", description="x", scope=scope,
                          criteria=["c"])
        return BOBQualityGate(ledger).evaluate(GateInputs(
            mission=mission, findings=[], regression_ok=False,
            behavior_probe_ok=False))

    def test_sibling_prefix_fails_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate, ledger = self._gate(tmp)
            scope = str(Path(tmp) / "src")
            ledger.append_request(ActionRequest(
                sequence=0, requester="t", capability=Capability.READ,
                target=str(Path(tmp) / "src-evil" / "x.py"), purpose="p"))
            evaluation = self._evaluate(ledger, scope)
            self.assertIn("E:scope", evaluation.failed)
            self.assertTrue(any("scope violation" in r
                                for r in evaluation.reasons))

    def test_traversal_fails_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate, ledger = self._gate(tmp)
            scope = str(Path(tmp) / "src")
            ledger.append_request(ActionRequest(
                sequence=0, requester="t", capability=Capability.READ,
                target=str(Path(tmp) / "src" / ".." / "secret"),
                purpose="p"))
            evaluation = self._evaluate(ledger, scope)
            self.assertIn("E:scope", evaluation.failed)

    def test_contained_target_passes_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate, ledger = self._gate(tmp)
            scope = str(Path(tmp) / "src")
            ledger.append_request(ActionRequest(
                sequence=0, requester="t", capability=Capability.READ,
                target=str(Path(tmp) / "src" / "a.py"), purpose="p"))
            evaluation = self._evaluate(ledger, scope)
            self.assertIn("E:scope", evaluation.passed)


if __name__ == "__main__":
    unittest.main()
