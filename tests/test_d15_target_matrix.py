"""Deterministic D15 target-state selection matrix.

The matrix exercises only synthetic ``TargetFacts`` and ``WorldState`` values.
The APIs under test are ``ServiceRecord``, ``AuthorizationScope``,
``TargetFacts``, ``initial_world_state``, ``CapabilityRegistry``,
``register_default``, ``register_d15_descriptors``,
``CapabilitySelector.select_and_compose``, and
``plan_to_action_requests``.  No target is contacted and no adapter executes.
"""
from __future__ import annotations

import unittest
from typing import Final

from raphael_ibm_bob.capability_bootstrap import InertAdapter, register_default
from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import (
    AdapterNotBoundError,
    CapabilityRegistry,
)
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.d14_world_state import WorldState, initial_world_state
from raphael_ibm_bob.d15_capability_catalogue import (
    d15_descriptors,
    register_d15_descriptors,
)
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)


HOST: Final = "synthetic.invalid"
MISSION: Final = Mission(
    mission_id="M-D15-synthetic",
    description="D15 synthetic target matrix",
    scope="scope://synthetic/d15",
)
D15_CAPABILITY_IDS: Final = frozenset(
    {
        "NETWORK_SSH_SESSION",
        "NETWORK_SMB_METADATA",
        "NETWORK_TLS_METADATA",
        "NETWORK_DNS_METADATA",
        "NETWORK_GENERIC_SERVICE_BANNER",
    }
)


def _ids(*capability_ids: str) -> frozenset[str]:
    return frozenset(capability_ids)


MATRIX: Final = (
    ("http-only", (("http", 80),), (), _ids("NETWORK_HTTP_REQUEST")),
    ("telnet-only", (("telnet", 23),), ("telnet-valid",), _ids("NETWORK_TELNET_SESSION")),
    (
        "http-and-telnet",
        (("http", 80), ("telnet", 23)),
        ("telnet-valid",),
        _ids("NETWORK_HTTP_REQUEST", "NETWORK_TELNET_SESSION"),
    ),
    ("ssh-observed", (("ssh", 22),), ("ssh_valid",), _ids("NETWORK_SSH_SESSION")),
    ("smb-observed", (("smb", 445),), (), _ids("NETWORK_SMB_METADATA")),
    ("tls-observed", (("tls", 443),), (), _ids("NETWORK_TLS_METADATA")),
    ("dns-observed", (("dns", 53),), (), _ids("NETWORK_DNS_METADATA")),
    ("unknown-service-banner", (("generic-service", 9999),), (), _ids("NETWORK_GENERIC_SERVICE_BANNER")),
    ("mixed-http-and-tls", (("http", 80), ("tls", 443)), (), _ids("NETWORK_HTTP_REQUEST", "NETWORK_TLS_METADATA")),
    (
        "mixed",
        (("http", 80), ("telnet", 23), ("ssh", 22), ("smb", 445),
         ("tls", 443), ("dns", 53), ("generic-service", 9999)),
        ("telnet-valid", "ssh_valid"),
        _ids(
            "NETWORK_HTTP_REQUEST",
            "NETWORK_TELNET_SESSION",
            "NETWORK_SSH_SESSION",
            "NETWORK_SMB_METADATA",
            "NETWORK_TLS_METADATA",
            "NETWORK_DNS_METADATA",
            "NETWORK_GENERIC_SERVICE_BANNER",
        ),
    ),
    ("unsupported-unknown-service", (("gopher", 70),), (), _ids()),
    ("missing-telnet-credential", (("telnet", 23),), (), _ids()),
)


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_default(registry)
    register_d15_descriptors(registry)
    return registry


def _facts(
    services: tuple[tuple[str, int], ...],
    credentials: tuple[str, ...] = (),
    scope: AuthorizationScope | None = None,
) -> TargetFacts:
    facts = TargetFacts(
        target_id="synthetic-target",
        host=HOST,
        credential_refs=list(credentials),
        mission_id=MISSION.mission_id,
    )
    for protocol, port in services:
        facts.add_service(ServiceRecord(
            HOST, port, protocol, state="open", source="manual", discovered_at=0.0,
        ))
    facts.authorization = scope or AuthorizationScope(
        target_host=HOST,
        authorized_protocols=frozenset(protocol for protocol, _ in services),
        authorized_ports=frozenset(port for _, port in services),
        engagement_id="E-D15-synthetic",
        scope_document_ref="scope://synthetic/d15",
    )
    return facts


def _state(
    services: tuple[tuple[str, int], ...],
    credentials: tuple[str, ...] = (),
    scope: AuthorizationScope | None = None,
) -> WorldState:
    return initial_world_state(MISSION, _facts(services, credentials, scope))


def _selected_ids(selector: CapabilitySelector, state: WorldState) -> frozenset[str]:
    plan = selector.select_and_compose(
        mission_type="service_interaction",
        mission_params={"mission_id": state.mission_id},
        facts=state.facts,
        credential_refs=state.facts.credential_refs,
    )
    return frozenset(step.capability_id for step in plan.steps)


class D15TargetMatrixTests(unittest.TestCase):
    def test_registry_contains_only_inert_d15_declarations(self) -> None:
        registry = _registry()

        self.assertTrue(D15_CAPABILITY_IDS <= {
            descriptor.capability_id
            for descriptor in registry.all_capabilities()
        })
        for capability_id in D15_CAPABILITY_IDS:
            with self.subTest(capability_id=capability_id):
                self.assertIsInstance(
                    registry.get_adapter(capability_id),
                    InertAdapter,
                )

    def test_matrix_selects_expected_capabilities_from_synthetic_worlds(self) -> None:
        registry = _registry()
        selector = CapabilitySelector(
            registry=registry,
            prerequisite_engine=PrerequisiteEngine(),
        )

        for name, services, credentials, expected in MATRIX:
            with self.subTest(world=name):
                selected = _selected_ids(
                    selector,
                    _state(services, credentials),
                )
                self.assertEqual(selected, expected)

    def test_same_selector_changes_when_only_observed_services_change(self) -> None:
        registry = _registry()
        selector = CapabilitySelector(registry, PrerequisiteEngine())
        shared_scope = AuthorizationScope(
            target_host=HOST,
            authorized_protocols=frozenset(
                {"http", "telnet", "ssh", "smb", "tls", "generic-service"},
            ),
            authorized_ports=frozenset({22, 23, 70, 80, 443, 445, 9999}),
            engagement_id="E-D15-shared",
            scope_document_ref="scope://synthetic/d15/shared",
        )
        shared_credentials = ("ssh_valid", "telnet-valid")
        worlds = {
            "A": (("http", 80), ("tls", 443)),
            "B": (("telnet", 23),),
            "C": (("ssh", 22), ("smb", 445)),
            "D": (("http", 80), ("telnet", 23), ("generic-service", 9999)),
        }
        expected = {
            "A": frozenset({"NETWORK_HTTP_REQUEST", "NETWORK_TLS_METADATA"}),
            "B": frozenset({"NETWORK_TELNET_SESSION"}),
            "C": frozenset({"NETWORK_SSH_SESSION", "NETWORK_SMB_METADATA"}),
            "D": frozenset(
                {
                    "NETWORK_HTTP_REQUEST",
                    "NETWORK_TELNET_SESSION",
                    "NETWORK_GENERIC_SERVICE_BANNER",
                },
            ),
        }

        states = {
            name: _state(services, shared_credentials, shared_scope)
            for name, services in worlds.items()
        }
        selected = {
            name: _selected_ids(selector, state)
            for name, state in states.items()
        }

        self.assertEqual(selected, expected)
        self.assertEqual(len(set(selected.values())), len(selected))
        self.assertEqual(
            {state.facts.authorization for state in states.values()},
            {shared_scope},
        )
        self.assertEqual(
            {tuple(state.facts.credential_refs) for state in states.values()},
            {shared_credentials},
        )

    def test_missing_prerequisite_is_not_ready_even_when_service_is_observed(self) -> None:
        registry = _registry()
        facts = _facts((("telnet", 23),))
        discovered = registry.discover_for_target(facts.to_facts())
        self.assertEqual(
            {descriptor.capability_id for descriptor in discovered},
            {"NETWORK_TELNET_SESSION"},
        )

        selected = _selected_ids(
            CapabilitySelector(registry),
            initial_world_state(MISSION, facts),
        )
        self.assertEqual(selected, frozenset())

    def test_unbound_d15_descriptor_fails_closed_before_request_creation(self) -> None:
        registry = _registry()
        descriptor = next(
            item for item in d15_descriptors()
            if item.capability_id == "NETWORK_SMB_METADATA"
        )
        plan = ExecutionPlan(
            plan_id="DP-D15-unbound",
            mission_id=MISSION.mission_id,
            target_id="synthetic-target",
        )
        plan.add_step(
            descriptor.capability_id,
            {"target": "synthetic.invalid"},
            purpose="metadata declaration only",
        )

        with self.assertRaisesRegex(ValueError, "no governed Capability enum binding"):
            plan_to_action_requests(plan, registry=registry)

        self.assertIsInstance(registry.get_adapter(descriptor.capability_id), InertAdapter)
        with self.assertRaises(AdapterNotBoundError):
            registry.get_adapter(descriptor.capability_id).execute({}, [], {})


if __name__ == "__main__":
    unittest.main()
