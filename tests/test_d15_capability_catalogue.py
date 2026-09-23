from __future__ import annotations

import unittest

from raphael_ibm_bob.capability_bootstrap import (
    InertAdapter,
    d15_descriptors,
    register_d15_descriptors,
)
from raphael_ibm_bob.capability_registry import (
    AdapterNotBoundError,
    CapabilityRegistry,
)
from raphael_ibm_bob.capability_selector import ExecutionPlan, plan_to_action_requests


EXPECTED = {
    "NETWORK_SSH_SESSION": ("ssh", frozenset({"service", "authorization", "credential"})),
    "NETWORK_SMB_METADATA": ("smb", frozenset({"service", "authorization"})),
    "NETWORK_TLS_METADATA": ("tls", frozenset({"service", "authorization"})),
    "NETWORK_DNS_METADATA": ("dns", frozenset({"service", "authorization"})),
    "NETWORK_GENERIC_SERVICE_BANNER": (
        "generic-service",
        frozenset({"service", "authorization"}),
    ),
}


class D15CatalogueTests(unittest.TestCase):
    def test_catalogue_contains_all_descriptor_only_capabilities(self) -> None:
        descriptors = d15_descriptors()

        self.assertEqual({descriptor.capability_id for descriptor in descriptors}, set(EXPECTED))
        for descriptor in descriptors:
            protocol, prerequisite_kinds = EXPECTED[descriptor.capability_id]
            self.assertEqual(descriptor.protocol, protocol)
            self.assertEqual(
                {spec.kind for spec in descriptor.prerequisites}, prerequisite_kinds
            )
            self.assertEqual(descriptor.verifier_binding, None)
            self.assertEqual(descriptor.falsifier_binding, None)

    def test_registers_every_descriptor_with_inert_adapter(self) -> None:
        registry = register_d15_descriptors(CapabilityRegistry())

        self.assertEqual(
            {descriptor.capability_id for descriptor in registry.all_capabilities()},
            set(EXPECTED),
        )
        for capability_id in EXPECTED:
            self.assertIsInstance(registry.get_adapter(capability_id), InertAdapter)

    def test_duplicate_registration_fails_closed(self) -> None:
        registry = CapabilityRegistry()
        descriptor = d15_descriptors()[0]
        registry.register(descriptor, InertAdapter())

        with self.assertRaises(ValueError):
            registry.register(descriptor, InertAdapter())

    def test_discovery_matches_each_open_protocol(self) -> None:
        registry = register_d15_descriptors(CapabilityRegistry())

        for capability_id, (protocol, _kinds) in EXPECTED.items():
            found = registry.discover_for_target(
                {"services": [{"protocol": protocol, "state": "open"}]}
            )
            self.assertEqual({descriptor.capability_id for descriptor in found}, {capability_id})

    def test_planning_fails_closed_without_enum_binding(self) -> None:
        registry = register_d15_descriptors(CapabilityRegistry())

        for descriptor in d15_descriptors():
            plan = ExecutionPlan("plan", "mission", "target")
            plan.add_step(descriptor.capability_id, {"target": "host"})
            with self.assertRaises(ValueError):
                plan_to_action_requests(plan, registry=registry)

    def test_inert_execution_fails_closed(self) -> None:
        registry = register_d15_descriptors(CapabilityRegistry())

        for descriptor in d15_descriptors():
            with self.assertRaises(AdapterNotBoundError):
                registry.get_adapter(descriptor.capability_id).execute({}, [], {})


if __name__ == "__main__":
    unittest.main()
