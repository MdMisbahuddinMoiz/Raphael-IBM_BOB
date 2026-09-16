"""tests.test_capability_arsenal — M15.9 Capability Arsenal tests.

The screen is a read-only catalog of the authoritative capability /
skill / role declarations exposed through `harness.api`. Declarations
grant no authority; the page must say so and must expose no execution
controls.
"""
from __future__ import annotations

import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig, Request, create_server, dispatch,
)
from raphael_ibm_bob.http.views import capability_arsenal as ca


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = RaphaelHTTPConfig(runs_root=Path("runs"),
                                     sessions_root=Path("sessions"),
                                     host="127.0.0.1", port=0)

    def render(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/capabilities"), self.cfg)
        return response.status, response.content_type, response.body


class Render(_Case):
    def test_A_route_exists(self):
        status, ctype, html = self.render()
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Capability Arsenal", html)

    def test_B_registry_state_renders(self):
        data = ca.collect()
        self.assertEqual(data["counts"]["roles"], len(api.list_roles()))
        self.assertEqual(data["counts"]["skills"], len(api.list_skills()))
        self.assertEqual(data["counts"]["capabilities"],
                         len(api.list_capabilities()))
        _, _, html = self.render()
        self.assertIn("ARSENAL SUMMARY", html)

    def test_C_real_roles_render(self):
        _, _, html = self.render()
        for role in api.list_roles():
            self.assertIn(role.id, html)
            self.assertIn(role.name, html)

    def test_D_real_skills_render(self):
        _, _, html = self.render()
        for skill in api.list_skills():
            self.assertIn(skill.id, html)
            self.assertIn(skill.version, html)

    def test_E_real_capabilities_render(self):
        _, _, html = self.render()
        for cap in api.list_capabilities():
            self.assertIn(cap.capability.value, html)
            self.assertIn(cap.description, html)

    def test_F_role_skill_relationship_is_real(self):
        skills = api.list_skills()
        data = ca.collect()
        by_role = {r["id"]: r["skills"] for r in data["roles"]}
        for skill in skills:
            self.assertIn(skill.id, by_role.get(skill.role, []),
                          f"{skill.id} not bound to {skill.role}")
        _, _, html = self.render()
        self.assertIn("DECLARED RELATIONSHIP", html)

    def test_G_skill_capability_relationship_is_real(self):
        data = ca.collect()
        caps = {c["id"]: c for c in data["capabilities"]}
        for skill in api.list_skills():
            self.assertIn(skill.id, caps[skill.capability.value]["skills"])
        _, _, html = self.render()
        self.assertIn("read-file", html)
        self.assertIn("skill:read:{target}", html)

    def test_H_evidence_produced_is_real(self):
        _, _, html = self.render()
        for cap in api.list_capabilities():
            for kind in cap.evidence_produced:
                self.assertIn(kind, html, f"{cap.capability.value}:{kind}")

    def test_I_evidence_consumed_is_real(self):
        _, _, html = self.render()
        for cap in api.list_capabilities():
            for kind in cap.evidence_consumed:
                self.assertIn(kind, html, f"{cap.capability.value}:{kind}")

    def test_J_prerequisites_are_real(self):
        data = ca.collect()
        for skill in api.list_skills():
            row = [s for s in data["skills"] if s["id"] == skill.id][0]
            self.assertEqual(row["prerequisites"],
                             list(skill.prerequisites))
        _, _, html = self.render()
        self.assertIn("PREREQUISITES", html)
        self.assertIn("NONE DECLARED", html)

    def test_K_version_and_target_template_real(self):
        _, _, html = self.render()
        self.assertIn("TARGET SCHEMA", html)
        self.assertIn("PURPOSE TEMPLATE", html)
        self.assertIn("relative file path inside the workspace", html)

    def test_L_unresolvable_relationships_honest(self):
        data = ca.collect()
        self.assertEqual(data["unresolved_skills"], [])
        _, _, html = self.render()
        # roles with no declared skills say so, not invented ones
        self.assertIn("NONE DECLARED", html)


class Safety(_Case):
    def test_M_search_and_filter(self):
        _, _, html = self.render()
        self.assertIn('data-filter="roles"', html)
        self.assertIn('data-kind="skills"', html)
        self.assertIn('id="search"', html)
        self.assertIn("data-search=", html)
        self.assertNotIn("?role=", html)

    def test_N_no_execute_run_controls(self):
        _, _, html = self.render()
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        for control in (">RUN<", ">EXECUTE<", ">ENABLE<", ">DISABLE<",
                        ">ACTIVATE<", ">APPROVE<", ">REPLAN<"):
            self.assertNotIn(control, html, control)

    def test_O_no_fabricated_authorization(self):
        _, _, html = self.render()
        upper = html
        for claim in ("ENABLED FOR EXECUTION", "READY TO EXECUTE",
                      "AUTHORIZED CAPABILITY", "APPROVED FOR EXECUTION",
                      "ACTIVE ATTACK TOOL"):
            self.assertNotIn(claim, upper, claim)
        self.assertIn("DECLARATION ≠ AUTHORIZATION", html)

    def test_P_no_credentials(self):
        _, _, html = self.render()
        lower = html.lower()
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", lower)
        self.assertNotIn("authorization:", lower)   # header form only
        self.assertNotIn("bearer ", lower)

    def test_Q_no_direct_execution_path(self):
        _, _, html = self.render()
        self.assertNotIn("execute_capability", html)
        self.assertNotIn("/operations/start", html)

    def test_R_governance_static(self):
        root = Path(ca.__file__).resolve().parents[2]
        view = (root / "http" / "views" /
                "capability_arsenal.py").read_text("utf-8")
        route = (root / "http" / "routes" /
                 "capabilities.py").read_text("utf-8")
        self.assertIn("harness import api", view)
        for name, src in (("view", view), ("route", route)):
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal", "append_evidence",
                          "append_gate", "EvidenceLedger", "LedgerWriter",
                          "FindingStore", ".transition(",
                          "run_model_mission(", "while True"):
                self.assertNotIn(token, src, f"{token} in {name}")


class Regression(_Case):
    def test_S_command_center(self):
        response = dispatch(Request(method="GET", path="/command"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("/operations/capabilities", response.body)

    def test_T_findings(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/findings"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Findings Intelligence", response.body)

    def test_U_evidence(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/evidence"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Evidence Intelligence", response.body)

    def test_V_gate(self):
        response = dispatch(Request(method="GET",
                                    path="/operations/gate"), self.cfg)
        self.assertEqual(response.status, 200)
        self.assertIn("Policy &amp; Quality Gate", response.body)

    def test_W_decision_trace_route_reachable(self):
        # A literal route must not shadow the per-run console route.
        response = dispatch(Request(method="GET",
                                    path="/operations/some-run"), self.cfg)
        self.assertIn(response.status, (404, 200))

    def test_X_event_stream_route_reachable(self):
        response = dispatch(Request(
            method="GET", path="/operations/some-run/events"), self.cfg)
        self.assertIn(response.status, (404, 200))

    def test_served_over_http(self):
        import http.client
        server = create_server(self.cfg)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", "/operations/capabilities")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Capability Arsenal", body)


if __name__ == "__main__":
    unittest.main()
