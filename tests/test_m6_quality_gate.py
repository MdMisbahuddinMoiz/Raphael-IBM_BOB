"""tests/test_m6_quality_gate.py — M6 QualityGate + final orchestration tests."""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from raphael_bob import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    GateVerdict,
    Mission,
    Workspace,
)
from raphael_bob.broker import BOBBroker
from raphael_bob.evidence_ledger import EvidenceLedger
from raphael_bob.falsifier import Falsifier
from raphael_bob.finding import FindingStore
from raphael_bob.policy import BOBPolicy
from raphael_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_bob.replanner import Replanner
from raphael_bob.runner import Runner
from raphael_bob.runtime import BOBRuntime
from raphael_bob.verifier import Verifier


def _make_workspace(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m6_ws_")
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "hello.txt").write_text("hello-m6\n", encoding="utf-8")
    (root / "src" / "fixed.py").write_text(
        "def fixed_session(): return 'OK'\n", encoding="utf-8"
    )
    (root / "src" / "still_buggy.py").write_text(
        "BUG: still contains the original defect\n", encoding="utf-8"
    )
    (root / "src" / "test_smoke.py").write_text(textwrap.dedent("""
        import unittest
        class T(unittest.TestCase):
            def test_true(self):
                self.assertTrue(True)
        if __name__ == "__main__":
            unittest.main()
    """).strip() + "\n", encoding="utf-8")
    testcase.addCleanup(_rm, root)
    return root


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m6_run_")
    testcase.addCleanup(_rm, Path(tmp))
    return Path(tmp)


def _rm(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _mission() -> Mission:
    return Mission(
        mission_id="M-test", description="authkit fix",
        scope="src/", criteria=[
            "all named tests pass",
            "behavior probe passes",
            "no UNVERIFIED findings",
        ],
    )


class _Harness:
    def __init__(self, ws_root: Path, run_root: Path):
        self.workspace = Workspace(ws_root)
        self.ledger = EvidenceLedger(run_root)
        self.policy = BOBPolicy(self.workspace)
        self.broker = BOBBroker(self.policy, self.workspace, ledger=self.ledger)
        self.runtime = BOBRuntime(self.broker)
        self.store = FindingStore(self.ledger)
        self.verifier = Verifier(self.runtime, self.ledger, self.store)
        self.falsifier = Falsifier(self.runtime, self.ledger, self.store)
        self.replanner = Replanner(self.store, self.ledger)
        self.gate = BOBQualityGate(self.ledger)
        self.runner = Runner(
            self.runtime, self.ledger, self.store,
            self.verifier, self.falsifier, self.replanner, self.gate,
        )
        self.mission = _mission()


def _harness(testcase: unittest.TestCase) -> _Harness:
    return _Harness(_make_workspace(testcase), _make_run_dir(testcase))


def _submit_test(h: _Harness) -> None:
    """Inject a passing RUN_TEST record into the ledger."""
    h.runtime.submit(ActionRequest(
        sequence=0, requester="runner",
        capability=Capability.RUN_TEST, target="src/test_smoke.py",
        purpose="required-test",
    ), h.mission)


# -----------------------------------------------------------------------------
# 1. Positive path: valid final result -> COMPLETE
# -----------------------------------------------------------------------------

class PositiveComplete(unittest.TestCase):
    def test_runner_with_required_test_completes(self):
        h = _harness(self)
        _submit_test(h)
        # Run with NO refutation so finding stays VERIFIED and Plan B is
        # skipped. All gate conditions are satisfied.
        outcome = h.runner.run(
            h.mission,
            challenger_target="src/fixed.py",
            challenger_forbidden_substring="THIS-FRAGMENT-DOES-NOT-EXIST",
        )
        self.assertEqual(outcome.finding.state, FindingState.VERIFIED)
        self.assertEqual(outcome.gate_verdict, GateVerdict.COMPLETE)


# -----------------------------------------------------------------------------
# 2. Independent probe failure -> REFUSE
# -----------------------------------------------------------------------------

class IndependentProbeFailure(unittest.TestCase):
    def test_named_test_passes_but_probe_fails(self):
        h = _harness(self)
        _submit_test(h)
        outcome = h.runner.run(
            h.mission,
            challenger_target="src/fixed.py",
            challenger_forbidden_substring="THIS-FRAGMENT-DOES-NOT-EXIST",
            behavior_probe_ok=False,
        )
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)
        self.assertIn("D:independent-behavior-probe",
                      outcome.gate_evaluation.failed)


# -----------------------------------------------------------------------------
# 3. Missing evidence -> REFUSE
# -----------------------------------------------------------------------------

class MissingEvidenceRefuses(unittest.TestCase):
    def test_empty_ledger_refuses(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(_rm, tmp)
        ledger = EvidenceLedger(tmp)
        gate = BOBQualityGate(ledger)
        ws = _make_workspace(self)
        workspace = Workspace(ws)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        store = FindingStore(ledger)
        verifier = Verifier(runtime, ledger, store)
        falsifier = Falsifier(runtime, ledger, store)
        replanner = Replanner(store, ledger)
        runner = Runner(runtime, ledger, store, verifier, falsifier, replanner, gate)
        outcome = runner.run(_mission(), regression_ok=True, behavior_probe_ok=True)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)


# -----------------------------------------------------------------------------
# 4. UNVERIFIED finding -> REFUSE
# -----------------------------------------------------------------------------

class UnverifiedFindingRefuses(unittest.TestCase):
    def test_unverified_finding_blocks_complete(self):
        h = _harness(self)
        _submit_test(h)
        f = Finding(finding_id="F-OPEN", state=FindingState.UNVERIFIED,
                    summary="unresolved", target="src/hello.txt")
        h.store.register(f)
        evaluation = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        self.assertEqual(evaluation.verdict, GateVerdict.REFUSE)
        self.assertIn("G:finding-state", evaluation.failed)


# -----------------------------------------------------------------------------
# 5. REFUTED without replan -> REFUSE
# -----------------------------------------------------------------------------

class RefutedWithoutReplanRefuses(unittest.TestCase):
    def test_refuted_finding_without_replan_blocks(self):
        h = _harness(self)
        _submit_test(h)
        f = Finding(finding_id="F-RF", state=FindingState.UNVERIFIED,
                    summary="r", target="src/hello.txt")
        h.store.register(f)
        # Walk through the lifecycle correctly: UNVERIFIED -> VERIFIED -> REFUTED.
        h.store.transition("F-RF", FindingState.VERIFIED, evidence_seqs=(1,))
        h.store.transition("F-RF", FindingState.REFUTED, evidence_seqs=(1,))
        # No replan was performed; the gate must REFUSE.
        evaluation = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        self.assertEqual(evaluation.verdict, GateVerdict.REFUSE)
        self.assertIn("G:finding-state", evaluation.failed)


# -----------------------------------------------------------------------------
# 6. Final gate decision is persisted
# -----------------------------------------------------------------------------

class GateDecisionPersisted(unittest.TestCase):
    def test_gate_decision_record_written(self):
        h = _harness(self)
        outcome = h.runner.run(h.mission)
        gate_records = h.ledger.gate_decisions()
        self.assertEqual(len(gate_records), 1)
        rec = gate_records[0]
        self.assertEqual(rec.get("decision"), outcome.gate_verdict.value)
        self.assertEqual(rec.get("mission_id"), h.mission.mission_id)
        self.assertEqual(rec.get("run_id"), h.ledger.run_dir().name)
        self.assertIn("A:mission-criterion", rec.get("checks", ()))
        self.assertIn("B:required-tests", rec.get("checks", ()))


# -----------------------------------------------------------------------------
# 7. Runner delegates completion to QualityGate
# -----------------------------------------------------------------------------

class RunnerDelegates(unittest.TestCase):
    def test_runner_returns_gate_verdict(self):
        h = _harness(self)
        outcome = h.runner.run(h.mission)
        self.assertEqual(outcome.gate_verdict, outcome.gate_evaluation.verdict)

    def test_runner_does_not_construct_complete_directly(self):
        runner_text = Path("raphael_bob/runner.py").read_text(encoding="utf-8")
        # The Runner only reads verdict from the gate; it must not
        # construct COMPLETE itself.
        self.assertNotIn("GateVerdict.COMPLETE", runner_text)


# -----------------------------------------------------------------------------
# 8. Non-gate cannot bypass
# -----------------------------------------------------------------------------

class BypassBlocked(unittest.TestCase):
    def test_only_quality_gate_constructs_complete(self):
        for mod_name in [
            "raphael_bob.runtime", "raphael_bob.broker",
            "raphael_bob.policy", "raphael_bob.verifier",
            "raphael_bob.falsifier", "raphael_bob.replanner",
            "raphael_bob.runner",
        ]:
            text = Path(f"{mod_name.replace('.', '/')}.py").read_text(encoding="utf-8")
            self.assertNotIn("GateVerdict.COMPLETE", text,
                msg=f"{mod_name} returns COMPLETE without QualityGate")

    def test_runner_with_fake_gate_cannot_bypass(self):
        h = _harness(self)
        # Even if the gate were replaced with a stub that always returns
        # REFUSE, the runner must report REFUSE. The Runner does NOT
        # override the gate.
        from raphael_bob.contracts import GateVerdict as GV
        from raphael_bob.quality_gate import GateEvaluation

        class _FakeGate:
            def evaluate(self, inputs):
                return GateEvaluation(
                    verdict=GV.REFUSE,
                    passed=("A:mission-criterion",),
                    failed=(),
                    reasons=("fake",), evidence_refs=(), finding_refs=(),
                )
        h.runner._gate = _FakeGate()  # type: ignore[assignment]
        outcome = h.runner.run(h.mission)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)


# -----------------------------------------------------------------------------
# 9. Gate reads real ledger evidence
# -----------------------------------------------------------------------------

class GateReadsRealLedger(unittest.TestCase):
    def test_gate_evaluates_from_ledger_records(self):
        h = _harness(self)
        _submit_test(h)
        evaluation = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        all_evidence_ids = {
            r.get("evidence_id") for r in h.ledger.all_records()
            if r.get("kind") == "evidence"
        }
        real_refs = [eid for eid in evaluation.evidence_refs
                     if eid in all_evidence_ids]
        self.assertGreater(len(real_refs), 0)

    def test_gate_decision_references_ledger_evidence(self):
        h = _harness(self)
        _submit_test(h)
        h.runner.run(h.mission)
        gate_records = h.ledger.gate_decisions()
        rec = gate_records[0]
        refs = rec.get("evidence_refs", ())
        ledger_evidence_ids = {
            r.get("evidence_id") for r in h.ledger.all_records()
            if r.get("kind") == "evidence"
        }
        for ref in refs:
            self.assertIn(ref, ledger_evidence_ids,
                msg=f"gate-decision reference {ref} not in ledger")


# -----------------------------------------------------------------------------
# 10. Determinism
# -----------------------------------------------------------------------------

class GateDeterminism(unittest.TestCase):
    def test_two_evaluations_produce_identical_verdict(self):
        h = _harness(self)
        _submit_test(h)
        ev1 = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        ev2 = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        self.assertEqual(ev1.verdict, ev2.verdict)
        self.assertEqual(set(ev1.passed), set(ev2.passed))
        self.assertEqual(set(ev1.failed), set(ev2.failed))
        self.assertEqual(set(ev1.evidence_refs), set(ev2.evidence_refs))


# -----------------------------------------------------------------------------
# 11. Full control-loop test (M6 §19)
# -----------------------------------------------------------------------------

class FullControlLoop(unittest.TestCase):
    def test_plan_a_refuted_plan_b_complete(self):
        h = _harness(self)
        # Run the default flow: Plan A -> Verifier -> Falsifier -> REFUTED
        # -> Replanner -> Plan B -> Verifier -> QualityGate.
        outcome = h.runner.run(h.mission)
        self.assertGreater(outcome.plan_a_step_runtime_seq, 0)
        self.assertIsNotNone(outcome.plan_b)
        self.assertEqual(outcome.plan_b.parent_plan_id, outcome.plan_a.plan_id)
        self.assertIsNotNone(outcome.plan_b_step_runtime_seq)
        self.assertGreater(outcome.plan_b_step_runtime_seq, 0)
        # The FindingRecord chain shows UNVERIFIED -> VERIFIED -> REFUTED.
        fids = h.ledger.records_for_finding(outcome.finding.finding_id)
        states = [r.get("state") for r in fids if r.get("kind") == "finding"]
        self.assertIn("unverified", states)
        self.assertIn("verified", states)
        self.assertIn("refuted", states)
        # The Replanner persisted its evidence record.
        replanner_evs = [r for r in h.ledger.all_records()
                         if r.get("kind") == "evidence"
                         and r.get("producer") == "replanner"]
        self.assertEqual(len(replanner_evs), 1)
        # Without RUN_TEST the default run returned REFUSE.
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)
        # Inject a passing RUN_TEST and re-evaluate.
        _submit_test(h)
        final = h.gate.evaluate(GateInputs(
            mission=h.mission, findings=list(h.store.all()),
            regression_ok=True, behavior_probe_ok=True,
        ))
        self.assertEqual(final.verdict, GateVerdict.COMPLETE)
        # Final gate decision persisted.
        self.assertEqual(len(h.ledger.gate_decisions()), 2)
        last = h.ledger.gate_decisions()[-1]
        self.assertEqual(last.get("decision"), "complete")


if __name__ == "__main__":
    unittest.main()