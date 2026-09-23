from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import InertAdapter, bind_governed_adapters
from raphael_ibm_bob.capability_registry import CapabilityRegistry
from raphael_ibm_bob.capability_selector import CapabilitySelector
from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.network_runtime import NetworkMediator
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.workspace import Workspace
from tests.test_d15_applicability import _NETWORK_DESCRIPTORS, _facts


class D15GovernedBridgeTests(unittest.TestCase):
    def test_available_http_selection_executes_through_governed_path(self) -> None:
        descriptor = next(
            item for item in _NETWORK_DESCRIPTORS
            if item.capability_id == "NETWORK_HTTP_REQUEST"
        )
        registry = CapabilityRegistry()
        registry.register(descriptor, InertAdapter())
        facts = _facts(descriptor.protocol)
        plan = CapabilitySelector(registry).select_and_compose(
            "service_interaction",
            {"mission_id": "M-D15"},
            facts,
        )
        self.assertEqual(
            [step.capability_id for step in plan.steps],
            [descriptor.capability_id],
        )

        calls: list[str] = []

        def opener(url: str, method: str, timeout: float,
                   max_bytes: int) -> tuple[int, bytes, bool]:
            calls.append(f"{method}:{url}:{timeout}:{max_bytes}")
            return 200, b"synthetic-http", False

        with tempfile.TemporaryDirectory(prefix="d15_applicability_") as tmp:
            workspace = Workspace(Path(tmp))
            store = TargetStore()
            store.set_target(build_target_profile(
                mission_id="M-D15",
                locator=facts.host,
                allowed_ports=[80],
                allowed_protocols=["http"],
                authorization_ref="synthetic-http-authorization",
            ))
            ledger = EvidenceLedger(Path(tmp) / "run")
            try:
                broker = BOBBroker(
                    BOBPolicy(workspace, target_store=store),
                    workspace,
                    ledger=ledger,
                    network_mediator=NetworkMediator(opener=opener),
                    target_store=store,
                )
                runtime = BOBRuntime(broker)
                mission = Mission(
                    mission_id="M-D15",
                    description="synthetic D15 governed bridge",
                    scope="",
                    criteria=["selection is governed"],
                )
                bind_governed_adapters(registry, runtime, mission)
                observation = registry.get_adapter(
                    descriptor.capability_id,
                ).execute(
                    {"host": facts.host},
                    [],
                    {"target": f"http://{facts.host}:80/"},
                )
                records = ledger.all_records()
            finally:
                ledger.close()

        self.assertEqual(observation["capability_id"], descriptor.capability_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [record["kind"] for record in records[:3]],
            ["request", "decision", "evidence"],
        )


if __name__ == "__main__":
    unittest.main()
