"""tests.test_capability_fabric — M16.1 Capability Fabric seam tests.

Proves the provider-resolution seam is real: capability -> Fabric ->
Native Provider -> existing ActionRequest -> existing Runtime/Broker/
Policy path. The Fabric grants no authority and never executes.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_fabric import (
    AmbiguousCapabilityError,
    CapabilityFabric,
    CapabilityNotProvidedError,
    DuplicateProviderError,
    NATIVE_PROVIDER_ID,
    NativeCapabilityProvider,
    ProviderNotFoundError,
    default_fabric,
)
from raphael_ibm_bob.contracts import (
    ActionRequest, Capability, Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import default_registry, register_default_skills
from raphael_ibm_bob.workspace import Workspace

NATIVE_CAPS = (Capability.READ, Capability.LIST, Capability.SEARCH,
               Capability.WRITE, Capability.RUN_TEST)


class _StubProvider:
    def __init__(self, provider_id, capabilities):
        self.provider_id = provider_id
        self._capabilities = tuple(capabilities)

    def list_capabilities(self):
        return self._capabilities

    def declaration(self, capability):
        raise NotImplementedError

    def build_action_request(self, *a, **k):
        raise NotImplementedError


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m161_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")

    def mission(self):
        return Mission(mission_id="M-fabric", description="fabric mission",
                       scope="src/", criteria=["c"],
                       problem={"symptom_target": "src/cand.txt"})


class Registration(_Case):
    def test_A_native_provider_registers(self):
        fabric = CapabilityFabric()
        registry = register_default_skills(default_registry())
        fabric.register(NativeCapabilityProvider(registry=registry))
        self.assertEqual(fabric.list_providers(), (NATIVE_PROVIDER_ID,))

    def test_B_registry_lists_native_provider(self):
        self.assertEqual(default_fabric().list_providers(),
                         (NATIVE_PROVIDER_ID,))

    def test_G_duplicate_provider_id_rejected(self):
        fabric = default_fabric()
        with self.assertRaises(DuplicateProviderError):
            fabric.register(NativeCapabilityProvider(
                registry=register_default_skills(default_registry())))

    def test_F_unknown_provider_fails_explicitly(self):
        with self.assertRaises(ProviderNotFoundError):
            default_fabric().get_provider("does-not-exist")

    def test_H_duplicate_capability_claim_is_deterministic(self):
        fabric = default_fabric()
        fabric.register(_StubProvider("other", (Capability.READ,)))
        with self.assertRaises(AmbiguousCapabilityError):
            fabric.resolve(Capability.READ)  # no silent shadowing
        # An explicit provider still resolves deterministically.
        self.assertEqual(
            fabric.resolve(Capability.READ,
                           provider_id="other").provider_id, "other")


class Resolution(_Case):
    def test_C_all_five_native_capabilities_resolve(self):
        fabric = default_fabric()
        for capability in NATIVE_CAPS:
            provider = fabric.resolve(capability)
            self.assertEqual(provider.provider_id, NATIVE_PROVIDER_ID)

    def test_D_resolution_is_deterministic(self):
        fabric = default_fabric()
        first = [fabric.resolve(c).provider_id for c in NATIVE_CAPS]
        second = [default_fabric().resolve(c).provider_id
                  for c in NATIVE_CAPS]
        self.assertEqual(first, second)
        self.assertEqual(fabric.list_providers(), (NATIVE_PROVIDER_ID,))

    def test_E_unknown_capability_fails_explicitly(self):
        fabric = CapabilityFabric()
        fabric.register(_StubProvider("empty", ()))
        with self.assertRaises(CapabilityNotProvidedError):
            fabric.resolve(Capability.READ)
        # A non-Capability value is rejected explicitly, not coerced.
        with self.assertRaises(ValueError):
            fabric.resolve("read")

    def test_I_provider_metadata_matches_native_declarations(self):
        registry = register_default_skills(default_registry())
        provider = NativeCapabilityProvider(registry=registry)
        self.assertEqual(
            set(provider.list_capabilities()),
            {d.capability for d in registry.list_capabilities()})

    def test_J_provider_does_not_invent_definitions(self):
        registry = register_default_skills(default_registry())
        provider = NativeCapabilityProvider(registry=registry)
        for capability in NATIVE_CAPS:
            self.assertIs(provider.declaration(capability),
                          registry.lookup_capability(capability))

    def test_resolve_explicit_provider_must_supply_capability(self):
        fabric = default_fabric()
        fabric.register(_StubProvider("small", (Capability.READ,)))
        with self.assertRaises(CapabilityNotProvidedError):
            fabric.resolve(Capability.WRITE, provider_id="small")


class ActionRequestBoundary(_Case):
    def test_build_action_request_is_ordinary(self):
        provider = default_fabric().resolve(Capability.READ)
        request = provider.build_action_request(Capability.READ,
                                                "src/cand.txt")
        self.assertIsInstance(request, ActionRequest)
        self.assertEqual(request.capability, Capability.READ)
        self.assertEqual(request.target, "src/cand.txt")
        self.assertTrue(request.purpose)
        self.assertEqual(request.requester, f"provider:{NATIVE_PROVIDER_ID}")
        # No authority: it is a plain proposal object.
        self.assertFalse(hasattr(request, "execute"))

    def test_K_resolution_does_not_execute(self):
        provider = default_fabric().resolve(Capability.READ)
        request = provider.build_action_request(Capability.READ,
                                                "src/cand.txt")
        self.assertIsInstance(request, ActionRequest)

    def test_no_credentials(self):
        html = (Path(__file__).resolve().parents[1] /
                "docs" / "capability-fabric.md").read_text("utf-8")
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html.lower())


class Governance(unittest.TestCase):
    def test_L_to_R_fabric_has_no_authority_or_network_tokens(self):
        src = (Path(__file__).resolve().parents[1] / "raphael_ibm_bob" /
               "capability_fabric.py").read_text("utf-8")
        for token in ("import subprocess", "Popen", "import socket",
                      "import urllib", "from urllib", "urlopen",
                      "BOBBroker", "BOBPolicy", "BOBRuntime",
                      "BOBQualityGate", "execute_capability(",
                      "from raphael_ibm_bob.broker",
                      "from raphael_ibm_bob.policy",
                      "from raphael_ibm_bob.runtime",
                      "from raphael_ibm_bob.quality_gate",
                      "from raphael_ibm_bob.capabilities",
                      "while True"):
            self.assertNotIn(token, src, token)


class Integration(_Case):
    """capability -> Fabric -> Native Provider -> ActionRequest ->
    existing Runtime/Broker/Policy path (real contracts, not faked)."""

    def _stack(self):
        run_dir = self.base / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(self.ws)
        ledger = EvidenceLedger(run_dir)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        return BOBRuntime(broker), ledger

    def test_T_seam_connects_to_real_runtime_broker_policy(self):
        provider = default_fabric().resolve(Capability.READ)
        request = provider.build_action_request(Capability.READ,
                                                "src/cand.txt")
        runtime, ledger = self._stack()
        result = runtime.submit(request, self.mission())
        self.assertEqual(result.broker_result.decision.decision.value,
                         "allow")
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        ledger.close()

    def test_U_deny_path_preserved(self):
        provider = default_fabric().resolve(Capability.READ)
        request = provider.build_action_request(Capability.READ,
                                                "/etc/hostname")
        runtime, ledger = self._stack()
        result = runtime.submit(request, self.mission())
        self.assertEqual(result.broker_result.decision.decision.value,
                         "deny")
        self.assertIsNone(result.execution)  # DENY != executed
        ledger.close()


if __name__ == "__main__":
    unittest.main()
