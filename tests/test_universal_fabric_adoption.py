"""tests.test_universal_fabric_adoption — M16.3 tests.

Proves the deterministic Planner and the Replanner resolve capabilities
through the SAME Capability Fabric (no direct ActionRequest construction,
no native-execution bypass), with real Runtime/Broker/Policy downstream.

Recording-Fabric technique: a Fabric subclass records resolve() calls.
Planner uses the patchable `planner.default_fabric` module seam (the M8
rule forbids Planner constructor args); Replanner accepts an injected
`fabric`.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_fabric import (
    CapabilityFabric,
    CapabilityNotProvidedError,
    NativeCapabilityProvider,
    default_fabric,
)
from raphael_ibm_bob.contracts import (
    ActionRequest, Capability, EvidenceReceipt, Finding, FindingState,
    FocusedContext, Mission, Plan,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.planner import Planner, derive_plan_a_id
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.replanner import Replanner, derive_plan_b_id
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import default_registry, register_default_skills
from raphael_ibm_bob.workspace import Workspace


class _RecordingFabric(CapabilityFabric):
    def __init__(self):
        super().__init__()
        self.resolve_calls = []
        self.register(NativeCapabilityProvider(
            registry=register_default_skills(default_registry())))

    def resolve(self, capability, provider_id=None):
        self.resolve_calls.append(capability)
        return super().resolve(capability, provider_id)


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m163_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")

    def mission(self, **problem_over):
        problem = {"symptom_target": "src/cand.txt"}
        problem.update(problem_over)
        return Mission(mission_id="M-univ", description="univ", scope="src/",
                       criteria=["c"], problem=problem)

    def _stack(self):
        run_dir = self.base / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(self.ws)
        ledger = EvidenceLedger(run_dir)
        broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
        return BOBRuntime(broker), ledger

    def _refuted_replan(self, fabric):
        """Build a real REFUTED-driven Plan B through the Replanner."""
        run_dir = self.base / "replan"
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = EvidenceLedger(run_dir)
        store = FindingStore(ledger)
        refuted = Finding(finding_id="F-1", state=FindingState.REFUTED,
                          summary="bad fix", target="src/other.py")
        context = FocusedContext(
            refuted_claim=refuted,
            diagnostic_evidence=[EvidenceReceipt(
                evidence_id="O-1", sequence=5, producer="probe",
                payload={"payload": {"kind": "counter-example",
                                     "new_target": "src/cand.txt"}})],
            mission_scope="src/")
        parent = Plan(plan_id="P-A", mission_id="M-univ",
                      steps=[ActionRequest(sequence=0, requester="planner",
                                           capability=Capability.READ,
                                           target="src/other.py",
                                           purpose="parent")],
                      parent_plan_id=None)
        replanner = Replanner(store, ledger, fabric=fabric)
        return replanner.replan(context, parent), ledger


class PlannerAdoption(_Case):
    def test_A_planner_resolves_capability_through_fabric(self):
        rec = _RecordingFabric()
        with mock.patch("raphael_ibm_bob.planner.default_fabric",
                        return_value=rec):
            plan = Planner().plan_a(self.mission())
        self.assertEqual(rec.resolve_calls, [Capability.READ])
        self.assertIsInstance(plan.steps[0], ActionRequest)

    def test_B_planner_capability_resolves_to_native_provider(self):
        self.assertEqual(
            default_fabric().resolve(Capability.READ).provider_id,
            "raphael-native")
        plan = Planner().plan_a(self.mission())
        self.assertEqual(plan.steps[0].capability, Capability.READ)

    def test_C_planner_builds_request_via_provider(self):
        plan = Planner().plan_a(self.mission())
        step = plan.steps[0]
        self.assertEqual(step.requester, "planner")
        self.assertEqual(step.target, "src/cand.txt")
        self.assertEqual(step.plan_id, derive_plan_a_id(self.mission()))
        self.assertIsNone(step.finding_id)

    def test_J_unknown_capability_fails_explicitly(self):
        with self.assertRaises(ValueError):
            Planner().plan_a(self.mission(capability="not-a-capability"))

    def test_L_provider_failure_is_explicit(self):
        with mock.patch("raphael_ibm_bob.planner.default_fabric",
                        return_value=CapabilityFabric()):
            with self.assertRaises(CapabilityNotProvidedError):
                Planner().plan_a(self.mission())

    def test_M_to_R_fields_preserved(self):
        plan = Planner().plan_a(self.mission(purpose="plan-a:probe:custom"))
        step = plan.steps[0]
        self.assertEqual(step.target, "src/cand.txt")      # M
        self.assertEqual(step.purpose, "plan-a:probe:custom")  # N
        self.assertEqual(step.requester, "planner")        # O
        self.assertEqual(step.plan_id, derive_plan_a_id(self.mission()))  # P
        self.assertIsNone(step.finding_id)                  # Q
        self.assertIsNone(step.timeout_seconds)             # R (READ: none)

    def test_S_write_purpose_preserved(self):
        plan = Planner().plan_a(self.mission(
            capability="write", purpose="content=OK\n"))
        self.assertEqual(plan.steps[0].capability, Capability.WRITE)
        self.assertEqual(plan.steps[0].purpose, "content=OK\n")


class ReplannerAdoption(_Case):
    def test_D_Replanner_resolves_capability_through_fabric(self):
        rec = _RecordingFabric()
        plan_b, ledger = self._refuted_replan(rec)
        self.assertEqual(rec.resolve_calls, [Capability.READ])
        self.assertIsInstance(plan_b.steps[0], ActionRequest)
        ledger.close()

    def test_E_replanner_builds_request_via_provider(self):
        plan_b, ledger = self._refuted_replan(default_fabric())
        step = plan_b.steps[0]
        self.assertEqual(step.requester, "replanner")
        self.assertEqual(step.finding_id, "F-1")
        self.assertEqual(step.target, "src/cand.txt")
        self.assertEqual(step.plan_id, plan_b.plan_id)  # step <-> Plan B
        self.assertTrue(step.plan_id.startswith("P-"))
        ledger.close()

    def test_K_unknown_capability_in_replanner_fails(self):
        class _Unknown:
            pass
        # Replanner validates via Fabric.resolve; an empty fabric fails.
        from raphael_ibm_bob.replanner import ReplanStrategy
        run_dir = self.base / "r2"
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = EvidenceLedger(run_dir)
        replanner = Replanner(FindingStore(ledger), ledger,
                              ReplanStrategy(capability=Capability.READ),
                              fabric=CapabilityFabric())
        refuted = Finding(finding_id="F-2", state=FindingState.REFUTED,
                          summary="s", target="t")
        context = FocusedContext(
            refuted_claim=refuted,
            diagnostic_evidence=[EvidenceReceipt(
                evidence_id="O-2", sequence=1, producer="probe",
                payload={"payload": {"kind": "counter-example",
                                     "new_target": "src/cand.txt"}})],
            mission_scope="src/")
        parent = Plan(plan_id="P-A", mission_id="M", steps=[
            ActionRequest(sequence=0, requester="planner",
                          capability=Capability.READ, target="src/x",
                          purpose="p")], parent_plan_id=None)
        with self.assertRaises(CapabilityNotProvidedError):
            replanner.replan(context, parent)
        ledger.close()


class Governance(_Case):
    def test_F_G_H_I_no_bypass_in_production_paths(self):
        root = Path(__file__).resolve().parents[1] / "raphael_ibm_bob"
        planner_src = (root / "planner.py").read_text("utf-8")
        replanner_src = (root / "replanner.py").read_text("utf-8")
        for name, src in (("planner.py", planner_src),
                          ("replanner.py", replanner_src)):
            self.assertNotIn("ActionRequest(", src, name)   # no direct build
            self.assertIn("fabric", src, name)
            self.assertIn(".resolve(", src, name)
            for token in ("execute_capability(", "BOBBroker", "BOBPolicy",
                          "BOBRuntime", "BOBQualityGate",
                          "import subprocess", "import socket",
                          "import urllib", "from raphael_ibm_bob.broker",
                          "from raphael_ibm_bob.policy",
                          "from raphael_ibm_bob.runtime",
                          "from raphael_ibm_bob.capabilities"):
                self.assertNotIn(token, src, f"{token} in {name}")

    def test_T_fabric_free_of_authority(self):
        src = (Path(__file__).resolve().parents[1] / "raphael_ibm_bob" /
               "capability_fabric.py").read_text("utf-8")
        for token in ("BOBBroker", "BOBPolicy", "BOBRuntime",
                      "BOBQualityGate", "execute_capability(",
                      "import subprocess", "import socket", "import urllib"):
            self.assertNotIn(token, src, token)


class Integration(_Case):
    def test_U_deterministic_plan_a_executes_through_fabric(self):
        plan = Planner().plan_a(self.mission())
        runtime, ledger = self._stack()
        result = runtime.submit(plan.steps[0], self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "allow")
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        ledger.close()

    def test_V_deny_still_denies(self):
        plan = Planner().plan_a(self.mission(symptom_target="/etc/hostname"))
        runtime, ledger = self._stack()
        result = runtime.submit(plan.steps[0], self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "deny")
        self.assertIsNone(result.execution)
        ledger.close()

    def test_W_replan_plan_b_executes_through_fabric(self):
        plan_b, ledger = self._refuted_replan(default_fabric())
        runtime, _ = self._stack()
        result = runtime.submit(plan_b.steps[0], self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "allow")
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        ledger.close()


if __name__ == "__main__":
    unittest.main()
