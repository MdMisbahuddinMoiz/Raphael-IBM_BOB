"""tests.test_d13_target_agnostic — same fabric, different target state.

Proves the D13 selector is target-agnostic: ONE registry, ONE selector, the
SAME governance core, driven ONLY by observed services + credentials, produce
different capability choices for structurally different synthetic targets
(HTTP / Telnet / HTTP+Telnet / unknown service / missing prerequisite).
"""
from __future__ import annotations

import unittest

from raphael_ibm_bob.capability_bootstrap import register_default
from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)

MISSION_TYPE = "web_enum"


def _facts(host, services, protocols, ports):
    facts = TargetFacts(target_id=f"target_{host}", host=host)
    for port, protocol in services:
        facts.add_service(ServiceRecord(host=host, port=port, protocol=protocol))
    facts.authorization = AuthorizationScope(
        target_host=host, authorized_protocols=frozenset(protocols),
        authorized_ports=frozenset(ports), engagement_id="E-1",
        scope_document_ref="scope://signed/1")
    return facts


class TargetAgnosticFabric(unittest.TestCase):
    def setUp(self):
        self.reg = CapabilityRegistry()
        register_default(self.reg)
        self.selector = CapabilitySelector(self.reg, PrerequisiteEngine())

    def _ids(self, facts, creds=None):
        plan = self.selector.select_and_compose(
            MISSION_TYPE, {"mission_id": "M"}, facts, credential_refs=creds)
        return {s.capability_id for s in plan.steps}

    def test_A_http_target_selects_http_only(self):
        facts = _facts("10.0.0.1", [(80, "http")], ["http"], [80])
        self.assertEqual(self._ids(facts), {"NETWORK_HTTP_REQUEST"})

    def test_B_telnet_target_selects_telnet_only(self):
        facts = _facts("10.0.0.2", [(23, "telnet")], ["telnet"], [23])
        self.assertEqual(self._ids(facts, ["telnet"]),
                         {"NETWORK_TELNET_SESSION"})

    def test_C_http_and_telnet_target_selects_both(self):
        facts = _facts("10.0.0.3", [(80, "http"), (23, "telnet")],
                       ["http", "telnet"], [80, 23])
        self.assertEqual(self._ids(facts, ["telnet"]),
                         {"NETWORK_HTTP_REQUEST", "NETWORK_TELNET_SESSION"})

    def test_D_unknown_service_selects_nothing(self):
        facts = _facts("10.0.0.4", [(70, "gopher")], ["gopher"], [70])
        self.assertEqual(self._ids(facts, ["telnet"]), set())

    def test_E_missing_prerequisite_selects_nothing(self):
        facts = _facts("10.0.0.5", [(23, "telnet")], ["telnet"], [23])
        self.assertEqual(self._ids(facts), set())

    def test_same_selector_serves_all_targets_without_branching(self):
        http = _facts("10.0.0.1", [(80, "http")], ["http"], [80])
        telnet = _facts("10.0.0.2", [(23, "telnet")], ["telnet"], [23])
        both = _facts("10.0.0.3", [(80, "http"), (23, "telnet")],
                      ["http", "telnet"], [80, 23])
        self.assertEqual(self._ids(http), {"NETWORK_HTTP_REQUEST"})
        self.assertEqual(self._ids(telnet, ["telnet"]),
                         {"NETWORK_TELNET_SESSION"})
        self.assertEqual(self._ids(both, ["telnet"]),
                         {"NETWORK_HTTP_REQUEST", "NETWORK_TELNET_SESSION"})


class BridgeFabricParticipation(unittest.TestCase):
    """The governed bridge resolves BOTH network capabilities through the one
    fabric, and refuses any capability the D13 registry does not know about.
    """

    def setUp(self):
        self.reg = CapabilityRegistry()
        register_default(self.reg)

    def _plan(self, capability_id, target):
        plan = ExecutionPlan(plan_id="DP-test", mission_id="M",
                             target_id="target_x")
        plan.add_step(capability_id, {"target": target})
        return plan

    def test_http_and_telnet_both_build_requests_through_one_fabric(self):
        http = plan_to_action_requests(
            self._plan("NETWORK_HTTP_REQUEST", "http://10.0.0.1/"),
            registry=self.reg)
        telnet = plan_to_action_requests(
            self._plan("NETWORK_TELNET_SESSION", "telnet://10.0.0.2:23"),
            registry=self.reg)
        self.assertEqual([r.capability.value for r in http],
                         ["network_http_request"])
        self.assertEqual([r.capability.value for r in telnet],
                         ["network_telnet_session"])

    def test_unregistered_capability_fails_closed(self):
        plan = self._plan("WRITE", "/workspace/out.txt")
        with self.assertRaises(ValueError):
            plan_to_action_requests(plan, registry=self.reg)


if __name__ == "__main__":
    unittest.main()
