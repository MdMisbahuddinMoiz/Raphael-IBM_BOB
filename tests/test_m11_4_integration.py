"""tests.test_m11_4_integration — model/provider integration tests.

The provider boundary is a programmable in-process stub HTTP server
(real HTTP through the real adapter). EVERYTHING behind it is the
real RAPHAEL core: Runtime, Broker, Policy, EvidenceLedger,
FindingStore, Verifier, Falsifier, Replanner, QualityGate. Nothing
on the governed path is mocked.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from raphael_ibm_bob import (
    Capability,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    Workspace,
)
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import ActionRequest, EvidenceReceipt
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger, digest_id, latest_allowed_success,
)
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.loop import drive_turns
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.harness.providers.openai_compat import (
    OpenAICompatAdapter,
    OpenAICompatConfig,
    StructuredProposalError,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.replanner import Replanner
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.skills import (
    SkillDefinition,
    default_registry,
)
from raphael_ibm_bob.verifier import RetestSpec, Verifier


class StubProvider:
    """Programmable chat-completions stub (queue of JSON payloads)."""

    def __init__(self, testcase: unittest.TestCase):
        self.queue = []
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.hits += 1
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                payload = outer.queue[min(outer.hits - 1,
                                          len(outer.queue) - 1)]
                body = {"choices": [{"message": {
                    "content": json.dumps(payload)}}]}
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        testcase.addCleanup(self._server.server_close)
        thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        thread.start()
        testcase.addCleanup(self._server.shutdown)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"


def _act(skill="read-file", target="src/cand.txt", purpose="inspect"):
    return {"intent": "act", "skill": skill, "target": target,
            "purpose": purpose}


class _Stack:
    def __init__(self, testcase: unittest.TestCase):
        ws_root = Path(tempfile.mkdtemp(prefix="m114_ws_"))
        testcase.addCleanup(shutil.rmtree, ws_root, True)
        src = ws_root / "src"
        src.mkdir()
        (src / "cand.txt").write_text("OK\nDEFECT: beta\n")
        (src / "clean.txt").write_text("OK\n")
        (src / "test_ok.py").write_text(
            "import unittest\n"
            "class OkTest(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n")
        run_root = Path(tempfile.mkdtemp(prefix="m114_run_"))
        testcase.addCleanup(shutil.rmtree, run_root, True)
        self.workspace = Workspace(ws_root)
        self.ledger = EvidenceLedger(run_root)
        self.policy = BOBPolicy(self.workspace)
        self.broker = BOBBroker(self.policy, self.workspace,
                                ledger=self.ledger)
        self.runtime = BOBRuntime(self.broker)
        self.store = FindingStore(self.ledger)
        self.verifier = Verifier(self.runtime, self.ledger, self.store)
        self.falsifier = Falsifier(self.runtime, self.ledger, self.store)
        self.replanner = Replanner(self.store, self.ledger)
        self.gate = BOBQualityGate(self.ledger)
        self.mission = Mission(
            mission_id="M-i9", description="integration",
            scope="src/", criteria=["recover"],
            problem={"symptom_target": "src/cand.txt"})
        self.registry = default_registry()
        self.registry.register_skill(SkillDefinition(
            id="read-file", name="Read file", version="1.0",
            description="Read a file.", capability=Capability.READ,
            target_schema="relative path",
            purpose_template="read:{target}",
            success_markers=("OK",)))

    def adapter(self, stub: StubProvider) -> OpenAICompatAdapter:
        return OpenAICompatAdapter(
            OpenAICompatConfig(endpoint=stub.url, model="stub"),
            self.registry)

    def context(self, findings=None) -> ModelContext:
        return ModelContext(
            mission=self.mission, findings=findings or [],
            workspace_root=str(self.workspace.root),
            evidence_count=len(self.ledger.all_records()))


class TestAValidProposal(unittest.TestCase):
    def test_allow_execution_evidence(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act()]
        adapter = stack.adapter(stub)
        request = adapter.propose(stack.context())
        self.assertEqual(request.capability, Capability.READ)
        result = stack.runtime.submit(request, stack.mission)
        self.assertEqual(
            result.broker_result.decision.decision.value, "allow")
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertTrue(result.execution.success)
        self.assertTrue(result.evidence_ids)


class TestBInvalidProposal(unittest.TestCase):
    def test_unknown_skill_never_executes(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(skill="launch-missiles")]
        adapter = stack.adapter(stub)
        before = stack.broker.submissions
        with self.assertRaises(StructuredProposalError):
            adapter.propose(stack.context())
        self.assertEqual(stack.broker.submissions, before)
        self.assertEqual(
            [r for r in stack.ledger.all_records()
             if r.get("kind") == "request"], [])

    def test_missing_target_never_executes(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(target="")]
        adapter = stack.adapter(stub)
        before = stack.broker.submissions
        with self.assertRaises(StructuredProposalError):
            adapter.propose(stack.context())
        self.assertEqual(stack.broker.submissions, before)


class TestCPolicyDeny(unittest.TestCase):
    def test_valid_proposal_denied_without_execution(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(target="/etc/hostname")]
        adapter = stack.adapter(stub)
        request = adapter.propose(stack.context())
        result = stack.runtime.submit(request, stack.mission)
        self.assertEqual(
            result.broker_result.decision.decision.value, "deny")
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.execution)
        denials = [r for r in stack.ledger.all_records()
                   if r.get("kind") == "decision"
                   and r.get("decision") == "deny"]
        self.assertEqual(len(denials), 1)


class TestDModelRecovery(unittest.TestCase):
    def test_deny_then_valid_alternative(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(target="/etc/hostname"), _act()]
        adapter = stack.adapter(stub)
        first = adapter.propose(stack.context())
        denied = stack.runtime.submit(first, stack.mission)
        self.assertEqual(
            denied.broker_result.decision.decision.value, "deny")
        # Governed result feeds the next model turn.
        second = adapter.propose(stack.context())
        allowed = stack.runtime.submit(second, stack.mission)
        self.assertEqual(
            allowed.broker_result.decision.decision.value, "allow")
        self.assertTrue(allowed.execution.success)
        self.assertEqual(stub.hits, 2)


class TestEVerificationFalsification(unittest.TestCase):
    def test_local_success_then_refutation(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act()]
        adapter = stack.adapter(stub)
        request = adapter.propose(stack.context())
        stack.runtime.submit(request, stack.mission)
        finding = stack.store.register(Finding(
            finding_id="F-e", state=FindingState.UNVERIFIED,
            summary="candidate", target="src/cand.txt"))
        verify_out = stack.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/cand.txt",
                       expected_substring="OK"),
            stack.mission, requester="model")
        self.assertTrue(verify_out.transition_applied)
        challenge_out = stack.falsifier.challenge(
            stack.store.get("F-e"),
            ChallengeSpec(
                capability=Capability.READ, target="src/cand.txt",
                purpose="model:challenge",
                forbidden_substring="DEFECT"),
            stack.mission, requester="model")
        self.assertTrue(challenge_out.counter_example_observed)
        self.assertEqual(challenge_out.finding.state,
                         FindingState.REFUTED)


class TestFReplan(unittest.TestCase):
    def test_refuted_result_replans(self):
        stack = _Stack(self)
        finding = stack.store.register(Finding(
            finding_id="F-f", state=FindingState.UNVERIFIED,
            summary="candidate", target="src/cand.txt"))
        stack.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/cand.txt",
                       expected_substring="OK"),
            stack.mission, requester="model")
        stack.falsifier.challenge(
            stack.store.get("F-f"),
            ChallengeSpec(
                capability=Capability.READ, target="src/cand.txt",
                purpose="model:challenge",
                forbidden_substring="DEFECT"),
            stack.mission, requester="model")
        refuted = stack.store.get("F-f")
        self.assertEqual(refuted.state, FindingState.REFUTED)
        parent = Plan(plan_id="P-i9", mission_id="M-i9", steps=[])
        records = stack.ledger.records_for_finding("F-f")
        receipts = [EvidenceReceipt(
            evidence_id=r.get("evidence_id", ""),
            sequence=r.get("seq", 0),
            producer=r.get("producer", ""),
            payload=dict(r)) for r in records
            if r.get("kind") == "evidence"]
        ctx = FocusedContext(
            refuted_claim=refuted, diagnostic_evidence=receipts,
            mission_scope=stack.mission.scope)
        plan_b = stack.replanner.replan(ctx, parent)
        self.assertEqual(plan_b.parent_plan_id, "P-i9")
        self.assertEqual(plan_b.steps[0].requester, "replanner")
        self.assertEqual(plan_b.steps[0].target, "src/cand.txt")


class TestGGate(unittest.TestCase):
    def test_verified_result_completes(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(target="src/clean.txt")]
        adapter = stack.adapter(stub)
        request = adapter.propose(stack.context())
        stack.runtime.submit(request, stack.mission)
        finding = stack.store.register(Finding(
            finding_id="F-g", state=FindingState.UNVERIFIED,
            summary="clean candidate", target="src/clean.txt"))
        stack.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ,
                       target="src/clean.txt",
                       expected_substring="OK"),
            stack.mission, requester="model")
        self.assertEqual(stack.store.get("F-g").state,
                         FindingState.VERIFIED)
        stack.runtime.submit(ActionRequest(
            sequence=0, requester="model",
            capability=Capability.RUN_TEST,
            target="src/test_ok.py", purpose="model:verify"),
            stack.mission)
        req_seq, dec_seq, res_seq = latest_allowed_success(stack.ledger)
        for producer, allowed in (("probe", True), ("regression", None)):
            payload = {"kind": producer, "result": "passed",
                       "request_seq": req_seq, "result_seq": res_seq}
            if allowed is not None:
                payload["allowed"] = allowed
            stack.ledger.append_evidence(
                evidence_id=digest_id(payload, prefix="T"),
                producer=producer, request_seq=req_seq, decision_seq=dec_seq,
                result_seq=res_seq, payload=payload)
        evaluation = stack.gate.evaluate(GateInputs(
            mission=stack.mission,
            findings=list(stack.store.all()),
            regression_ok=True, behavior_probe_ok=True))
        self.assertEqual(evaluation.verdict, GateVerdict.COMPLETE)


class TestLoopDriver(unittest.TestCase):
    def test_turns_drive_governed_execution(self):
        stack = _Stack(self)
        stub = StubProvider(self)
        stub.queue = [_act(), {"intent": "done"}]
        adapter = stack.adapter(stub)
        from raphael_ibm_bob.harness.loop import drive_turns

        calls = {"n": 0}
        real_propose = adapter.propose

        def scripted(context):
            calls["n"] += 1
            if calls["n"] > 1:
                from raphael_ibm_bob.harness.providers import DoneSignal
                raise DoneSignal("finished")
            return real_propose(context)

        adapter.propose = scripted
        outcome = drive_turns(
            model=adapter, runtime=stack.runtime,
            mission=stack.mission, store=stack.store)
        self.assertEqual(outcome.terminal, "done")
        self.assertEqual(len(outcome.turns), 1)
        self.assertEqual(outcome.turns[0].decision, "allow")


if __name__ == "__main__":
    unittest.main()
