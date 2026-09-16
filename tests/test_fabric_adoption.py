"""tests.test_fabric_adoption — M16.2 model-led Fabric adoption tests.

Proves the real model-proposal path now traverses:

    structured proposal -> declared skill -> declared capability
      -> Capability Fabric -> Native Provider -> ActionRequest
      -> Runtime -> Broker -> Policy -> execution/denial

Uses the real `validate_proposal` (the function the live OpenAI-compatible
adapter calls) and the real Runtime/Broker/Policy stack. It also records
Fabric resolution to prove the proposal actually passed through it.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_fabric import (
    CapabilityFabric,
    CapabilityNotProvidedError,
    NativeCapabilityProvider,
    default_fabric,
)
from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.harness.providers.openai_compat import validate_proposal
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import default_registry, register_default_skills
from raphael_ibm_bob.workspace import Workspace

try:
    from raphael_ibm_bob.harness.providers import StructuredProposalError
except Exception:  # pragma: no cover
    StructuredProposalError = Exception


def _registry():
    return register_default_skills(default_registry())


class _RecordingFabric(CapabilityFabric):
    """Fabric that records every resolve() call (observability proof)."""

    def __init__(self, registry):
        super().__init__()
        self.resolve_calls = []
        self.register(NativeCapabilityProvider(registry=registry))

    def resolve(self, capability, provider_id=None):
        self.resolve_calls.append(capability)
        return super().resolve(capability, provider_id)


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m162_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        self.registry = _registry()

    def mission(self):
        return Mission(mission_id="M-adopt", description="adopt",
                       scope="src/", criteria=["c"],
                       problem={"symptom_target": "src/cand.txt"})

    def _stack(self):
        run_dir = self.base / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(self.ws)
        ledger = EvidenceLedger(run_dir)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        return BOBRuntime(broker), ledger

    def proposal(self, **over):
        data = {"intent": "act", "skill": "read-file",
                "target": "src/cand.txt", "purpose": "inspect"}
        data.update(over)
        return data


class ProposalPath(_Case):
    def test_A_valid_skill_identified(self):
        request = validate_proposal(self.proposal(), self.registry)
        self.assertIsInstance(request, ActionRequest)
        self.assertEqual(request.capability, Capability.READ)

    def test_B_skill_resolves_to_declared_capability(self):
        skill = self.registry.lookup_skill("read-file")
        request = validate_proposal(self.proposal(), self.registry)
        self.assertEqual(request.capability, skill.capability)

    def test_C_capability_resolves_through_fabric(self):
        fabric = _RecordingFabric(self.registry)
        validate_proposal(self.proposal(), self.registry, fabric=fabric)
        self.assertEqual(fabric.resolve_calls, [Capability.READ])

    def test_D_fabric_resolves_native_provider(self):
        provider = default_fabric().resolve(Capability.READ)
        self.assertEqual(provider.provider_id, "raphael-native")

    def test_E_native_provider_prepares_request(self):
        request = validate_proposal(self.proposal(), self.registry)
        self.assertEqual(request.requester, "skill:read-file")
        self.assertEqual(request.timeout_seconds, None)  # READ default
        run_test = validate_proposal(
            self.proposal(skill="run-test", target="src/test_x.py"),
            self.registry)
        self.assertEqual(run_test.capability, Capability.RUN_TEST)

    def test_G_no_registry_propose_bypass_in_model_path(self):
        src = (Path(__file__).resolve().parents[1] / "raphael_ibm_bob" /
               "harness" / "providers" / "openai_compat.py").read_text("utf-8")
        self.assertIn("resolved_fabric.resolve(capability)", src)
        self.assertNotIn("registry.propose(", src)

    def test_H_unknown_skill_fails_explicitly(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(self.proposal(skill="no-such-skill"),
                              self.registry)

    def test_I_unknown_capability_fails_explicitly(self):
        empty = CapabilityFabric()
        with self.assertRaises(StructuredProposalError):
            validate_proposal(self.proposal(), self.registry, fabric=empty)

    def test_J_provider_resolution_failure_fails_explicitly(self):
        empty = CapabilityFabric()
        with self.assertRaises(StructuredProposalError):
            validate_proposal(self.proposal(), self.registry, fabric=empty)

    def test_K_malformed_proposal_never_reaches_fabric(self):
        fabric = _RecordingFabric(self.registry)
        for bad in ({}, {"intent": "act"},
                    {"intent": "act", "skill": "read-file"},
                    {"intent": "bogus", "skill": "read-file",
                     "target": "src/cand.txt", "purpose": "x"}):
            with self.assertRaises(StructuredProposalError):
                validate_proposal(bad, self.registry, fabric=fabric)
        self.assertEqual(fabric.resolve_calls, [])


class FieldPreservation(_Case):
    def test_L_to_Q_fields_preserved(self):
        request = validate_proposal(self.proposal(), self.registry)
        self.assertEqual(request.target, "src/cand.txt")     # L
        self.assertEqual(request.purpose, "inspect")          # M
        self.assertEqual(request.requester, "skill:read-file")  # N
        self.assertIsNone(request.plan_id)                    # O
        self.assertIsNone(request.finding_id)                 # P
        write = validate_proposal(
            self.proposal(skill="write-file", target="src/cand.txt",
                          purpose="fix", content="OK\n"), self.registry)
        self.assertEqual(write.purpose, "content=OK\n")

    def test_Q_timeout_from_declaration(self):
        request = validate_proposal(
            self.proposal(skill="run-test", target="src/cand.txt"),
            self.registry)
        declaration = self.registry.lookup_capability(Capability.RUN_TEST)
        self.assertEqual(request.timeout_seconds, declaration.timeout_seconds)


class Governance(_Case):
    def test_R_fabric_has_no_authority_tokens(self):
        fabric_src = (Path(__file__).resolve().parents[1] / "raphael_ibm_bob" /
                      "capability_fabric.py").read_text("utf-8")
        for token in ("BOBBroker", "BOBPolicy", "BOBRuntime",
                      "BOBQualityGate", "execute_capability(",
                      "import subprocess", "import socket", "import urllib"):
            self.assertNotIn(token, fabric_src, token)

    def test_adapter_does_not_import_authority_layers(self):
        src = (Path(__file__).resolve().parents[1] / "raphael_ibm_bob" /
               "harness" / "providers" / "openai_compat.py").read_text("utf-8")
        for token in ("from raphael_ibm_bob.broker",
                      "from raphael_ibm_bob.policy",
                      "from raphael_ibm_bob.runtime",
                      "from raphael_ibm_bob.quality_gate",
                      "from raphael_ibm_bob.capabilities"):
            self.assertNotIn(token, src, token)


class Integration(_Case):
    """Real proposal -> Fabric -> Native -> ActionRequest -> Runtime/
    Broker/Policy -> execution or denial (real contracts)."""

    def test_F_U_allow_path_executes(self):
        request = validate_proposal(self.proposal(), self.registry)
        runtime, ledger = self._stack()
        result = runtime.submit(request, self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "allow")
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        ledger.close()

    def test_S_T_deny_path_stays_deny(self):
        request = validate_proposal(
            self.proposal(target="/etc/hostname"), self.registry)
        runtime, ledger = self._stack()
        result = runtime.submit(request, self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "deny")
        self.assertIsNone(result.execution)
        ledger.close()

    def test_accessor_adapter_holds_a_fabric(self):
        from raphael_ibm_bob.harness.providers.openai_compat import (
            OpenAICompatAdapter, OpenAICompatConfig)
        adapter = OpenAICompatAdapter(
            OpenAICompatConfig(endpoint="http://x", model="m"), self.registry)
        self.assertEqual(adapter._fabric.resolve(Capability.READ).provider_id,
                         "raphael-native")


if __name__ == "__main__":
    unittest.main()
