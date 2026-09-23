"""tests.test_m14_specialization — M14 specialization tests.

Roles, richer skill/capability declarations, role-aware discovery,
task decomposition, and evidence contracts. Every test uses the real
RAPHAEL core; the point is that specialization is DECLARATION, never
authority.
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
    Mission,
    Workspace,
)
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, latest_allowed_success
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import (
    CapabilityRegistry,
    SkillDefinition,
    default_registry,
    register_default_skills,
)
from raphael_ibm_bob.specialization import (
    DEFAULT_ROLES,
    InvalidTaskTransitionError,
    Role,
    RoleRegistry,
    TaskState,
    decompose_mission,
    default_roles,
    evidence_contract,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier


def _tree(testcase):
    base = Path(tempfile.mkdtemp(prefix="m14_"))
    testcase.addCleanup(shutil.rmtree, base, True)
    ws = base / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
    (ws / "src" / "test_ok.py").write_text(
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertTrue(True)\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n", encoding="utf-8")
    return base, ws


def _mission() -> Mission:
    return Mission(mission_id="M-authkit", description="x", scope="src/",
                   criteria=["fix"],
                   problem={"symptom_target": "src/cand.txt"})


def _stack(ws):
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(ws)
    ledger = EvidenceLedger(ws / "run")
    broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    store = FindingStore(ledger)
    verifier = Verifier(runtime, ledger, store)
    falsifier = Falsifier(runtime, ledger, store)
    gate = BOBQualityGate(ledger)
    return workspace, ledger, broker, runtime, store, verifier, falsifier, gate


class RolesAreDeclarations(unittest.TestCase):
    def test_A_role_metadata_does_not_grant_authority(self):
        base, ws = _tree(self)
        reg = register_default_skills(default_registry())
        # investigator declares READ; Policy still denies an out-of-scope
        # READ target regardless of the role claim.
        skills = reg.list_skills_for_role("investigator")
        self.assertTrue(skills)
        _, ledger, broker, runtime, *_ = _stack(ws)
        request = reg.propose("read-file", "/etc/hostname").request
        result = runtime.submit(request, _mission())
        self.assertEqual(
            result.broker_result.decision.decision.value, "deny")
        self.assertFalse(result.broker_result.capability_invoked)
        # Role purpose is descriptive text, not a permission token.
        role = reg.get_role("investigator")
        self.assertIn("Locate", role.purpose)

    def test_B_unknown_role_fails_cleanly(self):
        reg = register_default_skills(default_registry())
        with self.assertRaises(KeyError):
            reg.get_role("no-such-role")
        with self.assertRaises(KeyError):
            reg.list_skills_for_role("no-such-role")
        with self.assertRaises(ValueError):
            reg.register_skill(SkillDefinition(
                id="x", name="x", version="1.0", description="d",
                capability=Capability.READ, target_schema="t",
                purpose_template="p:{target}", role="no-such-role"))

    def test_C_unknown_skill_fails(self):
        reg = register_default_skills(default_registry())
        with self.assertRaises(KeyError):
            reg.propose("no-such-skill", "src/cand.txt")

    def test_D_role_skill_mismatch_fails(self):
        reg = register_default_skills(default_registry())
        with self.assertRaises(ValueError):
            reg.register_skill(SkillDefinition(
                id="bad-mix", name="bad", version="1.0", description="d",
                capability=Capability.WRITE, target_schema="t",
                purpose_template="p:{target}",
                role="investigator"))  # investigator has no WRITE

    def test_role_vocabulary_is_small_and_stable(self):
        ids = [r.id for r in default_roles().list_roles()]
        self.assertEqual(ids, [
            "evidence_analyst", "falsifier", "investigator",
            "remediation_planner", "test_analyst", "verifier"])
        self.assertEqual(len(ids), 6)


class Discovery(unittest.TestCase):
    def test_skills_for_role(self):
        reg = register_default_skills(default_registry())
        inv = sorted(s.id for s in reg.list_skills_for_role("investigator"))
        self.assertEqual(inv, ["list-dir", "read-file", "search-dir"])
        self.assertEqual(
            [s.id for s in reg.list_skills_for_role("test_analyst")],
            ["run-test"])

    def test_capabilities_for_role(self):
        reg = register_default_skills(default_registry())
        caps = reg.list_capabilities_for_role("remediation_planner")
        self.assertEqual(caps, [Capability.WRITE])

    def test_discover_skills_filters(self):
        reg = register_default_skills(default_registry())
        found = reg.discover_skills(role="investigator",
                                    capability=Capability.READ)
        self.assertEqual([s.id for s in found], ["read-file"])
        # Evidence filtering: a skill whose consumed evidence is not
        # available is excluded; skills with no requirement are kept.
        reg.register_skill(SkillDefinition(
            id="needs-remediation", name="needs", version="1.0",
            description="d", capability=Capability.READ,
            target_schema="t", purpose_template="p:{target}",
            role="investigator",
            evidence_consumed=("remediation",)))
        found2 = [s.id for s in reg.discover_skills(
            role="investigator", evidence_available=("inspection",))]
        self.assertNotIn("needs-remediation", found2)
        found3 = [s.id for s in reg.discover_skills(
            role="investigator",
            evidence_available=("inspection", "remediation"))]
        self.assertIn("needs-remediation", found3)
        self.assertIn("read-file",
                      [s.id for s in reg.discover_skills()])

    def test_discover_prereq_missing_rejected(self):
        reg = register_default_skills(default_registry())
        with self.assertRaises(ValueError):
            reg.register_skill(SkillDefinition(
                id="needs-read", name="needs", version="1.0",
                description="d", capability=Capability.READ,
                target_schema="t", purpose_template="p:{target}",
                role="investigator", prerequisites=("ghost-skill",)))


class ProposalStillGoverned(unittest.TestCase):
    def test_E_invalid_target_fails(self):
        reg = register_default_skills(default_registry())
        with self.assertRaises(ValueError):
            reg.propose("read-file", "")

    def test_G_role_selected_skill_still_builds_action_request(self):
        reg = register_default_skills(default_registry())
        skill = reg.discover_skills(role="investigator")[0]
        proposal = reg.propose(skill.id, "src/cand.txt")
        self.assertIsInstance(proposal.request, ActionRequest)
        self.assertEqual(proposal.request.capability, skill.capability)

    def test_H_I_role_selected_skill_goes_through_broker(self):
        base, ws = _tree(self)
        _, ledger, broker, runtime, *_ = _stack(ws)
        reg = register_default_skills(default_registry())
        skill = reg.discover_skills(role="investigator",
                                    capability=Capability.READ)[0]
        # H: an in-scope request is brokered (submission count rises).
        before = broker.submissions
        ok = runtime.submit(reg.propose(skill.id, "src/cand.txt").request,
                            _mission())
        self.assertEqual(broker.submissions, before + 1)
        self.assertEqual(ok.broker_result.decision.decision.value, "allow")
        # I: an out-of-scope request is denied and does not execute.
        denied = runtime.submit(
            reg.propose(skill.id, "/etc/hostname").request, _mission())
        self.assertEqual(
            denied.broker_result.decision.decision.value, "deny")
        self.assertEqual(
            [r for r in ledger.all_records() if r.get("kind") == "result"
             and r.get("request_seq") == denied.request_seq], [])

    def test_F_J_invalid_proposal_and_fabricated_context(self):
        from raphael_ibm_bob.harness.providers.openai_compat import (
            StructuredProposalError,
            validate_proposal,
        )
        base, ws = _tree(self)
        _, _, broker, *_ = _stack(ws)
        reg = register_default_skills(default_registry())
        # F: an invalid proposal never reaches the Broker.
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "made-up",
                 "target": "src/cand.txt", "purpose": "p"}, reg)
        self.assertEqual(broker.submissions, 0)
        # J: a context claiming a skill exists does not register it.
        ctx = ModelContext(
            mission=_mission(),
            available_roles=({"role": "investigator",
                              "capabilities": ["read"]},),
            active_task={"steps": [{"name": "investigate",
                                    "skills": ["made-up"]}]})
        self.assertIn("made-up", str(ctx.summary()))
        self.assertFalse(reg.has_skill("made-up"))


class EvidenceContracts(unittest.TestCase):
    def test_L_evidence_contracts_do_not_write_evidence(self):
        base, ws = _tree(self)
        _, ledger, *_ = _stack(ws)
        reg = register_default_skills(default_registry())
        before = len(ledger.all_records())
        for skill in reg.list_skills():
            contract = evidence_contract(skill)
            self.assertIn("evidence_produced", contract)
        self.assertEqual(len(ledger.all_records()), before)

    def test_capability_evidence_fields(self):
        reg = default_registry()
        read = reg.lookup_capability(Capability.READ)
        run_test = reg.lookup_capability(Capability.RUN_TEST)
        write = reg.lookup_capability(Capability.WRITE)
        self.assertIn("inspection", read.evidence_produced)
        self.assertIn("test-execution", run_test.evidence_produced)
        self.assertIn("remediation", write.evidence_produced)
        self.assertIn("inspection", write.evidence_consumed)


class TaskDecomposition(unittest.TestCase):
    def test_deterministic_tree(self):
        plan_a = decompose_mission(_mission())
        plan_b = decompose_mission(_mission())
        self.assertEqual(plan_a.to_dict(), plan_b.to_dict())
        steps = [t.name for t in plan_a.root.subtasks]
        self.assertEqual(steps, ["investigate", "reproduce", "remediate",
                                 "verify", "validate"])
        self.assertEqual(plan_a.state_of(
            "M-authkit::investigate"), TaskState.PENDING)

    def test_task_state_machine(self):
        plan = decompose_mission(_mission())
        tid = "M-authkit::investigate"
        plan.mark(tid, TaskState.ACTIVE)
        plan.mark(tid, TaskState.COMPLETED)
        with self.assertRaises(InvalidTaskTransitionError):
            plan.mark(tid, TaskState.ACTIVE)  # completed is terminal
        with self.assertRaises(KeyError):
            plan.mark("nope", TaskState.ACTIVE)

    def test_K_task_completed_cannot_manufacture_complete(self):
        base, ws = _tree(self)
        _, ledger, _, _, store, _, _, gate = _stack(ws)
        plan = decompose_mission(_mission())
        for task in plan.tasks():
            if plan.states[task.task_id] is TaskState.PENDING:
                plan.mark(task.task_id, TaskState.ACTIVE)
            if plan.states[task.task_id] is TaskState.ACTIVE:
                plan.mark(task.task_id, TaskState.COMPLETED)
        # All tasks COMPLETED, but there is no evidence: gate REFUSES.
        evaluation = gate.evaluate(GateInputs(
            mission=_mission(), findings=list(store.all()),
            regression_ok=False, behavior_probe_ok=False))
        self.assertEqual(evaluation.verdict.value, "refuse")

    def test_M_task_state_cannot_override_finding_lifecycle(self):
        base, ws = _tree(self)
        _, ledger, _, _, store, verifier, falsifier, _ = _stack(ws)
        finding = store.register(Finding(
            finding_id="F-1", state=FindingState.UNVERIFIED,
            summary="s", target="src/cand.txt"))
        plan = decompose_mission(_mission())
        for task in plan.tasks():
            if plan.states[task.task_id] is TaskState.PENDING:
                plan.mark(task.task_id, TaskState.ACTIVE)
            if plan.states[task.task_id] is TaskState.ACTIVE:
                plan.mark(task.task_id, TaskState.COMPLETED)
        # FindingStore remains authoritative; task states change nothing.
        self.assertEqual(store.get("F-1").state, FindingState.UNVERIFIED)


class ExistingAuthoritiesRemain(unittest.TestCase):
    def test_N_falsifier_remains_authoritative(self):
        base, ws = _tree(self)
        (ws / "src" / "buggy.txt").write_text("DEFECT\n", encoding="utf-8")
        _, ledger, _, runtime, store, verifier, falsifier, _ = _stack(ws)
        finding = store.register(Finding(
            finding_id="F-2", state=FindingState.UNVERIFIED,
            summary="s", target="src/cand.txt"))
        verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/cand.txt", expected_substring="OK"),
            _mission(), requester="m14")
        out = falsifier.challenge(
            store.get("F-2"),
            ChallengeSpec(capability=Capability.READ,
                          target="src/buggy.txt",
                          purpose="challenge",
                          forbidden_substring="DEFECT"),
            _mission(), requester="m14")
        self.assertTrue(out.counter_example_observed)
        self.assertEqual(out.finding.state, FindingState.REFUTED)
        # Task plan is irrelevant to the Falsifier's decision.
        self.assertTrue(decompose_mission(_mission()).states)

    def test_O_quality_gate_sole_complete_authority(self):
        base, ws = _tree(self)
        _, ledger, broker, runtime, store, verifier, falsifier, gate = \
            _stack(ws)
        # Seed a clean, verified finding + a passing RUN_TEST + probe.
        finding = store.register(Finding(
            finding_id="F-3", state=FindingState.UNVERIFIED,
            summary="s", target="src/cand.txt"))
        verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/cand.txt", expected_substring="OK"),
            _mission(), requester="m14")
        runtime.submit(ActionRequest(
            sequence=0, requester="m14", capability=Capability.RUN_TEST,
            target="src/test_ok.py", purpose="required-test"), _mission())
        from raphael_ibm_bob.evidence_ledger import digest_id
        req_seq, dec_seq, res_seq = latest_allowed_success(ledger)
        for producer, payload in (
                ("probe", {"kind": "probe", "result": "passed",
                           "allowed": True, "request_seq": req_seq,
                           "result_seq": res_seq}),
                ("regression", {"kind": "regression", "result": "passed",
                                "request_seq": req_seq,
                                "result_seq": res_seq})):
            ledger.append_evidence(
                evidence_id=digest_id(payload, prefix=producer[:2].upper()),
                producer=producer, request_seq=req_seq, decision_seq=dec_seq,
                result_seq=res_seq, payload=payload)
        ok = gate.evaluate(GateInputs(
            mission=_mission(), findings=list(store.all()),
            regression_ok=True, behavior_probe_ok=True))
        self.assertEqual(ok.verdict.value, "complete")
        # Roles/tasks cannot produce COMPLETE by themselves.
        import raphael_ibm_bob.quality_gate as qg
        src = Path(qg.__file__).read_text(encoding="utf-8")
        self.assertEqual(src.count("GateVerdict.COMPLETE"), 2)  # doc + code


if __name__ == "__main__":
    unittest.main()
