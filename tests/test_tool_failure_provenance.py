"""test_tool_failure_provenance.py — RBS-v4 repair item 6: TOOL FAILURE VS REAL OBSERVATION.

Verifies:
  1. RawObservation with is_tool_failure=True normalizes to TrustLevel.TOOL_FAILURE
  2. Normal RawObservation normalizes to TrustLevel.TOOL_OBSERVATION
  3. The trust level distinction is preserved in the Evidence objects.

Run: python -m pytest tests/test_tool_failure_provenance.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.environment import RawObservation, ObservationNormalizer
from orchestrator.brain.trust import TrustLevel


def test_tool_failure_normalizes_to_tool_failure_trust():
    obs = RawObservation(
        observation_id="obs_1",
        source_tool="nmap",
        action_receipt_id="rec_1",
        raw_output="EXECUTION_ERROR: tool nmap failed",
        observed_at=0.0,
        target="10.0.0.5",
        observation_type="port_scan",
        is_tool_failure=True,
    )
    ev_list = ObservationNormalizer.normalize(obs)
    assert len(ev_list) == 1
    assert ev_list[0].trust_level == TrustLevel.TOOL_FAILURE
    assert "EXECUTION_ERROR" in ev_list[0].raw_content


def test_normal_observation_normalizes_to_tool_observation_trust():
    obs = RawObservation(
        observation_id="obs_2",
        source_tool="nmap",
        action_receipt_id="rec_2",
        raw_output="PORT   STATE SERVICE\n80/tcp open http\n",
        observed_at=0.0,
        target="10.0.0.5",
        observation_type="port_scan",
        is_tool_failure=False,  # default
    )
    ev_list = ObservationNormalizer.normalize(obs)
    # Two output lines -> two evidence items, both TOOL_OBSERVATION.
    assert len(ev_list) == 2
    for ev in ev_list:
        assert ev.trust_level == TrustLevel.TOOL_OBSERVATION
    assert "80/tcp" in ev_list[1].raw_content


def test_multiple_lines_each_get_correct_trust():
    obs_failure = RawObservation(
        observation_id="obs_3",
        source_tool="curl",
        action_receipt_id="rec_3",
        raw_output="Line 1\nLine 2\n",
        observed_at=0.0,
        target="10.0.0.5",
        observation_type="http_get",
        is_tool_failure=True,
    )
    ev_list = ObservationNormalizer.normalize(obs_failure)
    assert len(ev_list) == 2
    for ev in ev_list:
        assert ev.trust_level == TrustLevel.TOOL_FAILURE


def test_explicit_trust_level_override_still_works():
    """If caller explicitly passes trust_level, it should be respected."""
    from orchestrator.brain.trust import TrustLevel
    obs = RawObservation(
        observation_id="obs_4",
        source_tool="nmap",
        action_receipt_id="rec_4",
        raw_output="whatever",
        observed_at=0.0,
        target="10.0.0.5",
        observation_type="port_scan",
        is_tool_failure=True,  # would default to TOOL_FAILURE
    )
    # Override to TARGET_CONTROLLED
    ev_list = ObservationNormalizer.normalize(obs, trust_level=TrustLevel.TARGET_CONTROLLED)
    assert len(ev_list) == 1
    assert ev_list[0].trust_level == TrustLevel.TARGET_CONTROLLED


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("tool failure -> TOOL_FAILURE trust", test_tool_failure_normalizes_to_tool_failure_trust),
    ("normal -> TOOL_OBSERVATION trust", test_normal_observation_normalizes_to_tool_observation_trust),
    ("multi-line failure each gets trust", test_multiple_lines_each_get_correct_trust),
    ("explicit override respected", test_explicit_trust_level_override_still_works),
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
    print(f"TOOL FAILURE PROVENANCE: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_manual() else 0)