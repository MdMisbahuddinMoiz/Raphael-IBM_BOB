"""tests.test_m9_multi_replan — M9 bounded multi-replan recovery tests.

Stdlib-only. NO mocks: every test drives the real production path

    Runner -> Runtime -> Broker -> Policy -> capability
    -> EvidenceLedger -> FindingStore -> Verifier -> Falsifier
    -> Replanner -> QualityGate

over a deterministic synthetic workspace with three candidates:

    src/cand_a.txt   "OK"                       (Plan A claim)
    src/cand_b.txt   "OK" + "DEFECT: ..."       (wrong, observable)
    src/cand_c.txt   "OK" + "TODO-beta ..."     (wrong for a coarse
                                                 probe, clean for the
                                                 strict probe)

Each recovery iteration challenges the current finding with an
explicit per-iteration ChallengeSpec. A counter-example is a REAL
broker-mediated observation (file content through Policy ALLOW);
the Replanner derives the next target from the persisted
counter-evidence record, never from hard-coded Runner knowledge.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List

from raphael_bob import (
    Capability,
    FindingState,
    GateVerdict,
    Mission,
    Workspace,
)
from raphael_bob.broker import BOBBroker
from raphael_bob.evidence_ledger import EvidenceLedger
from raphael_bob.falsifier import ChallengeSpec, Falsifier
from raphael_bob.finding import FindingStore
from raphael_bob.planner import Planner
from raphael_bob.policy import BOBPolicy
from raphael_bob.quality_gate import BOBQualityGate
from raphael_bob.replanner import Replanner
from raphael_bob.runner import Runner, RunnerOutcome
from raphael_bob.runtime import BOBRuntime
from raphael_bob.verifier import Verifier


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

def _make_workspace(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m9_ws_")
    root = Path(tmp)
    testcase.addCleanup(shutil.rmtree, root, True)
    src = root / "src"
    src.mkdir()
    (src / "cand_a.txt").write_text("OK\n", encoding="utf-8")
    (src / "cand_b.txt").write_text(
        "OK\nDEFECT: beta handler missing\n", encoding="utf-8")
    (src / "cand_c.txt").write_text(
        "OK\nNOTE: TODO-beta shim retained for compatibility\n",
        encoding="utf-8")
    (src / "test_recovery.py").write_text(
        "import unittest\n"
        "class RecoveryTest(unittest.TestCase):\n"
        "    def test_marker(self):\n"
        "        self.assertTrue(True)\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8")
    subdir = src / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text(
        "DEFECT: nested issue\n", encoding="utf-8")
    return root


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_bob_m9_run_")
    testcase.addCleanup(shutil.rmtree, Path(tmp), True)
    return Path(tmp)


def _mission() -> Mission:
    return Mission(
        mission_id="M-m9-bounded-recovery",
        description="bounded multi-replan recovery mission",
        scope="src/",
        criteria=[
            "bounded recovery completes",
            "required tests pass",
        ],
        problem={
            "symptom_target": "src/cand_a.txt",
            "capability": "read",
            "purpose": "m9:initial-probe",
        },
    )


class _Harness:
    def __init__(self, ws_root: Path, run_root: Path):
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
        self.runner = Runner(
            self.runtime, self.ledger, self.store,
            self.verifier, self.falsifier, self.replanner, self.gate,
        )
        self.mission = _mission()


def _harness(testcase: unittest.TestCase) -> _Harness:
    return _Harness(_make_workspace(testcase), _make_run_dir(testcase))


def _success_specs() -> List[ChallengeSpec]:
    """Per-iteration challenges for the A -> B -> C success path."""
    return [
        ChallengeSpec(
            capability=Capability.READ,
            target="src/cand_b.txt",
            purpose="m9:challenge-F1",
            forbidden_substring="DEFECT",
        ),
        ChallengeSpec(
            capability=Capability.READ,
            target="src/cand_c.txt",
            purpose="m9:challenge-F2",
            forbidden_substring="TODO-beta",
        ),
        ChallengeSpec(
            capability=Capability.READ,
            target="src/cand_c.txt",
            purpose="m9:challenge-F3",
            forbidden_substring="BUG:",
        ),
    ]


def _run_success(h: _Harness) -> RunnerOutcome:
    return h.runner.run(
        h.mission,
        candidate_target="src/cand_a.txt",
        candidate_summary="candidate A leaves the defect in scope",
        challenge_specs=_success_specs(),
        verification_tests=("src/test_recovery.py",),
        max_replans=2,
    )


def _finding_states(h: _Harness, finding_id: str) -> List[str]:
    return [r.get("state") for r in h.ledger.records_for_finding(finding_id)
            if r.get("kind") == "finding"]


def _replanner_records(h: _Harness) -> list:
    return [r for r in h.ledger.all_records()
            if r.get("kind") == "evidence"
            and r.get("producer") == "replanner"]


# -----------------------------------------------------------------------------
# §16.1 M8 mission-driven Planner still works through the M9 Runner.
# -----------------------------------------------------------------------------

class MissionDrivenPlannerHolds(unittest.TestCase):
    def test_plan_a_comes_from_mission(self):
        h = _harness(self)
        outcome = _run_success(h)
        self.assertEqual(outcome.plan_a.steps[0].target, "src/cand_a.txt")
        self.assertEqual(outcome.plan_a.mission_id, h.mission.mission_id)

    def test_different_missions_give_different_plan_a(self):
        h = _harness(self)
        p = Planner()
        m1 = _mission()
        m2 = Mission(
            mission_id="M-m9-other", description="x", scope="src/",
            criteria=["x"],
            problem={"symptom_target": "src/cand_b.txt"},
        )
        self.assertNotEqual(p.plan_a(m1).steps[0].target,
                            p.plan_a(m2).steps[0].target)


# -----------------------------------------------------------------------------
# §16.2-4 F1 refuted; Plan B created with parent Plan A.
# -----------------------------------------------------------------------------

class FirstRecovery(unittest.TestCase):
    def test_f1_is_refuted(self):
        h = _harness(self)
        outcome = _run_success(h)
        self.assertEqual(outcome.finding.finding_id,
                         f"F-{outcome.plan_a.plan_id[2:8]}")
        self.assertEqual(outcome.finding.state, FindingState.REFUTED)
        states = _finding_states(h, outcome.finding.finding_id)
        self.assertEqual(states, ["unverified", "verified", "refuted"])

    def test_plan_b_has_parent_plan_a(self):
        h = _harness(self)
        outcome = _run_success(h)
        self.assertIsNotNone(outcome.plan_b)
        self.assertEqual(outcome.plan_b.parent_plan_id,
                         outcome.plan_a.plan_id)
        self.assertNotEqual(outcome.plan_b.plan_id, outcome.plan_a.plan_id)
        # Plan B targets the evidence-identified defect, not Plan A.
        self.assertEqual(outcome.plan_b.steps[0].target, "src/cand_b.txt")


# -----------------------------------------------------------------------------
# §16.5-7 Plan B produces F2; F2 is independently verified then refuted.
# -----------------------------------------------------------------------------

class SecondFinding(unittest.TestCase):
    def _f2(self, h: _Harness, outcome: RunnerOutcome):
        f2_id = f"F-{outcome.plan_b.plan_id[2:8]}"
        f2 = h.store.get(f2_id)
        self.assertIsNotNone(f2)
        return f2

    def test_plan_b_produces_new_finding_f2(self):
        h = _harness(self)
        outcome = _run_success(h)
        f2 = self._f2(h, outcome)
        self.assertEqual(f2.target, "src/cand_b.txt")
        self.assertNotEqual(f2.finding_id, outcome.finding.finding_id)
        self.assertEqual(f2.supersedes, outcome.finding.finding_id)

    def test_f2_verified_then_refuted(self):
        h = _harness(self)
        outcome = _run_success(h)
        f2 = self._f2(h, outcome)
        self.assertEqual(f2.state, FindingState.REFUTED)
        states = _finding_states(h, f2.finding_id)
        self.assertEqual(states, ["unverified", "verified", "refuted"])


# -----------------------------------------------------------------------------
# §16.8-9 Replan from F2 creates Plan C with parent Plan B.
# -----------------------------------------------------------------------------

class SecondRecovery(unittest.TestCase):
    def test_plan_c_has_parent_plan_b(self):
        h = _harness(self)
        outcome = _run_success(h)
        self.assertIsNotNone(outcome.plan_c)
        self.assertEqual(outcome.plan_c.parent_plan_id,
                         outcome.plan_b.plan_id)
        self.assertEqual(outcome.plan_c.steps[0].target, "src/cand_c.txt")

    def test_plan_c_produces_f3_verified(self):
        h = _harness(self)
        outcome = _run_success(h)
        f3_id = f"F-{outcome.plan_c.plan_id[2:8]}"
        f3 = h.store.get(f3_id)
        self.assertIsNotNone(f3)
        self.assertEqual(f3.state, FindingState.VERIFIED)
        self.assertEqual(f3.target, "src/cand_c.txt")
        self.assertEqual(_finding_states(h, f3_id),
                         ["unverified", "verified"])


# -----------------------------------------------------------------------------
# §16.10 Every recovery action is requested_by="replanner" with linkage.
# -----------------------------------------------------------------------------

class RecoveryProvenance(unittest.TestCase):
    def test_recovery_steps_carry_replanner_provenance(self):
        h = _harness(self)
        outcome = _run_success(h)
        for plan in (outcome.plan_b, outcome.plan_c):
            step = plan.steps[0]
            self.assertEqual(step.requester, "replanner")
            self.assertTrue(step.finding_id)
            self.assertIn(step.finding_id, step.purpose)
            self.assertEqual(step.plan_id, plan.plan_id)
        self.assertEqual(outcome.plan_b.steps[0].finding_id,
                         outcome.finding.finding_id)


# -----------------------------------------------------------------------------
# §16.11 Every recovery action remains Broker/Policy mediated.
# -----------------------------------------------------------------------------

class RecoveryMediation(unittest.TestCase):
    def test_plan_steps_have_allow_decisions(self):
        h = _harness(self)
        outcome = _run_success(h)
        records = h.ledger.all_records()
        for plan in (outcome.plan_a, outcome.plan_b, outcome.plan_c):
            target = plan.steps[0].target
            reqs = [r for r in records
                    if r.get("kind") == "request"
                    and r.get("target") == target]
            self.assertTrue(reqs, msg=f"no request for {target}")
            for req in reqs:
                decs = [r for r in records
                        if r.get("kind") == "decision"
                        and r.get("request_seq") == req.get("seq")]
                self.assertTrue(
                    any(d.get("decision") == "allow" for d in decs),
                    msg=f"no ALLOW decision for {target}")
        self.assertGreater(h.broker.capability_invocations, 0)

    def test_unauthorized_plan_c_denied_without_side_effect(self):
        # §13: the counter-evidence names a directory, so Plan C's READ
        # is DENIED by Policy. Real denial through the boundary: no
        # capability invocation, no result record, workspace untouched.
        h = _harness(self)
        before = sorted(p.name for p in
                        (h.workspace.root / "src" / "subdir").iterdir())
        outcome = h.runner.run(
            h.mission,
            candidate_target="src/cand_a.txt",
            candidate_summary="candidate A leaves the defect in scope",
            challenge_specs=[
                ChallengeSpec(
                    capability=Capability.READ,
                    target="src/cand_b.txt",
                    purpose="m9:challenge-F1",
                    forbidden_substring="DEFECT",
                ),
                ChallengeSpec(
                    capability=Capability.SEARCH,
                    target="src/subdir",
                    purpose="DEFECT",
                    forbidden_substring="DEFECT",
                ),
            ],
            max_replans=2,
        )
        self.assertIsNotNone(outcome.plan_c)
        self.assertEqual(outcome.plan_c.steps[0].target, "src/subdir")
        records = h.ledger.all_records()
        reqs = [r for r in records
                if r.get("kind") == "request"
                and r.get("target") == "src/subdir"
                and r.get("capability") == "read"]
        self.assertTrue(reqs, msg="Plan C READ request missing")
        for req in reqs:
            decs = [r for r in records
                    if r.get("kind") == "decision"
                    and r.get("request_seq") == req.get("seq")]
            self.assertTrue(
                any(d.get("decision") == "deny" for d in decs),
                msg="Plan C READ was not denied")
            results = [r for r in records
                       if r.get("kind") == "result"
                       and r.get("request_seq") == req.get("seq")]
            self.assertEqual(results, [],
                             msg="denied Plan C action left a result")
        after = sorted(p.name for p in
                       (h.workspace.root / "src" / "subdir").iterdir())
        self.assertEqual(before, after)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)


# -----------------------------------------------------------------------------
# §16.12 Ledger reconstructs A -> F1 -> B -> F2 -> C.
# -----------------------------------------------------------------------------

class LedgerReconstruction(unittest.TestCase):
    def test_causal_chain_reconstructible(self):
        h = _harness(self)
        outcome = _run_success(h)
        f1 = outcome.finding.finding_id
        f2 = h.store.get(f"F-{outcome.plan_b.plan_id[2:8]}").finding_id
        f3 = h.store.get(f"F-{outcome.plan_c.plan_id[2:8]}").finding_id
        recs = _replanner_records(h)
        self.assertEqual(len(recs), 2)
        first, second = recs
        self.assertEqual(first["payload"]["parent_plan_id"],
                         outcome.plan_a.plan_id)
        self.assertEqual(first["payload"]["plan_b_id"],
                         outcome.plan_b.plan_id)
        self.assertEqual(first["payload"]["refuted_finding_id"], f1)
        self.assertEqual(second["payload"]["parent_plan_id"],
                         outcome.plan_b.plan_id)
        self.assertEqual(second["payload"]["plan_b_id"],
                         outcome.plan_c.plan_id)
        self.assertEqual(second["payload"]["refuted_finding_id"], f2)
        # Finding supersede chain mirrors the plan chain.
        self.assertEqual(h.store.get(f2).supersedes, f1)
        self.assertEqual(h.store.get(f3).supersedes, f2)
        # Outcome carries the full finding sequence.
        self.assertEqual(
            [f.finding_id for f in outcome.findings], [f1, f2, f3])


# -----------------------------------------------------------------------------
# §16.13 Deterministic recovery for identical inputs.
# -----------------------------------------------------------------------------

class RecoveryDeterminism(unittest.TestCase):
    def test_identical_runs_agree(self):
        h1 = _harness(self)
        h2 = _harness(self)
        o1 = _run_success(h1)
        o2 = _run_success(h2)
        self.assertEqual(o1.plan_a.plan_id, o2.plan_a.plan_id)
        self.assertEqual(o1.plan_b.plan_id, o2.plan_b.plan_id)
        self.assertEqual(o1.plan_c.plan_id, o2.plan_c.plan_id)
        self.assertEqual(o1.plan_a.steps[0].target,
                         o2.plan_a.steps[0].target)
        self.assertEqual(o1.plan_b.steps[0].target,
                         o2.plan_b.steps[0].target)
        self.assertEqual(o1.plan_c.steps[0].target,
                         o2.plan_c.steps[0].target)
        self.assertEqual(
            [f.finding_id for f in o1.findings],
            [f.finding_id for f in o2.findings])
        self.assertEqual(o1.plan_b.parent_plan_id,
                         o2.plan_b.parent_plan_id)
        self.assertEqual(o1.plan_c.parent_plan_id,
                         o2.plan_c.parent_plan_id)
        self.assertEqual(o1.gate_verdict, o2.gate_verdict)
        self.assertEqual(o1.plan_a_step_runtime_seq,
                         o2.plan_a_step_runtime_seq)


# -----------------------------------------------------------------------------
# §16.14 Bounded exhaustion terminates with REFUSE (no fourth attempt).
# -----------------------------------------------------------------------------

class BoundedTermination(unittest.TestCase):
    def test_exhaustion_refuses(self):
        h = _harness(self)
        specs = _success_specs()
        specs[2] = ChallengeSpec(
            capability=Capability.READ,
            target="src/cand_c.txt",
            purpose="m9:challenge-F3-final",
            forbidden_substring="TODO-beta",
        )
        outcome = h.runner.run(
            h.mission,
            candidate_target="src/cand_a.txt",
            candidate_summary="candidate A leaves the defect in scope",
            challenge_specs=specs,
            verification_tests=("src/test_recovery.py",),
            max_replans=2,
        )
        # Terminal finding is REFUTED with no replan left for it.
        f3_id = f"F-{outcome.plan_c.plan_id[2:8]}"
        f3 = h.store.get(f3_id)
        self.assertEqual(f3.state, FindingState.REFUTED)
        self.assertEqual(outcome.gate_verdict, GateVerdict.REFUSE)
        self.assertIn("G:finding-state",
                      outcome.gate_evaluation.failed)
        # Bounded: exactly two replans (B and C), no fourth plan.
        self.assertEqual(len(_replanner_records(h)), 2)
        self.assertIsNotNone(outcome.plan_a)
        self.assertIsNotNone(outcome.plan_b)
        self.assertIsNotNone(outcome.plan_c)


# -----------------------------------------------------------------------------
# §16.15 Successful bounded recovery reaches QualityGate COMPLETE.
# -----------------------------------------------------------------------------

class BoundedSuccess(unittest.TestCase):
    def test_success_completes(self):
        h = _harness(self)
        outcome = _run_success(h)
        self.assertEqual(outcome.gate_verdict, GateVerdict.COMPLETE)
        self.assertIn("B:required-tests",
                      outcome.gate_evaluation.passed)
        self.assertIn("C:regression", outcome.gate_evaluation.passed)
        self.assertEqual(outcome.gate_verdict,
                         outcome.gate_evaluation.verdict)


# -----------------------------------------------------------------------------
# §16.16-17 Runner never COMPLETEs directly; Wave1 stays isolated.
# -----------------------------------------------------------------------------

class RunnerAuthority(unittest.TestCase):
    def test_runner_never_constructs_complete(self):
        text = Path("raphael_bob/runner.py").read_text(encoding="utf-8")
        self.assertNotIn("GateVerdict.COMPLETE", text)
        self.assertIn("BOBQualityGate", text)

    def test_wave1_remains_isolated(self):
        text = Path("raphael_bob/runner.py").read_text(encoding="utf-8")
        for forbidden in ("from raphael.main", "import raphael.main",
                          "wave1_loop"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
