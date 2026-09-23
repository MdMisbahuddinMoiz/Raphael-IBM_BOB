"""tests.test_d12_1_remediation — D12.1 gap-closure adversarial tests.

Covers the code-level closures for:
    G1  caller-fabricated completion evidence removed from the Runner
    G2  finding registration always begins UNVERIFIED
    G15 scope containment fails closed on mixed absoluteness
    G19 VPN profile cannot inject a command-line option token
"""
from __future__ import annotations

import inspect
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from raphael_ibm_bob.c1a_scope import scope_contains
from raphael_ibm_bob.contracts import Finding, FindingState
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.runner import Runner
from raphael_ibm_bob.vpn.profile import ProfileError, validate_profile


def _rm(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


class G1RunnerCannotFabricate(unittest.TestCase):
    def test_runner_rejects_caller_authoritative_booleans(self):
        params = inspect.signature(Runner.run).parameters
        for banned in ("regression_ok", "behavior_probe_ok",
                       "verification_ok", "probe_passed", "tests_passed"):
            self.assertNotIn(banned, params,
                             f"{banned} must not be a Runner.run parameter")

    def test_runner_env_true_cannot_override(self):
        params = inspect.signature(Runner.run).parameters
        self.assertNotIn("env", params)
        self.assertNotIn("force", params)


class G2FindingLifecycleEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d121_g2_"))
        self.addCleanup(_rm, self.tmp)
        self.ledger = EvidenceLedger(self.tmp)
        self.addCleanup(self.ledger.close)
        self.store = FindingStore(self.ledger)

    def _finding(self, state):
        return Finding(finding_id=f"F-{state.value}", state=state,
                       summary="s", target="t")

    def test_register_unverified_allowed(self):
        f = self.store.register(self._finding(FindingState.UNVERIFIED))
        self.assertIs(f.state, FindingState.UNVERIFIED)

    def test_register_terminal_states_rejected(self):
        for state in (FindingState.VERIFIED, FindingState.REFUTED,
                      FindingState.SUPERSEDED):
            with self.assertRaises(InvalidTransitionError):
                self.store.register(self._finding(state))


class G15ScopeFailClosed(unittest.TestCase):
    def test_relative_scope_does_not_admit_absolute_target(self):
        self.assertFalse(scope_contains("src", "/ws/evil/src/x"))

    def test_sibling_directory_not_contained(self):
        self.assertFalse(scope_contains("/ws/src", "/ws/src-evil/x"))

    def test_contained_and_sibling_relative(self):
        self.assertTrue(scope_contains("src", "src/app/x.py"))
        self.assertFalse(scope_contains("src", "srcx/app.py"))


class G19VpnProfileArgumentBoundary(unittest.TestCase):
    def test_option_token_rejected(self):
        with self.assertRaises(ProfileError):
            validate_profile("client\n--script-security 2\nremote x 1194\n")

    def test_valid_profile_accepted(self):
        text = textwrap.dedent("""
            client
            dev tun
            remote 10.10.15.1 1194
            <ca>
            -----BEGIN CERTIFICATE-----
            MIIB
            -----END CERTIFICATE-----
            </ca>
        """).strip() + "\n"
        self.assertEqual(validate_profile(text), text)


if __name__ == "__main__":
    unittest.main()
