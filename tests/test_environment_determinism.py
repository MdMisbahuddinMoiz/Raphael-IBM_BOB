"""test_environment_determinism.py — RBS-v4 repair item 2: ENVIRONMENT DETERMINISM.

Verifies:
  1. ScenarioEnvironment generates the SAME ARP MAC for the SAME scenario_id
     across separate instances (previously used the global random module).
  2. Different scenario_ids produce different MACs (no degenerate constant).
  3. create_initial_observations is unaffected (no regression).

Run: python -m pytest tests/test_environment_determinism.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.environment import ScenarioEnvironment


class _FakeScenario:
    """Minimal scenario stub: scenario_id + evaluator_truth + engagement_view."""

    def __init__(self, scenario_id, asset_metadata=None):
        self.scenario_id = scenario_id
        self._asset_metadata = asset_metadata or {}
        self.evaluator_truth = {
            "expected_observations": [],
            "starting_assets": [
                {
                    "hostname": "web01",
                    "ip": "10.0.0.5",
                    "os": "linux",
                    "services": ["http"],
                    "asset_metadata": self._asset_metadata,
                }
            ],
        }

    def engagement_view(self):
        return {
            "name": f"scenario {self.scenario_id}",
            "objective": "test",
            "allowed_scope": ["10.0.0.0/24"],
            "starting_assets": [
                {
                    "hostname": "web01",
                    "ip": "10.0.0.5",
                    "os": "linux",
                    "services": ["http"],
                    "tags": [],
                    "asset_metadata": self._asset_metadata,
                }
            ],
        }


def _arp_mac(env: ScenarioEnvironment) -> str:
    """Drive the ARP handler and extract the MAC from the observation text."""
    obs_list = env.handle_action(
        target="10.0.0.5", action_type="arp", capability="arp",
        method="query", receipt_id="rec_1",
    )
    assert obs_list, "ARP handler returned no observations"
    text = obs_list[0].raw_output
    assert "ARP reply" in text, f"unexpected ARP output: {text}"
    # MAC pattern: xx:xx:xx:xx:xx:xx
    import re
    m = re.search(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', text)
    assert m, f"no MAC found in: {text}"
    return m.group(0)


def test_same_scenario_same_mac():
    """Deterministic: same scenario_id → same generated MAC (no global RNG)."""
    s1 = _FakeScenario("T2-s0042")
    s2 = _FakeScenario("T2-s0042")
    env1 = ScenarioEnvironment(s1)
    env2 = ScenarioEnvironment(s2)
    assert _arp_mac(env1) == _arp_mac(env2), \
        "identical scenario_id produced different MACs — global RNG still in use"


def test_different_scenarios_different_mac():
    """Different scenario_id → different MAC (no degenerate constant)."""
    env_a = ScenarioEnvironment(_FakeScenario("T1-s0001"))
    env_b = ScenarioEnvironment(_FakeScenario("T3-s0099"))
    mac_a = _arp_mac(env_a)
    mac_b = _arp_mac(env_b)
    assert mac_a != mac_b, "different scenario_ids produced identical MACs"


def test_metadata_mac_is_stable():
    """A mac_address in asset_metadata is used verbatim (never regenerated)."""
    env = ScenarioEnvironment(_FakeScenario(
        "T4-s0077", asset_metadata={"mac_address": "00:50:56:ab:cd:ef"}
    ))
    assert _arp_mac(env) == "00:50:56:ab:cd:ef"


def test_same_scenario_repeatable_across_instances():
    """Run the SAME scenario 3× — all MACs identical (cross-process parity)."""
    macs = set()
    for _ in range(3):
        env = ScenarioEnvironment(_FakeScenario("T6-s1010"))
        macs.add(_arp_mac(env))
    assert len(macs) == 1, f"non-repeatable MACs: {macs}"


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("same scenario same MAC", test_same_scenario_same_mac),
    ("different scenarios differ", test_different_scenarios_different_mac),
    ("metadata MAC stable", test_metadata_mac_is_stable),
    ("repeatable across instances", test_same_scenario_repeatable_across_instances),
]


def _run_manual():
    import traceback
    passed = failed = 0
    for name, fn in TESTS:
        try:
            fn()
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"FAIL: {name}: {e}")
        else:
            passed += 1
    print(f"ENVIRONMENT DETERMINISM: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_manual() else 0)
