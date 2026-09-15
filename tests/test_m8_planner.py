"""tests.test_m8_planner — M8 mission-driven Planner tests.

M8 proof areas (§10):
    1. Planner derives target from Mission.
    2. Runner does not supply the target directly.
    3. Different Missions can produce different Plan A targets.
    4. Planner remains deterministic.
    5. Planner does not import Runtime/Broker/Policy.
    6. Planner does not invoke the legacy Wave1 loop.
    7. Replanner remains the only Plan B generator.
    8. M7 hero still reaches COMPLETE.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MissionDrivenPlanner(unittest.TestCase):
    def test_planner_derives_target_from_mission(self):
        from raphael_bob import Mission, Planner
        mission = Mission(
            mission_id="M-derived",
            description="x",
            scope="x",
            criteria=["x"],
            problem={"symptom_target": "src/derived.py"},
        )
        plan_a = Planner().plan_a(mission)
        self.assertEqual(plan_a.steps[0].target, "src/derived.py")

    def test_runner_does_not_supply_target_directly(self):
        # Structural: Planner must have no constructor arg; plan_a must
        # take only mission. This is the M8 architectural rule.
        from raphael_bob import Planner
        sig = inspect.signature(Planner.__init__)
        self.assertEqual(list(sig.parameters.keys()), ["self"],
            msg=f"Planner.__init__ must take no args, got {list(sig.parameters)}")
        sig2 = inspect.signature(Planner.plan_a)
        self.assertEqual(list(sig2.parameters.keys()), ["self", "mission"],
            msg=f"Planner.plan_a must take only mission, got {list(sig2.parameters)}")

    def test_different_missions_produce_different_targets(self):
        from raphael_bob import Mission, Planner
        m1 = Mission(mission_id="M-1", description="x", scope="x", criteria=["x"],
                     problem={"symptom_target": "src/a.py"})
        m2 = Mission(mission_id="M-2", description="x", scope="x", criteria=["x"],
                     problem={"symptom_target": "src/b.py"})
        p = Planner()
        self.assertEqual(p.plan_a(m1).steps[0].target, "src/a.py")
        self.assertEqual(p.plan_a(m2).steps[0].target, "src/b.py")
        self.assertNotEqual(p.plan_a(m1).steps[0].target,
                            p.plan_a(m2).steps[0].target)

    def test_planner_is_deterministic(self):
        from raphael_bob import Mission, Planner
        m = Mission(mission_id="M-det", description="x", scope="x", criteria=["x"],
                   problem={"symptom_target": "src/x.py"})
        p = Planner()
        ids = [p.plan_a(m).plan_id for _ in range(5)]
        self.assertEqual(len(set(ids)), 1)
        targets = [p.plan_a(m).steps[0].target for _ in range(5)]
        self.assertEqual(len(set(targets)), 1)

    def test_planner_does_not_import_runtime_broker_policy(self):
        from raphael_bob import Planner
        planner_text = Path("raphael_bob/planner.py").read_text(encoding="utf-8")
        for forbidden in [
            "from raphael_bob.runtime",
            "from raphael_bob.broker",
            "from raphael_bob.policy",
        ]:
            self.assertNotIn(forbidden, planner_text,
                msg=f"planner.py still references {forbidden}")

    def test_planner_does_not_invoke_wave1(self):
        from raphael_bob import Planner
        planner_text = Path("raphael_bob/planner.py").read_text(encoding="utf-8")
        forbidden = ["from raphael.main", "Wave1 cognitive", "wave1_loop"]
        for f in forbidden:
            self.assertNotIn(f, planner_text,
                msg=f"planner.py references {f}")

    def test_replanner_remains_only_plan_B_generator(self):
        from raphael_bob import Planner, Replanner
        planner_text = Path("raphael_bob/planner.py").read_text(encoding="utf-8")
        replanner_text = Path("raphael_bob/replanner.py").read_text(encoding="utf-8")
        self.assertNotIn("plan_b", planner_text.lower())
        self.assertIn("plan_b", replanner_text.lower())

    def test_planner_raises_when_problem_missing(self):
        from raphael_bob import Mission, Planner
        m = Mission(mission_id="M", description="x", scope="x", criteria=["x"])
        with self.assertRaises(ValueError):
            Planner().plan_a(m)

    def test_planner_raises_when_symptom_target_missing(self):
        from raphael_bob import Mission, Planner
        m = Mission(mission_id="M", description="x", scope="x", criteria=["x"],
                   problem={"capability": "read"})
        with self.assertRaises(ValueError):
            Planner().plan_a(m)


class HeroRegressionAfterM8(unittest.TestCase):
    def test_hero_still_reaches_complete(self):
        proc = subprocess.run(
            [sys.executable, "demos/authkit_hero.py"],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertIn("COMPLETE", proc.stdout,
            msg=f"hero failed; stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")

    def test_runner_does_not_construct_planner_with_target(self):
        demo_text = Path("demos/authkit_hero.py").read_text(encoding="utf-8")
        self.assertIn("Planner()", demo_text,
            msg="demo should call Planner() with no arguments")
        self.assertNotIn("Planner(symptom_target", demo_text)
        self.assertIn("problem=", demo_text)
        self.assertIn("symptom_target", demo_text)
        self.assertNotIn("planner.symptom_target", demo_text)

    def test_hero_runner_uses_only_mission(self):
        import re
        demo_text = Path("demos/authkit_hero.py").read_text(encoding="utf-8")
        m = re.search(r"plan_a\(([^)]*)\)", demo_text)
        self.assertIsNotNone(m, msg="demo must call plan_a(...)")
        args = m.group(1)
        self.assertIn("mission", args)
        self.assertNotIn("symptom_target", args)
        self.assertNotIn("login.py", args)

    def test_demo_runs_twice_with_deterministic_plan_a_id(self):
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
        self.assertIn("plan_id=P-f5947b0c1d42", proc1.stdout)
        self.assertIn("plan_id=P-f5947b0c1d42", proc2.stdout)


if __name__ == "__main__":
    unittest.main()
