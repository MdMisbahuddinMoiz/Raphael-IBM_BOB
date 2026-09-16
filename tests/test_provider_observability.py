"""tests.test_provider_observability — M16.4 tests.

The Capability Arsenal exposes provider identity sourced from the
authoritative Capability Fabric (never hardcoded), read-only, with no
execution/authorization implication.
"""
from __future__ import annotations

import unittest
import unittest.mock as mock
from pathlib import Path

from raphael_ibm_bob.capability_fabric import (
    NATIVE_PROVIDER_ID, CapabilityFabric, default_fabric,
)
from raphael_ibm_bob.contracts import Capability
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig, Request, dispatch,
)
from raphael_ibm_bob.http.views import capability_arsenal as ca

ROOT = Path(ca.__file__).resolve().parents[2]
VIEW_SRC = (ROOT / "http" / "views" / "capability_arsenal.py").read_text("utf-8")


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = RaphaelHTTPConfig(runs_root=ROOT / "runs",
                                     sessions_root=ROOT / "sessions")

    def page(self):
        r = dispatch(Request(method="GET",
                             path="/operations/capabilities"), self.cfg)
        return r.status, r.body


class ProviderObservability(_Case):
    def test_A_arsenal_still_renders(self):
        status, html = self.page()
        self.assertEqual(status, 200)
        self.assertIn("Capability Arsenal", html)

    def test_B_provider_from_authoritative_fabric(self):
        expected = default_fabric().list_providers()
        status, html = self.page()
        for provider_id in expected:
            self.assertIn(provider_id, html)
        data = ca.collect()
        self.assertEqual(data["providers"], list(expected))
        for cap in data["capabilities"]:
            self.assertIn(cap["provider"], expected)

    def test_C_provider_not_hardcoded_in_template(self):
        # The provider id must come from data, not from the view source.
        self.assertNotIn(NATIVE_PROVIDER_ID, VIEW_SRC)
        self.assertNotIn("raphael-native", VIEW_SRC)
        _, html = self.page()
        self.assertIn(NATIVE_PROVIDER_ID, html)

    def test_D_native_mappings_resolve_consistently(self):
        fabric = default_fabric()
        data = ca.collect()
        for cap in data["capabilities"]:
            claimants = tuple(fabric.providers_for(Capability(cap["id"])))
            self.assertEqual(cap["provider_claimants"], list(claimants))
            self.assertEqual(cap["provider"], claimants[0])

    def test_E_unknown_provider_state_honest(self):
        empty = CapabilityFabric()
        with mock.patch(
                "raphael_ibm_bob.http.views.capability_arsenal.default_fabric",
                return_value=empty):
            _, html = self.page()
        self.assertIn("UNRESOLVED", html)
        self.assertIn("UNKNOWN / NOT VERIFIED (no single claimant)", html)
        self.assertIn("UNKNOWN / NOT VERIFIED", html)

    def test_F_no_fake_provider_availability(self):
        _, html = self.page()
        for fake in (">AVAILABLE<", ">CONNECTED<", ">READY<", ">OFFLINE<",
                     ">ACTIVE PROVIDER<"):
            self.assertNotIn(fake, html, fake)

    def test_G_no_authorization_claim(self):
        _, html = self.page()
        for claim in ("ENABLED FOR EXECUTION", "READY TO EXECUTE",
                      "AUTHORIZED PROVIDER", "APPROVED PROVIDER",
                      "provider_id = permission"):
            self.assertNotIn(claim, html, claim)
        self.assertIn("PROVIDER RESOLUTION ≠ AUTHORIZATION", html)
        self.assertIn("PROVIDER RESOLUTION ≠ EXECUTION", html)

    def test_H_no_execution_controls(self):
        _, html = self.page()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        for control in (">RUN<", ">EXECUTE<", ">ENABLE<", ">DISABLE<",
                        ">ACTIVATE<", ">APPROVE<", ">REPLAN<"):
            self.assertNotIn(control, html, control)

    def test_I_no_provider_mutation(self):
        _, html = self.page()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        for token in ("register_provider", "registerProvider",
                      "provider-register", "/operations/providers"):
            self.assertNotIn(token, html, token)

    def test_J_roles_skills_do_not_inherit_provider_authority(self):
        _, html = self.page()
        # Provider cells belong to capabilities only, not roles.
        self.assertEqual(html.count('class="aprov mono"'),
                         len(ca.collect()["capabilities"]))
        self.assertNotIn("role → provider", html.lower())

    def test_K_relationships_correct(self):
        data = ca.collect()
        for skill in data["skills"]:
            cap = [c for c in data["capabilities"]
                   if c["id"] == skill["capability"]][0]
            self.assertEqual(skill["provider"], cap["provider"])
        _, html = self.page()
        self.assertIn("RESOLVED PROVIDER", html)
        self.assertIn("PROVIDER CAPABILITY CLAIM", html)


class Governance(unittest.TestCase):
    def test_view_has_no_authority_tokens(self):
        for token in ("execute_capability(", "BOBBroker", "BOBPolicy",
                      "BOBRuntime", "BOBQualityGate", "import subprocess",
                      "import socket", "import urllib",
                      "from raphael_ibm_bob.broker",
                      "from raphael_ibm_bob.policy",
                      "from raphael_ibm_bob.runtime",
                      "from raphael_ibm_bob.capabilities"):
            self.assertNotIn(token, VIEW_SRC, token)
        self.assertIn("capability_fabric import default_fabric", VIEW_SRC)

    def test_no_credentials(self):
        cfg = RaphaelHTTPConfig(runs_root=ROOT / "runs",
                                sessions_root=ROOT / "sessions")
        html = dispatch(Request(method="GET",
                                path="/operations/capabilities"), cfg).body
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html.lower())


if __name__ == "__main__":
    unittest.main()
