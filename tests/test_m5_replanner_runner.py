"""tests/test_m5_replanner_runner.py — M5 Replanner + Runner tests.

Stdlib-only. Real Runtime + Broker + Policy + EvidenceLedger path. NO mocks.

Coverage maps to the brief's §11 proof areas:
    1. REFUTED finding produces FocusedContext
    2. FocusedContext contains actual evidence sequence(s)
    3. Replanner creates Plan B
    4. Plan B.parent == Plan A
    5. Plan B is causally derived from refutation evidence
    6. Plan B actions use requested_by="replanner"
    7. Plan B actions carry a purpose/finding reference
    8. Runner invokes Verifier/Falsifier in the correct sequence
    9. replan occurs only after actual refutation
   10. repeated identical inputs produce deterministic Plan B
   11. the legacy Wave1 loop is not used
   12. final completion is NOT decided by Runner
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from raphael_bob import (
    ActionRequest,
    Capability,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    Workspace,
)
from raphael_bob.broker import BOBBroker
from raphael_bob.evidence_ledger import EvidenceLedger
from raphael_bob.falsifier import (
    ChallengeSpec,
    Falsifier,
)
from raphael_bob.finding import FindingStore
from raphael_bob.policy import BOBPolicy
from raphael_bob.replanner import (
    ReplanStrategy,
    Replanner,
    derive_plan_b_id,
)
from raphael_bob.runner import PlannerStub, Runner
from raphael_bob.runtime import BOBRuntime
from raphael_bob.verifier import RetestSpec, Verifier


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

def _make_workspace(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m5_ws_")
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "hello.txt").write_text("hello-m5\n", encoding="utf-8")
    (root / "src" / "fixed.py").write_text(
        "def fixed_session(): return 'OK'\n", encoding="utf-8"
    )
    (root / "src" / "still_buggy.py").write_text(
        "BUG: still contains the original defect\n", encoding="utf-8"
    )
    testcase.addCleanup(_rm, root)
    return root


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m5_run_")
    testcase.addCleanup(_rm, Path(tmp))
    return Path(tmp)


def _rm(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _mission(scope: str = "src/") -> Mission:
    return Mission(
        mission_id="M-test", description="authkit fix",
        scope=scope, criteria=["all named tests pass", "behavior probe passes"],
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
        from raphael_bob.quality_gate import BOBQualityGate
        self.gate = BOBQualityGate(self.ledger)
        self.runner = Runner(
            self.runtime, self.ledger, self.store,
            self.verifier, self.falsifier, self.replanner, self.gate,
        )
        self.mission = _mission()

def _harness(testcase: unittest.TestCase) -> _Harness:
    return _Harness(_make_workspace(testcase), _make_run_dir(testcase))


def _build_receipts(ledger: EvidenceLedger, finding_id: str) -> list:
    from raphael_bob.contracts import EvidenceReceipt
    out: list = []
    for rec in ledger.records_for_finding(finding_id):
        if rec.get("kind") != "evidence":
            continue
        out.append(EvidenceReceipt(
            evidence_id=rec.get("evidence_id", ""),
            sequence=rec.get("seq", 0),
            producer=rec.get("producer", ""),
            payload=dict(rec),
        ))
    return out


def _build_context_for(h: _Harness, fid: str) -> FocusedContext:
    f = Finding(finding_id=fid, state=FindingState.UNVERIFIED,
                summary="session.py mishandles tokens", target="src/fixed.py")
    h.store.register(f)
    h.verifier.verify(
        f,
        RetestSpec(capability=Capability.READ, target="src/fixed.py",
                   expected_substring="OK"),
        h.mission,
    )
    h.falsifier.challenge(
        h.store.get(fid),
        ChallengeSpec(capability=Capability.READ, target="src/still_buggy.py",
                      forbidden_substring="BUG: still contains the original defect"),
        h.mission,
    )
    refuted = h.store.get(fid)
    return FocusedContext(
        refuted_claim=refuted,
        diagnostic_evidence=_build_receipts(h.ledger, fid),
        mission_scope=h.mission.scope,
    )


# -----------------------------------------------------------------------------
# 1. REFUTED finding produces FocusedContext
# 2. FocusedContext contains actual evidence sequence(s)
# -----------------------------------------------------------------------------

class FocusedContextConstruction(unittest.TestCase):
    def test_refuted_finding_builds_focused_context(self):
        h = _harness(self)
        finding = Finding(finding_id="F-1", state=FindingState.UNVERIFIED,
                          summary="session.py mishandles tokens", target="src/fixed.py")
        h.store.register(finding)
        h.verifier.verify(
            finding,
            RetestSpec(capability=Capability.READ, target="src/fixed.py",
                       expected_substring="OK"),
            h.mission,
        )
        h.falsifier.challenge(
            h.store.get("F-1"),
            ChallengeSpec(capability=Capability.READ, target="src/still_buggy.py",
                          forbidden_substring="BUG: still contains the original defect"),
            h.mission,
        )
        refuted = h.store.get("F-1")
        self.assertEqual(refuted.state, FindingState.REFUTED)
        ctx = FocusedContext(
            refuted_claim=refuted,
            diagnostic_evidence=_build_receipts(h.ledger, refuted.finding_id),
            mission_scope=h.mission.scope,
        )
        self.assertEqual(ctx.refuted_claim.state, FindingState.REFUTED)
        self.assertGreater(len(ctx.diagnostic_evidence), 0)
        for ev in ctx.diagnostic_evidence:
            self.assertGreaterEqual(ev.sequence, 1)
        real_ids = {r.get("evidence_id") for r in h.ledger.all_records()
                    if r.get("kind") == "evidence"}
        self.assertTrue(any(ev.evidence_id in real_ids for ev in ctx.diagnostic_evidence))


# -----------------------------------------------------------------------------
# 3-7. Replanner creates Plan B; parent linkage; provenance; determinism
# -----------------------------------------------------------------------------

class ReplannerProducesPlanB(unittest.TestCase):
    def test_replan_returns_plan_b_with_parent_linkage(self):
        h = _harness(self)
        ctx = _build_context_for(h, "F-1")
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id,
                      steps=[ActionRequest(
                          sequence=0, requester="planner",
                          capability=Capability.READ, target="src/login.py",
                          purpose="plan-a", plan_id="P-AAA", finding_id=None)])
        plan_b = h.replanner.replan(ctx, plan_a)
        self.assertEqual(plan_b.parent_plan_id, plan_a.plan_id)
        self.assertEqual(plan_b.mission_id, plan_a.mission_id)
        self.assertEqual(len(plan_b.steps), 1)
        step = plan_b.steps[0]
        self.assertEqual(step.requester, "replanner")
        self.assertEqual(step.finding_id, "F-1")
        self.assertIn("F-1", step.purpose)
        self.assertEqual(step.plan_id, plan_b.plan_id)

    def test_replan_target_is_different_from_plan_a_wrong_target(self):
        h = _harness(self)
        ctx = _build_context_for(h, "F-1")
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id,
                      steps=[ActionRequest(
                          sequence=0, requester="planner",
                          capability=Capability.READ, target="src/login.py",
                          purpose="plan-a", plan_id="P-AAA", finding_id=None)])
        plan_b = h.replanner.replan(ctx, plan_a)
        self.assertNotEqual(plan_b.steps[0].target, plan_a.steps[0].target)
        self.assertEqual(plan_b.steps[0].target, "src/still_buggy.py")

    def test_replan_persists_provenance_evidence(self):
        h = _harness(self)
        ctx = _build_context_for(h, "F-1")
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id,
                      steps=[])
        plan_b = h.replanner.replan(ctx, plan_a)
        evs = [r for r in h.ledger.all_records() if r.get("kind") == "evidence"
               and r.get("producer") == "replanner"]
        self.assertGreaterEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e.get("finding_id"), "F-1")
        self.assertEqual(e.get("payload", {}).get("parent_plan_id"), "P-AAA")
        self.assertEqual(e.get("payload", {}).get("plan_b_id"), plan_b.plan_id)

    def test_replan_requires_refuted_finding(self):
        h = _harness(self)
        finding = Finding(finding_id="F-2", state=FindingState.UNVERIFIED,
                          summary="x", target="src/fixed.py")
        h.store.register(finding)
        ctx = FocusedContext(
            refuted_claim=finding,
            diagnostic_evidence=[],
            mission_scope=h.mission.scope,
        )
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id, steps=[])
        with self.assertRaises(ValueError):
            h.replanner.replan(ctx, plan_a)

    def test_replan_requires_diagnostic_evidence(self):
        h = _harness(self)
        f = Finding(finding_id="F-1", state=FindingState.UNVERIFIED,
                    summary="x", target="src/fixed.py")
        h.store.register(f)
        h.store.transition("F-1", FindingState.VERIFIED, evidence_seqs=(1,))
        h.store.transition("F-1", FindingState.REFUTED, evidence_seqs=(1,))
        ctx = FocusedContext(
            refuted_claim=h.store.get("F-1"),
            diagnostic_evidence=[],
            mission_scope=h.mission.scope,
        )
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id, steps=[])
        with self.assertRaises(ValueError):
            h.replanner.replan(ctx, plan_a)

    def test_replan_is_deterministic(self):
        h = _harness(self)
        ctx = _build_context_for(h, "F-1")
        plan_a = Plan(plan_id="P-AAA", mission_id=h.mission.mission_id,
                      steps=[ActionRequest(
                          sequence=0, requester="planner",
                          capability=Capability.READ, target="src/login.py",
                          purpose="plan-a", plan_id="P-AAA", finding_id=None)])
        plan_b1 = h.replanner.replan(ctx, plan_a)
        plan_b2 = h.replanner.replan(ctx, plan_a)
        self.assertEqual(plan_b1.plan_id, plan_b2.plan_id)
        self.assertEqual(
            [s.to_dict() for s in plan_b1.steps],
            [s.to_dict() for s in plan_b2.steps],
        )
        self.assertEqual(plan_b1.plan_id, derive_plan_b_id(plan_a, "F-1"))


# -----------------------------------------------------------------------------
# 8. Runner invokes Verifier/Falsifier in correct sequence
# -----------------------------------------------------------------------------

class RunnerSequence(unittest.TestCase):
    def test_runner_returns_refuse_with_plan_b(self):
        h = _harness(self)
        outcome = h.runner.run(h.mission)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)
        self.assertIsNotNone(outcome.plan_a)
        self.assertIsNotNone(outcome.plan_b)
        self.assertEqual(outcome.plan_b.parent_plan_id, outcome.plan_a.plan_id)
        self.assertEqual(outcome.finding.state, FindingState.REFUTED)
        self.assertEqual(outcome.plan_b.steps[0].requester, "replanner")
        self.assertEqual(outcome.plan_b.steps[0].finding_id, outcome.finding.finding_id)


# -----------------------------------------------------------------------------
# 9. Replan occurs only after actual refutation
# -----------------------------------------------------------------------------

class ReplanOnlyAfterRefutation(unittest.TestCase):
    def test_runner_does_not_replan_when_falsifier_finds_nothing(self):
        h = _harness(self)
        outcome = h.runner.run(
            h.mission,
            challenger_target="src/fixed.py",
            challenger_forbidden_substring="THIS-FRAGMENT-DOES-NOT-EXIST",
        )
        self.assertEqual(outcome.finding.state, FindingState.VERIFIED)
        self.assertIsNone(outcome.plan_b)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)


# -----------------------------------------------------------------------------
# 10. Determinism for identical inputs
# -----------------------------------------------------------------------------

class ReplanDeterminism(unittest.TestCase):
    def test_two_runs_produce_identical_plan_b_ids(self):
        ids = []
        for _ in range(2):
            h = _harness(self)
            ctx = _build_context_for(h, "F-1")
            plan_a = Plan(plan_id="P-SAME", mission_id=h.mission.mission_id,
                          steps=[])
            plan_b = h.replanner.replan(ctx, plan_a)
            ids.append(plan_b.plan_id)
        self.assertEqual(ids[0], ids[1])


# -----------------------------------------------------------------------------
# 11. The legacy Wave1 loop is not used
# -----------------------------------------------------------------------------

class Wave1Isolation(unittest.TestCase):
    def test_main_py_not_imported(self):
        from pathlib import Path
        target = Path("raphael_bob/runner.py").read_text(encoding="utf-8")
        forbidden = [
            "from raphael.main",
            "import raphael.main",
            "src.raphael.main",
        ]
        for f in forbidden:
            self.assertNotIn(f, target, msg=f"runner.py references {f}")

    def test_no_runpy_loop_invocation(self):
        from pathlib import Path
        offenders: list[str] = []
        for p in Path("raphael_bob").rglob("*.py"):
            if p.name == "__init__.py":
                continue
            if p.name == "legacy.py":
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            stripped = re.sub(r'"""[\s\S]*?"""', '', text)
            stripped = re.sub(r"'''[\s\S]*?'''", '', stripped)
            for line in stripped.splitlines():
                if "raphael.main" in line and "import" in line:
                    offenders.append(f"{p}:{line.strip()[:60]}")
        self.assertEqual(offenders, [])


# -----------------------------------------------------------------------------
# 12. Final completion is NOT decided by Runner
# -----------------------------------------------------------------------------

class RunnerNeverCompletes(unittest.TestCase):
    def test_runner_never_returns_complete(self):
        h = _harness(self)
        outcome = h.runner.run(h.mission)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)
        self.assertNotEqual(outcome.gate_verdict, GateVerdict.COMPLETE)


# -----------------------------------------------------------------------------
# End-to-end causal chain
# -----------------------------------------------------------------------------

class EndToEndCausalChain(unittest.TestCase):
    def test_full_plan_a_to_plan_b_causal_chain(self):
        h = _harness(self)
        outcome = h.runner.run(h.mission)
        self.assertGreater(outcome.plan_a_step_runtime_seq, 0)
        self.assertIsNotNone(outcome.plan_b_step_runtime_seq)
        self.assertGreater(outcome.plan_b_step_runtime_seq, 0)
        self.assertNotEqual(outcome.plan_a.plan_id, outcome.plan_b.plan_id)
        self.assertNotEqual(outcome.plan_b.steps[0].target,
                            outcome.plan_a.steps[0].target)
        replanner_evs = [r for r in h.ledger.all_records()
                         if r.get("kind") == "evidence"
                         and r.get("producer") == "replanner"]
        self.assertEqual(len(replanner_evs), 1)
        ev = replanner_evs[0]
        self.assertEqual(ev.get("payload", {}).get("parent_plan_id"),
                         outcome.plan_a.plan_id)
        self.assertEqual(ev.get("payload", {}).get("plan_b_id"),
                         outcome.plan_b.plan_id)
        self.assertEqual(ev.get("payload", {}).get("refuted_finding_id"),
                         outcome.finding.finding_id)
        fids = h.ledger.records_for_finding(outcome.finding.finding_id)
        states = [r.get("state") for r in fids if r.get("kind") == "finding"]
        self.assertIn("unverified", states)
        self.assertIn("verified", states)
        self.assertIn("refuted", states)


if __name__ == "__main__":
    unittest.main()