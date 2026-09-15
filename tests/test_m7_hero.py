"""tests.test_m7_hero — M7 Planner + authkit hero tests."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class PlannerTests(unittest.TestCase):
    def test_mission_to_plan_a(self):
        from raphael_ibm_bob import Mission, Planner, Capability
        mission = Mission(
            mission_id="M-test", description="x", scope="x", criteria=["x"],
            problem={"symptom_target": "fixtures/authkit/login.py"},
        )
        p = Planner()
        plan_a = p.plan_a(mission)
        self.assertEqual(plan_a.mission_id, mission.mission_id)
        self.assertEqual(len(plan_a.steps), 1)
        self.assertEqual(plan_a.steps[0].capability, Capability.READ)
        self.assertEqual(plan_a.steps[0].target, "fixtures/authkit/login.py")

    def test_plan_a_contains_valid_bob_native_actions(self):
        from raphael_ibm_bob import Mission, Planner, Capability
        mission = Mission(
            mission_id="M-test", description="x", scope="x", criteria=["x"],
            problem={"symptom_target": "fixtures/authkit/login.py"},
        )
        p = Planner()
        plan_a = p.plan_a(mission)
        allowed = {Capability.READ, Capability.LIST, Capability.SEARCH,
                   Capability.WRITE, Capability.RUN_TEST}
        self.assertIn(plan_a.steps[0].capability, allowed)

    def test_plan_a_is_deterministic(self):
        from raphael_ibm_bob import Mission, Planner
        mission = Mission(
            mission_id="M-determinism", description="x", scope="x", criteria=["x"],
            problem={"symptom_target": "fixtures/authkit/login.py"},
        )
        p = Planner()
        ids = [p.plan_a(mission).plan_id for _ in range(5)]
        self.assertEqual(len(set(ids)), 1)

    def test_planner_does_not_invoke_wave1(self):
        from raphael_ibm_bob import Planner
        planner_text = Path("raphael_ibm_bob/planner.py").read_text(encoding="utf-8")
        forbidden = ["from raphael.main", "Wave1 cognitive", "wave1_loop"]
        for f in forbidden:
            self.assertNotIn(f, planner_text,
                msg=f"planner.py references {f}")

    def test_planner_does_not_bypass_runtime_broker_policy(self):
        from raphael_ibm_bob import Planner
        planner_text = Path("raphael_ibm_bob/planner.py").read_text(encoding="utf-8")
        for forbidden in [
            "from raphael_ibm_bob.runtime",
            "from raphael_ibm_bob.broker",
            "from raphael_ibm_bob.policy",
        ]:
            self.assertNotIn(forbidden, planner_text)

    def test_plan_b_remains_replanner_responsibility(self):
        from raphael_ibm_bob import Planner
        planner_text = Path("raphael_ibm_bob/planner.py").read_text(encoding="utf-8")
        self.assertNotIn("plan_b", planner_text.lower())


class AuthkitHeroIntegration(unittest.TestCase):
    def setUp(self):
        from demos.authkit_hero import _install_buggy_session
        _install_buggy_session(ROOT / "fixtures" / "authkit" / "session.py")

    def tearDown(self):
        from demos.authkit_hero import BUGGY_SESSION_TEXT
        (ROOT / "fixtures" / "authkit" / "session.py").write_text(
            BUGGY_SESSION_TEXT, encoding="utf-8",
        )

    def test_hero_runs_to_complete(self):
        from demos.authkit_hero import run_hero
        exit_code = run_hero(keep=False)
        self.assertEqual(exit_code, 0,
            msg=f"hero must produce QualityGate.COMPLETE, got exit={exit_code}")
        text = (ROOT / "fixtures" / "authkit" / "session.py").read_text(encoding="utf-8")
        self.assertIn("BUGGY", text)

    def test_forbidden_action_is_actually_denied(self):
        from raphael_ibm_bob import (
            BOBBroker, BOBPolicy, BOBRuntime, Mission, Workspace,
            ActionRequest, Capability,
        )
        from raphael_ibm_bob.evidence_ledger import EvidenceLedger as _JSONL
        workspace = Workspace(ROOT)
        ledger = _JSONL(Path(tempfile.mkdtemp(prefix="m7fc1_")))
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        rt = runtime.submit(ActionRequest(
            sequence=0, requester="runner",
            capability=Capability.RUN_TEST,
            target="fixtures/authkit/login.py",
            purpose="runner:fc1-probe",
        ), Mission(mission_id="M", description="x", scope="x", criteria=["x"]))
        self.assertEqual(rt.broker_result.decision.decision.value, "deny")
        self.assertIn("name-pattern",
                      rt.broker_result.decision.reason)
        self.assertFalse(rt.broker_result.capability_invoked)

    def test_denied_action_creates_no_side_effect(self):
        from raphael_ibm_bob import (
            BOBBroker, BOBPolicy, BOBRuntime, Mission, Workspace,
            ActionRequest, Capability,
        )
        from raphael_ibm_bob.evidence_ledger import EvidenceLedger as _JSONL
        workspace = Workspace(ROOT)
        ledger = _JSONL(Path(tempfile.mkdtemp(prefix="m7fc1b_")))
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        before_artifacts = set(
            p.name for p in ledger._artifacts._artifacts_dir.iterdir()
        )
        rt = runtime.submit(ActionRequest(
            sequence=0, requester="runner",
            capability=Capability.WRITE, target="/tmp/escape",
            purpose="content=x",
        ), Mission(mission_id="M", description="x", scope="x", criteria=["x"]))
        self.assertEqual(rt.broker_result.decision.decision.value, "deny")
        after_artifacts = set(
            p.name for p in ledger._artifacts._artifacts_dir.iterdir()
        )
        self.assertEqual(before_artifacts, after_artifacts)
        result_kinds = [r.get("kind") for r in ledger.all_records()
                        if r.get("kind") == "result"]
        self.assertEqual(result_kinds, [])

    def test_v1_really_causes_a_regression(self):
        from demos.authkit_hero import _install_buggy_session
        _install_buggy_session(ROOT / "fixtures" / "authkit" / "session.py")
        proc = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertNotEqual(proc.returncode, 0,
            msg=f"probe should fail on buggy; got {proc.returncode}")

    def test_probe_really_detects_regression(self):
        from demos.authkit_hero import _install_buggy_session, _install_v2_fix
        session_path = ROOT / "fixtures" / "authkit" / "session.py"
        _install_buggy_session(session_path)
        proc = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertNotEqual(proc.returncode, 0)
        _install_v2_fix(session_path)
        proc2 = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(proc2.returncode, 0,
            msg=f"probe should pass on v2; got {proc2.returncode}\n{proc2.stdout}")

    def test_v2_really_fixes_actual_defect(self):
        from demos.authkit_hero import _install_buggy_session, _install_v2_fix
        session_path = ROOT / "fixtures" / "authkit" / "session.py"
        _install_buggy_session(session_path)
        proc = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertNotEqual(proc.returncode, 0)
        _install_v2_fix(session_path)
        proc2 = subprocess.run(
            [sys.executable, "probes/auth_behavior_probe.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(proc2.returncode, 0,
            msg=f"probe should pass on v2; got {proc2.returncode}\n{proc2.stdout}")

    def test_final_qualitygate_really_produces_complete(self):
        from demos.authkit_hero import run_hero
        exit_code = run_hero(keep=False)
        self.assertEqual(exit_code, 0)


class HeroEndToEnd(unittest.TestCase):
    def test_demo_produces_human_readable_output(self):
        proc = subprocess.run(
            [sys.executable, "demos/authkit_hero.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        out = proc.stdout
        for i in range(1, 13):
            self.assertIn(f"[{i:02d}]", out,
                msg=f"step {i:02d} missing from demo output")
        self.assertIn("COMPLETE", out)
        runner_text = (ROOT / "raphael_ibm_bob" / "runner.py").read_text()
        self.assertNotIn("GateVerdict.COMPLETE", runner_text)
        self.assertIn("BOBQualityGate", runner_text)

    def test_demo_is_reproducible(self):
        proc1 = subprocess.run(
            [sys.executable, "demos/authkit_hero.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        proc2 = subprocess.run(
            [sys.executable, "demos/authkit_hero.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertIn("COMPLETE", proc1.stdout)
        self.assertIn("COMPLETE", proc2.stdout)
        session_text = (ROOT / "fixtures" / "authkit" / "session.py").read_text()
        self.assertIn("BUGGY", session_text)


if __name__ == "__main__":
    unittest.main()
