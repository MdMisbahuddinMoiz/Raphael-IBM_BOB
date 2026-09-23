from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import InertAdapter
from raphael_ibm_bob.capability_registry import (
    AdapterNotBoundError,
    CapabilityDescriptor,
    CapabilityRegistry,
)
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Decision,
    ExecutionResult,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.policy import BOBPolicy, PolicyCapabilityMetadata
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.workspace import Workspace


class SyntheticAdapter:
    def execute_governed(
        self, request: ActionRequest, mission: Mission, decision: PolicyDecision,
    ) -> ExecutionResult:
        return ExecutionResult(
            sequence=request.sequence,
            success=True,
            output="synthetic-observed",
            evidence={
                "capability_id": request.capability,
                "mission_id": mission.mission_id,
                "decision": decision.decision.value,
            },
        )


class D15GenericBridgeTests(unittest.TestCase):
    def test_synthetic_capability_uses_registry_policy_and_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            registry = CapabilityRegistry()
            capability_id = "SYNTHETIC_OBSERVATION"
            descriptor = CapabilityDescriptor(
                capability_id=capability_id,
                protocol="synthetic",
                description="test-only executable capability",
                prerequisites=frozenset(),
                authorization_scope="mission",
                evidence_schema="synthetic_observation_v1",
                execution_adapter="tests.synthetic",
                verifier_binding=None,
                falsifier_binding=None,
                mission_types=frozenset({"synthetic"}),
            )
            registry.register(descriptor, SyntheticAdapter())
            policy = BOBPolicy(workspace)
            policy.register_capability(
                capability_id,
                PolicyCapabilityMetadata(scope="mission"),
            )
            broker = BOBBroker(policy, workspace, registry=registry)
            runtime = BOBRuntime(broker)
            mission = Mission(
                mission_id="M-synthetic",
                description="synthetic bridge",
                scope="synthetic-target",
                criteria=["observe"],
            )
            request = ActionRequest(
                sequence=0,
                requester="test",
                capability=capability_id,
                target="synthetic-target",
                purpose="synthetic observation",
            )

            result = runtime.submit(request, mission)

            self.assertIs(result.broker_result.decision.decision, Decision.ALLOW)
            self.assertIsNotNone(result.execution)
            self.assertEqual(result.execution.output, "synthetic-observed")

    def test_descriptor_without_executable_adapter_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            registry = CapabilityRegistry()
            capability_id = "SYNTHETIC_DECLARATION_ONLY"
            registry.register(
                CapabilityDescriptor(
                    capability_id=capability_id,
                    protocol="synthetic",
                    description="test-only declaration",
                    prerequisites=frozenset(),
                    authorization_scope="mission",
                    evidence_schema="synthetic_observation_v1",
                    execution_adapter="tests.inert",
                    verifier_binding=None,
                    falsifier_binding=None,
                    mission_types=frozenset({"synthetic"}),
                ),
                InertAdapter(),
            )
            policy = BOBPolicy(workspace)
            policy.register_capability(
                capability_id,
                PolicyCapabilityMetadata(scope="mission"),
            )
            runtime = BOBRuntime(BOBBroker(policy, workspace, registry=registry))
            mission = Mission("M-declaration", "test", "target", ["observe"])
            request = ActionRequest(
                sequence=0, requester="test", capability=capability_id,
                target="target", purpose="declaration-only",
            )

            with self.assertRaises(AdapterNotBoundError):
                runtime.submit(request, mission)

    def test_unregistered_capability_is_refused_before_adapter_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            policy = BOBPolicy(workspace)
            broker = BOBBroker(policy, workspace, registry=CapabilityRegistry())
            mission = Mission("M-unregistered", "test", "target", ["observe"])
            request = ActionRequest(
                sequence=0,
                requester="test",
                capability="UNREGISTERED",
                target="target",
                purpose="unregistered",
            )

            result = broker.submit(request, mission)

            self.assertIs(result.decision.decision, Decision.DENY)
            self.assertEqual(result.decision.reason, "capability-not-allowed:UNREGISTERED")
            self.assertFalse(result.capability_invoked)


if __name__ == "__main__":
    unittest.main()
