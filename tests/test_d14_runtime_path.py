from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raphael_ibm_bob.capability_selector import (
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.capability_bootstrap import register_default
from raphael_ibm_bob.capability_bootstrap import InertAdapter
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.d14_ledger_view import EvidenceLedgerView
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.workspace import Workspace
from raphael_ibm_bob.harness import RaphaelSession, WorkspaceContext
from raphael_ibm_bob.harness.run import start_run


class D14RuntimePath(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "candidate.txt").write_text("candidate", encoding="utf-8")
        self.workspace = Workspace(root)
        self.ledger = EvidenceLedger(root / "run")
        self.broker = BOBBroker(
            BOBPolicy(self.workspace), self.workspace, ledger=self.ledger,
        )
        self.runtime = BOBRuntime(self.broker)
        self.mission = Mission(
            mission_id="M-D14",
            description="runtime path",
            scope=".",
            criteria=["candidate is inspected"],
        )

    def tearDown(self) -> None:
        self.ledger.close()
        self.tempdir.cleanup()

    def test_plan_action_request_reaches_broker_policy_with_linkage(self) -> None:
        plan = ExecutionPlan("DP-D14", "M-D14", "workspace")
        plan.add_step("READ", {"target": "candidate.txt"}, purpose="inspect")

        requests = plan_to_action_requests(plan)
        result = self.runtime.submit(requests[0], self.mission)

        self.assertEqual(result.broker_result.decision.decision.value, "allow")
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertIsNotNone(result.request_seq)
        self.assertIsNotNone(result.decision_seq)
        self.assertIsNotNone(result.result_seq)
        self.assertGreaterEqual(len(result.evidence_ids), 2)
        records = self.ledger.all_records()
        request = next(r for r in records if r["kind"] == "request")
        decision = next(r for r in records if r["kind"] == "decision")
        result_record = next(r for r in records if r["kind"] == "result")
        self.assertEqual(request["seq"], result.request_seq)
        self.assertEqual(decision["request_seq"], result.request_seq)
        self.assertEqual(result_record["request_seq"], result.request_seq)
        self.assertEqual(result_record["decision_seq"], result.decision_seq)

    def test_policy_deny_never_invokes_capability(self) -> None:
        plan = ExecutionPlan("DP-D14-DENY", "M-D14", "workspace")
        plan.add_step("READ", {"target": "/etc/hostname"}, purpose="escape")

        request = plan_to_action_requests(plan)[0]
        before = self.broker.capability_invocations
        result = self.runtime.submit(request, self.mission)

        self.assertEqual(result.broker_result.decision.decision.value, "deny")
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.execution)
        self.assertEqual(self.broker.capability_invocations, before)

    def test_default_bootstrap_declares_network_capabilities(self) -> None:
        registry = register_default()
        self.assertTrue(registry.has("NETWORK_HTTP_REQUEST"))
        self.assertTrue(registry.has("NETWORK_TELNET_SESSION"))

    def test_production_boot_binds_d14_registry_and_uses_runtime(self) -> None:
        session = RaphaelSession.create(
            mission=Mission(
                mission_id="M-D14-production",
                description="production D14 path",
                scope=".",
                criteria=["candidate is inspected"],
                problem={"symptom_target": "candidate.txt"},
            ),
            workspace=WorkspaceContext.from_workspace(self.workspace, "d14"),
            model="test",
        )
        captured = []
        original_bind = __import__(
            "raphael_ibm_bob.capability_bootstrap",
            fromlist=["bind_governed_adapters"],
        ).bind_governed_adapters

        def capture(registry, runtime, mission, capability_ids=None):
            original_bind(registry, runtime, mission, capability_ids)
            captured.append(registry)

        with patch(
            "raphael_ibm_bob.harness.run.capability_bootstrap.bind_governed_adapters",
            side_effect=capture,
        ):
            run = start_run(
                session,
                session.mission,
                Path(self.tempdir.name),
                runs_root=Path(self.tempdir.name) / "runs",
                candidate_target="candidate.txt",
                challenger_target="candidate.txt",
                max_replans=0,
            )

        self.assertEqual(len(captured), 1)
        registry = captured[0]
        self.assertTrue(registry.has("NETWORK_HTTP_REQUEST"))
        self.assertFalse(isinstance(registry.get_adapter("READ"), InertAdapter))
        records = list(
            __import__("raphael_ibm_bob.evidence_ledger", fromlist=["LedgerReader"])
            .LedgerReader(Path(run.ledger_dir) / "evidence.jsonl")
            .records(),
        )
        planner_requests = [
            record for record in records
            if record.get("kind") == "request"
            and record.get("requester") == "planner"
        ]
        self.assertTrue(planner_requests)

    def test_production_ledger_view_resolves_allow_success(self) -> None:
        result = self.runtime.submit(
            ActionRequest(
                sequence=0,
                requester="planner",
                capability=Capability.READ,
                target="candidate.txt",
                purpose="d14:read",
            ),
            self.mission,
        )
        evidence_id = "EV-D14"
        self.ledger.append_evidence(
            evidence_id=evidence_id,
            producer="d14-test",
            request_seq=result.request_seq,
            decision_seq=result.decision_seq,
            result_seq=result.result_seq,
            payload={
                "request_seq": result.request_seq,
                "decision_seq": result.decision_seq,
                "result_seq": result.result_seq,
                "session_id": "session-d14",
            },
        )

        binding = EvidenceLedgerView(self.ledger).resolve_evidence(evidence_id)

        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.policy_decision, "allow")
        self.assertTrue(binding.result_success)
        self.assertEqual(binding.session_id, "session-d14")


if __name__ == "__main__":
    unittest.main()
