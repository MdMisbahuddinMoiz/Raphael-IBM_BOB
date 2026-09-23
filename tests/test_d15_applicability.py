from __future__ import annotations

import unittest
from dataclasses import replace
from itertools import permutations

from raphael_ibm_bob.capability_bootstrap import (
    InertAdapter,
    network_descriptors,
)
from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import (
    AdapterNotBoundError,
    CapabilityDescriptor,
    CapabilityRegistry,
    PrerequisiteSpec,
)
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.d15_capability_catalogue import d15_descriptors
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
)

_RANKING_TIERS = (
    "D15-10-ARTIFACT",
    "D15-20-SSH",
    "D15-30-SMB",
    "D15-40-TLS",
    "D15-50-DNS",
    "D15-90-GENERIC",
)
_D15_CAPABILITY_IDS = frozenset({
    "NETWORK_SSH_SESSION",
    "NETWORK_SMB_METADATA",
    "NETWORK_TLS_METADATA",
    "NETWORK_DNS_METADATA",
    "NETWORK_GENERIC_SERVICE_BANNER",
})
_NETWORK_DESCRIPTORS = tuple(network_descriptors())
_ALL_DESCRIPTORS = tuple(d15_descriptors()) + _NETWORK_DESCRIPTORS
_ALL_CAPABILITY_IDS = frozenset(
    descriptor.capability_id for descriptor in _ALL_DESCRIPTORS
)


def _facts(protocol: str, *, service: bool = True,
           authorized: bool = True,
           service_state: str = "open") -> TargetFacts:
    facts = TargetFacts(target_id="target-d15", host="198.51.100.15")
    if service:
        facts.add_service(ServiceRecord(
            host=facts.host,
            port=443,
            protocol=protocol,
            state=service_state,
        ))
    if authorized:
        facts.authorization = AuthorizationScope(
            target_host=facts.host,
            authorized_protocols=frozenset({protocol}),
            authorized_ports=frozenset({443}),
            engagement_id="E-D15",
            scope_document_ref="scope://d15",
        )
    return facts


def _selector_plan(descriptor: CapabilityDescriptor,
                   facts: TargetFacts) -> list[str]:
    registry = CapabilityRegistry()
    registry.register(descriptor, InertAdapter())
    credential_refs = [
        prerequisite.predicate
        for prerequisite in descriptor.prerequisite_specs()
        if prerequisite.kind == "credential"
    ]
    plan = CapabilitySelector(registry=registry).select_and_compose(
        "service_interaction",
        {"mission_id": "M-D15"},
        facts,
        credential_refs=credential_refs,
    )
    return [step.capability_id for step in plan.steps]


class D15ApplicabilityTests(unittest.TestCase):
    def test_each_family_is_applicable_for_open_authorized_service(self) -> None:
        descriptors = _ALL_DESCRIPTORS
        self.assertEqual(
            {descriptor.capability_id for descriptor in d15_descriptors()},
            _D15_CAPABILITY_IDS,
        )
        for descriptor in descriptors:
            with self.subTest(capability=descriptor.capability_id):
                credential_refs = [
                    prerequisite.predicate
                    for prerequisite in descriptor.prerequisite_specs()
                    if prerequisite.kind == "credential"
                ]
                result = PrerequisiteEngine().evaluate(
                    descriptor, _facts(descriptor.protocol),
                    credential_refs=credential_refs,
                )
                self.assertTrue(result.satisfied, result.missing)
                self.assertEqual(
                    _selector_plan(descriptor, _facts(descriptor.protocol)),
                    [descriptor.capability_id],
                )

    def test_each_family_is_not_applicable_when_a_prerequisite_is_missing(
            self) -> None:
        for descriptor in _ALL_DESCRIPTORS:
            for missing in ("service", "authorization"):
                with self.subTest(capability=descriptor.capability_id,
                                  missing=missing):
                    facts = _facts(
                        descriptor.protocol,
                        service=missing != "service",
                        authorized=missing != "authorization",
                    )
                    result = PrerequisiteEngine().evaluate(descriptor, facts)
                    self.assertFalse(result.satisfied)
                    self.assertTrue(result.missing)
                    self.assertEqual(_selector_plan(descriptor, facts), [])

    def test_unknown_service_state_is_conservative_and_collapses_to_missing(
            self) -> None:
        engine = PrerequisiteEngine()
        for descriptor in _ALL_DESCRIPTORS:
            missing = engine.evaluate(
                descriptor,
                _facts(descriptor.protocol, service=False),
            )
            for state in ("filtered", "closed"):
                with self.subTest(capability=descriptor.capability_id,
                                  state=state):
                    unknown = engine.evaluate(
                        descriptor,
                        _facts(descriptor.protocol, service_state=state),
                    )
                    self.assertFalse(unknown.satisfied)
                    self.assertEqual(unknown.missing, missing.missing)
                    self.assertEqual(unknown.evaluated, missing.evaluated)
                    self.assertEqual(
                        _selector_plan(
                            descriptor,
                            _facts(descriptor.protocol, service_state=state),
                        ),
                        [],
                    )

    def test_unknown_prerequisite_kind_is_not_applicable_for_each_family(
            self) -> None:
        engine = PrerequisiteEngine()
        for descriptor in _ALL_DESCRIPTORS:
            unknown = PrerequisiteSpec(
                kind="unsupported-kind",
                predicate="available",
                description="unknown prerequisite",
            )
            unknown_descriptor = replace(
                descriptor,
                prerequisites=descriptor.prerequisites | frozenset({unknown}),
            )
            with self.subTest(capability=descriptor.capability_id):
                result = engine.evaluate(
                    unknown_descriptor, _facts(descriptor.protocol),
                )
                self.assertFalse(result.satisfied)
                self.assertTrue(
                    any("unsupported-kind" in item for item in result.missing),
                )
                self.assertEqual(
                    _selector_plan(unknown_descriptor,
                                   _facts(descriptor.protocol)),
                    [],
                )

    def test_selector_is_deterministic_and_permutation_invariant(
            self) -> None:
        descriptors = _ALL_DESCRIPTORS
        expected_signature: tuple[str, tuple[str, ...]] | None = None
        for ordered in permutations(descriptors):
            registry = CapabilityRegistry()
            for descriptor in ordered:
                registry.register(descriptor, InertAdapter())
            facts = TargetFacts(target_id="target-d15", host="198.51.100.15")
            for descriptor in ordered:
                facts.add_service(ServiceRecord(
                    host=facts.host, port=443, protocol=descriptor.protocol,
                    state="open",
                ))
            facts.authorization = AuthorizationScope(
                target_host=facts.host,
                authorized_protocols=frozenset(d.protocol for d in ordered),
                authorized_ports=frozenset({443}),
                engagement_id="E-D15",
                scope_document_ref="scope://d15",
            )
            plan = CapabilitySelector(registry=registry).select_and_compose(
                "service_interaction",
                {"mission_id": "M-D15"},
                facts,
                credential_refs=[
                    prerequisite.predicate
                    for descriptor in ordered
                    for prerequisite in descriptor.prerequisite_specs()
                    if prerequisite.kind == "credential"
                ],
            )
            self.assertEqual(
                {step.capability_id for step in plan.steps},
                _ALL_CAPABILITY_IDS,
            )
            signature = (
                plan.plan_id,
                tuple(sorted(step.capability_id for step in plan.steps)),
            )
            if expected_signature is None:
                expected_signature = signature
            self.assertEqual(signature, expected_signature)

    def test_generic_banner_is_selectable_but_bridge_execution_fails_closed(
            self) -> None:
        descriptor = next(
            item for item in d15_descriptors()
            if item.capability_id == "NETWORK_GENERIC_SERVICE_BANNER"
        )
        registry = CapabilityRegistry()
        registry.register(descriptor, InertAdapter())
        plan = CapabilitySelector(registry).select_and_compose(
            "service_interaction",
            {"mission_id": "M-D15"},
            _facts(descriptor.protocol),
        )
        self.assertEqual(
            [step.capability_id for step in plan.steps],
            [descriptor.capability_id],
        )

        single = ExecutionPlan("DP-D15-generic", "M-D15", "target-d15")
        single.add_step(
            descriptor.capability_id,
            {"target": "198.51.100.15"},
        )
        with self.assertRaisesRegex(ValueError, "no governed Capability enum binding"):
            plan_to_action_requests(single, registry=registry)
        with self.assertRaises(AdapterNotBoundError):
            registry.get_adapter(descriptor.capability_id).execute({}, [], {})

if __name__ == "__main__":
    unittest.main()
