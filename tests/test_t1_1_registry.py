"""tests.test_t1_1_registry — T1-1 capability/skill registry tests.

Unit coverage for the declaration model plus one mock-free
end-to-end: skill proposal -> ActionRequest -> Runtime/Broker/Policy
-> Finding -> Verifier -> Falsifier -> Replanner. No execution path
is mocked; the registry itself never authorizes anything.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    FocusedContext,
    Mission,
    Plan,
    Workspace,
)
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import EvidenceReceipt
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate
from raphael_ibm_bob.replanner import Replanner
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import (
    CapabilityDefinition,
    CapabilityRegistry,
    SkillDefinition,
    default_registry,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier


def _registry() -> CapabilityRegistry:
    return default_registry()


def _skill(**overrides) -> SkillDefinition:
    base = dict(
        id="read-candidate",
        name="Read candidate",
        version="1.0",
        description="Read a candidate file through the boundary.",
        capability=Capability.READ,
        target_schema="relative file path",
        purpose_template="skill:probe:{target}",
        success_markers=("OK",),
    )
    base.update(overrides)
    return SkillDefinition(**base)


class Registration(unittest.TestCase):
    def test_register_and_lookup_skill(self):
        reg = _registry()
        reg.register_skill(_skill())
        found = reg.lookup_skill("read-candidate")
        self.assertEqual(found.name, "Read candidate")
        self.assertEqual(found.version, "1.0")

    def test_register_capability(self):
        reg = CapabilityRegistry()
        reg.register_capability(CapabilityDefinition(
            capability=Capability.READ,
            description="r",
            target_schema="t",
            purpose_template="p:{target}",
            version="2.1"))
        self.assertEqual(
            reg.lookup_capability(Capability.READ).version, "2.1")

    def test_duplicate_skill_rejected(self):
        reg = _registry()
        reg.register_skill(_skill())
        with self.assertRaises(ValueError):
            reg.register_skill(_skill())

    def test_duplicate_capability_rejected(self):
        reg = _registry()
        with self.assertRaises(ValueError):
            reg.register_capability(CapabilityDefinition(
                capability=Capability.READ,
                description="dup",
                target_schema="t",
                purpose_template="p:{target}",
                version="1.0"))

    def test_lookup_missing_skill(self):
        with self.assertRaises(KeyError):
            _registry().lookup_skill("no-such-skill")

    def test_listing(self):
        reg = _registry()
        reg.register_skill(_skill(id="s-a", name="A"))
        reg.register_skill(_skill(id="s-b", name="B"))
        self.assertEqual([s.id for s in reg.list_skills()],
                         ["s-a", "s-b"])
        self.assertEqual(len(reg.list_capabilities()), 6)


class DeclarationValidation(unittest.TestCase):
    def test_malformed_template_rejected(self):
        with self.assertRaises(ValueError):
            _skill(purpose_template="no-placeholder-here")

    def test_invalid_capability_rejected(self):
        with self.assertRaises(ValueError):
            _skill(capability="READ")

    def test_bad_version_rejected(self):
        for bad in ("", "1", "v1.0", "1.0.0.0", "a.b"):
            with self.assertRaises(ValueError, msg=bad):
                _skill(version=bad)

    def test_capability_bad_version_rejected(self):
        with self.assertRaises(ValueError):
            CapabilityDefinition(
                capability=Capability.READ, description="r",
                target_schema="t", purpose_template="p:{target}",
                version="bogus")

    def test_skill_needs_declared_capability(self):
        reg = CapabilityRegistry()
        with self.assertRaises(ValueError):
            reg.register_skill(_skill())

    def test_empty_markers_rejected(self):
        with self.assertRaises(ValueError):
            _skill(success_markers=("",))


class ProposalBuildsActionRequest(unittest.TestCase):
    def test_proposal_is_plain_action_request(self):
        reg = _registry()
        reg.register_skill(_skill())
        proposal = reg.propose("read-candidate", "src/cand.txt")
        req = proposal.request
        self.assertIsInstance(req, ActionRequest)
        self.assertEqual(req.capability, Capability.READ)
        self.assertEqual(req.target, "src/cand.txt")
        self.assertEqual(req.purpose, "skill:probe:src/cand.txt")
        self.assertEqual(req.requester, "skill:read-candidate")
        self.assertEqual(proposal.skill_id, "read-candidate")
        self.assertEqual(proposal.skill_version, "1.0")

    def test_proposal_overrides(self):
        reg = _registry()
        reg.register_skill(_skill())
        proposal = reg.propose(
            "read-candidate", "src/cand.txt",
            requester="harness", plan_id="P-1", finding_id="F-1")
        self.assertEqual(proposal.request.requester, "harness")
        self.assertEqual(proposal.request.plan_id, "P-1")
        self.assertEqual(proposal.request.finding_id, "F-1")

    def test_proposal_empty_target_rejected(self):
        reg = _registry()
        reg.register_skill(_skill())
        with self.assertRaises(ValueError):
            reg.propose("read-candidate", "")

    def test_proposal_evidence_payload(self):
        reg = _registry()
        reg.register_skill(_skill())
        payload = reg.propose(
            "read-candidate", "src/cand.txt").to_evidence_payload()
        self.assertEqual(payload["kind"], "skill-proposal")
        self.assertEqual(payload["skill_id"], "read-candidate")
        self.assertEqual(payload["target"], "src/cand.txt")

    def test_registry_grants_no_authority(self):
        # A proposal for an out-of-scope target is still DENIED by
        # Policy: the registry cannot authorize anything.
        from raphael_ibm_bob.evidence_ledger import (
            EvidenceLedger as Ledger)
        ws_root = Path(tempfile.mkdtemp(prefix="t1_ws_"))
        self.addCleanup(shutil.rmtree, ws_root, True)
        run_root = Path(tempfile.mkdtemp(prefix="t1_run_"))
        self.addCleanup(shutil.rmtree, run_root, True)
        workspace = Workspace(ws_root)
        ledger = Ledger(run_root)
        broker = BOBBroker(BOBPolicy(workspace), workspace,
                           ledger=ledger)
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M", description="x", scope="src/",
                          criteria=["x"])
        reg = _registry()
        reg.register_skill(_skill())
        proposal = reg.propose("read-candidate", "/etc/hostname")
        result = runtime.submit(proposal.request, mission)
        self.assertEqual(
            result.broker_result.decision.decision.value, "deny")
        self.assertIsNone(result.execution)


class SkillDrivenRecovery(unittest.TestCase):
    """Mock-free end-to-end: a skill proposal drives real recovery."""

    def test_proposal_to_replan(self):
        ws_root = Path(tempfile.mkdtemp(prefix="t1_e2e_ws_"))
        self.addCleanup(shutil.rmtree, ws_root, True)
        src = ws_root / "src"
        src.mkdir()
        (src / "cand.txt").write_text("OK\nDEFECT: beta\n")
        (src / "fixed.txt").write_text("OK\n")
        run_root = Path(tempfile.mkdtemp(prefix="t1_e2e_run_"))
        self.addCleanup(shutil.rmtree, run_root, True)

        workspace = Workspace(ws_root)
        ledger = EvidenceLedger(run_root)
        broker = BOBBroker(BOBPolicy(workspace), workspace,
                           ledger=ledger)
        runtime = BOBRuntime(broker)
        store = FindingStore(ledger)
        verifier = Verifier(runtime, ledger, store)
        falsifier = Falsifier(runtime, ledger, store)
        replanner = Replanner(store, ledger)
        mission = Mission(mission_id="M-e2e", description="x",
                          scope="src/", criteria=["x"],
                          problem={"symptom_target": "src/cand.txt"})

        reg = _registry()
        reg.register_skill(_skill(
            challenge=ChallengeSpec(
                capability=Capability.READ,
                target="src/cand.txt",
                purpose="skill:challenge",
                forbidden_substring="DEFECT")))

        # Skill proposal -> ordinary broker-mediated execution.
        proposal = reg.propose("read-candidate", "src/cand.txt")
        rt = runtime.submit(proposal.request, mission)
        self.assertEqual(
            rt.broker_result.decision.decision.value, "allow")

        finding = Finding(finding_id="F-skill", state=FindingState.UNVERIFIED,
                          summary="candidate", target="src/cand.txt")
        store.register(finding)
        skill = reg.lookup_skill("read-candidate")
        verify_out = verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/cand.txt",
                       expected_substring=skill.success_markers[0]),
            mission, requester="skill")
        self.assertTrue(verify_out.transition_applied)

        challenge_out = falsifier.challenge(
            store.get("F-skill"), skill.challenge, mission,
            requester="skill")
        self.assertTrue(challenge_out.counter_example_observed)
        self.assertEqual(challenge_out.finding.state,
                         FindingState.REFUTED)

        # Replan from the refuted finding via real Replanner.
        parent = Plan(plan_id="P-parent", mission_id=mission.mission_id,
                      steps=[proposal.request])
        records = ledger.records_for_finding("F-skill")
        receipts = [EvidenceReceipt(
            evidence_id=r.get("evidence_id", ""),
            sequence=r.get("seq", 0),
            producer=r.get("producer", ""),
            payload=dict(r)) for r in records
            if r.get("kind") == "evidence"]
        ctx = FocusedContext(
            refuted_claim=store.get("F-skill"),
            diagnostic_evidence=receipts,
            mission_scope=mission.scope)
        plan_b = replanner.replan(ctx, parent)
        self.assertEqual(plan_b.parent_plan_id, "P-parent")
        self.assertEqual(plan_b.steps[0].requester, "replanner")
        # Counter-evidence named cand.txt, so Plan B targets it.
        self.assertEqual(plan_b.steps[0].target, "src/cand.txt")


if __name__ == "__main__":
    unittest.main()
