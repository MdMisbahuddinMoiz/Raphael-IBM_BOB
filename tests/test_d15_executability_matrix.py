"""Deterministic D15 descriptor-versus-executable proof matrix.

All target states and provider outcomes are synthetic.  HTTP and Telnet use
injected offline mediators, while SSH/SMB/TLS/DNS/banner remain declarations
with no enum binding or governed adapter.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Final

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import (
    InertAdapter,
    MediatedAdapter,
    bind_governed_adapters,
)
from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import AdapterNotBoundError
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.contracts import Capability, Decision, Mission, ActionRequest
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.network_runtime import NetworkMediator
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.target_service_model import TargetFacts
from raphael_ibm_bob.telnet_runtime import TelnetMediator, TelnetState
from raphael_ibm_bob.workspace import Workspace
from tests.test_d15_target_matrix import MATRIX, _registry, _state


HOST: Final = "198.51.100.15"
MISSION: Final = Mission(
    mission_id="M-D15-executability",
    description="synthetic D15 execution matrix",
    scope="",
    criteria=["matrix is governed"],
    problem={
        "telnet": {
            "username": "synthetic-user",
            "password": "synthetic-secret",
            "commands": ["pwd"],
            "flag_command": "pwd",
            "flag_pattern": "^/synthetic$",
        }
    },
)

CAPABILITY_MATRIX: Final = (
    ("HTTP", "NETWORK_HTTP_REQUEST", "http", True, True, True),
    ("Telnet", "NETWORK_TELNET_SESSION", "telnet", True, True, True),
    ("SSH", "NETWORK_SSH_SESSION", "ssh", True, False, False),
    ("SMB", "NETWORK_SMB_METADATA", "smb", True, False, False),
    ("TLS", "NETWORK_TLS_METADATA", "tls", True, False, False),
    ("DNS", "NETWORK_DNS_METADATA", "dns", True, False, False),
    ("Banner", "NETWORK_GENERIC_SERVICE_BANNER", "generic-service", True, False, False),
)
DESCRIPTOR_ONLY: Final = frozenset(
    capability_id
    for _label, capability_id, _protocol, _descriptor, adapter, _executable
    in CAPABILITY_MATRIX
    if not adapter
)
def _selected_ids(selector: CapabilitySelector, facts: TargetFacts) -> frozenset[str]:
    plan = selector.select_and_compose(
        "service_interaction",
        {"mission_id": MISSION.mission_id},
        facts,
        credential_refs=facts.credential_refs,
    )
    return frozenset(step.capability_id for step in plan.steps)


class D15ExecutabilityMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="d15_matrix_")
        self.workspace = Workspace(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _runtime(
        self,
        store: TargetStore,
        *,
        network_mediator: NetworkMediator | None = None,
        telnet_mediator: TelnetMediator | None = None,
    ) -> tuple[BOBRuntime, EvidenceLedger]:
        ledger = EvidenceLedger(Path(self.tempdir.name) / "run")
        self.addCleanup(ledger.close)
        broker = BOBBroker(
            BOBPolicy(self.workspace, target_store=store),
            self.workspace,
            ledger=ledger,
            network_mediator=network_mediator,
            target_store=store,
            telnet_mediator=telnet_mediator,
        )
        return BOBRuntime(broker), ledger

    def test_matrix_has_descriptor_adapter_and_executable_contract(self) -> None:
        registry = _registry()
        runtime, _ledger = self._runtime(TargetStore())
        bind_governed_adapters(registry, runtime, MISSION)

        self.assertEqual(
            {descriptor.capability_id for descriptor in registry.all_capabilities()},
            {row[1] for row in CAPABILITY_MATRIX},
        )
        for label, capability_id, _protocol, descriptor, adapter, executable in CAPABILITY_MATRIX:
            with self.subTest(capability=label):
                self.assertEqual(registry.has(capability_id), descriptor)
                self.assertEqual(
                    isinstance(registry.get_adapter(capability_id), MediatedAdapter),
                    adapter,
                )
                self.assertEqual(capability_id in Capability.__members__, executable)

    def test_target_agnostic_states_select_descriptors(self) -> None:
        selector = CapabilitySelector(_registry(), PrerequisiteEngine())
        for name, services, credentials, expected in MATRIX:
            with self.subTest(state=name):
                self.assertEqual(
                    _selected_ids(selector, _state(services, credentials).facts),
                    expected,
                )

    def test_descriptor_only_selection_and_execution_fail_closed(self) -> None:
        registry = _registry()
        selector = CapabilitySelector(registry, PrerequisiteEngine())
        for name, services, credentials, _expected in MATRIX:
            facts = _state(services, credentials).facts
            plan = selector.select_and_compose(
                "service_interaction",
                {"mission_id": MISSION.mission_id},
                facts,
                credential_refs=facts.credential_refs,
            )
            for step in plan.steps:
                if step.capability_id not in DESCRIPTOR_ONLY:
                    continue
                with self.subTest(state=name, capability=step.capability_id):
                    single = ExecutionPlan("DP-D15-closed", MISSION.mission_id, "synthetic")
                    single.add_step(step.capability_id, {"target": "synthetic.invalid"})
                    self.assertNotIn(step.capability_id, Capability.__members__)
                    with self.assertRaisesRegex(ValueError, "no governed Capability enum binding"):
                        plan_to_action_requests(single, registry=registry)
                    self.assertIsInstance(registry.get_adapter(step.capability_id), InertAdapter)
                    with self.assertRaises(AdapterNotBoundError):
                        registry.get_adapter(step.capability_id).execute({}, [], {})

    def test_policy_omits_descriptor_only_capabilities(self) -> None:
        policy = BOBPolicy(self.workspace)
        for capability_id in sorted(DESCRIPTOR_ONLY):
            with self.subTest(capability=capability_id):
                decision = policy.consult(
                    ActionRequest(
                        sequence=0,
                        requester="d15-test",
                        capability=capability_id,
                        target="synthetic.invalid",
                        purpose="descriptor-only",
                    ),
                    MISSION,
                )
                self.assertIs(decision.decision, Decision.DENY)
                self.assertEqual(
                    decision.reason,
                    f"capability-not-allowed:{capability_id}",
                )

    def test_http_registered_adapter_uses_runtime_broker_policy(self) -> None:
        calls: list[str] = []

        def opener(url: str, method: str, timeout: float, max_bytes: int) -> tuple[int, bytes, bool]:
            calls.append(f"{method}:{url}:{timeout}:{max_bytes}")
            return 200, b"synthetic-http", False

        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id=MISSION.mission_id,
            locator=HOST,
            allowed_ports=[80],
            allowed_protocols=["http"],
            authorization_ref="synthetic-http-authorization",
        ))
        runtime, ledger = self._runtime(
            store,
            network_mediator=NetworkMediator(opener=opener),
        )
        registry = _registry()
        bind_governed_adapters(registry, runtime, MISSION)
        observation = registry.get_adapter("NETWORK_HTTP_REQUEST").execute(
            {"host": HOST}, [], {"target": f"http://{HOST}:80/"},
        )

        self.assertEqual(observation["capability_id"], "NETWORK_HTTP_REQUEST")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [record["kind"] for record in ledger.all_records()[:3]],
            ["request", "decision", "evidence"],
        )
        self.assertEqual(
            [record["producer"] for record in ledger.all_records()
             if record.get("kind") == "evidence"][-1],
            "network",
        )

    def test_telnet_registered_adapter_uses_runtime_broker_policy(self) -> None:
        calls: list[tuple[str, int, tuple[str, ...]]] = []

        def session_fn(
            host: str,
            port: int,
            username: str,
            password: str,
            commands: list[str],
            timeout: float,
            max_bytes: int,
        ) -> dict:
            calls.append((host, port, tuple(commands)))
            return {
                "state": TelnetState.SUCCESS,
                "authenticated": True,
                "auth_decision": "accepted",
                "commands": [],
                "session_bytes": 1,
                "error": "",
            }

        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id=MISSION.mission_id,
            locator=HOST,
            allowed_ports=[23],
            allowed_protocols=["telnet"],
            authorization_ref="synthetic-telnet-authorization",
        ))
        runtime, ledger = self._runtime(
            store,
            telnet_mediator=TelnetMediator(session_fn=session_fn),
        )
        registry = _registry()
        bind_governed_adapters(registry, runtime, MISSION)
        observation = registry.get_adapter("NETWORK_TELNET_SESSION").execute(
            {"host": HOST}, [], {"target": f"telnet://{HOST}:23"},
        )

        self.assertEqual(observation["capability_id"], "NETWORK_TELNET_SESSION")
        self.assertEqual(calls, [(HOST, 23, ("pwd",))])
        self.assertTrue(any(
            record.get("producer") == "telnet"
            for record in ledger.all_records()
        ))


if __name__ == "__main__":
    unittest.main()
