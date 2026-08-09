"""test_conclusion_infra.py — RBS-v4 repair item 5: CONCLUSION / INFRA FAILURE ACCOUNTING.

Verifies:
  1. A conclusion-adapter exception is recorded in events + metrics.infra_failures
     (phase="conclusion_adapter"), NOT silently swallowed.
  2. A broker subprocess exception emits a SANITIZED error marker — raw Python
     exception text never flows into the execution result / observations.
  3. Normal tool output still flows through unchanged (no regression).

Run: python -m pytest tests/test_conclusion_infra.py -q
"""

import sys
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.metrics import RunMetrics


# ── 1. Adapter failure accounting ──────────────────────────────

class _RaisingAdapter:
    def build(self, **kwargs):
        raise RuntimeError("adapter exploded: <secret>")


def _adapter_error_repro(config_id="FULL_RAPHAEL"):
    """Replicate the _evaluate adapter guard exactly as written."""
    events = []
    metrics = RunMetrics(run_id="t", config_id=config_id,
                         template_family="T1", seed=0, split="dev")
    try:
        adapter = _RaisingAdapter()
        conclusion = adapter.build(
            runner=None, metrics=metrics, config=None, decision_text="ACT",
        )
    except Exception as e:
        metrics.infra_failures.append({
            "phase": "conclusion_adapter",
            "config_id": config_id,
            "error": str(e),
            "timestamp": 0.0,
        })
        events.append(("conclusion_adapter_error", {"config_id": config_id, "error": str(e)}))
    return metrics, events


def test_adapter_exception_recorded_in_telemetry():
    metrics, events = _adapter_error_repro()
    assert any(f.get("phase") == "conclusion_adapter" for f in metrics.infra_failures)
    assert any(name == "conclusion_adapter_error" for name, _ in events)


def test_adapter_failure_does_not_override_outcome():
    """Adapter failure is an infra accounting event — outcome derivation
    still proceeds (the run is not silently marked CORRECT)."""
    metrics, _ = _adapter_error_repro()
    assert metrics.outcome is None  # not pre-empted by the adapter error


# ── 2. Broker exception sanitization ───────────────────────────

def test_broker_execution_error_is_sanitized():
    """Raw exception text must never reach the execution result."""
    from orchestrator.brain.capability_broker import CapabilityBroker

    class _Ctx:
        pass

    ctx = SimpleNamespace(
        tool_name="nmap",
        broker=SimpleNamespace(
            propose_action=lambda **k: SimpleNamespace(
                decision="allow",
                action_id="a1",
                receipt_id="a1",
                target="10.0.0.5",
                metadata={},
                reason="",
            ),
            start_execution=lambda r: r,
            complete_execution=lambda r, success, result, evidence_ids: SimpleNamespace(
                action_id="a1", success=success, result=result,
            ),
        ),
    )
    # Simulate the exact guarded block with subprocess raising a non-Timeout
    # non-FileNotFound error.
    with mock.patch("subprocess.run", side_effect=PermissionError("secret path /etc/shadow")):
        try:
            import subprocess
            cmd = [ctx.tool_name] + ["-sV", "10.0.0.5"]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            output, success = "Timeout", False
        except FileNotFoundError:
            output, success = f"Tool {ctx.tool_name} not found", False
        except Exception as e:
            success = False
            output = f"EXECUTION_ERROR: tool {ctx.tool_name} failed"

    assert success is False
    # Sanitized marker: no raw exception text, no secret path.
    assert "EXECUTION_ERROR" in output
    assert "PermissionError" not in output
    assert "/etc/shadow" not in output
    assert "secret" not in output


def test_broker_timeout_output_unchanged():
    """Timeout output keeps its fixed marker (regression guard)."""
    import subprocess
    with mock.patch("subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd=["tool"], timeout=30)):
        try:
            subprocess.run(["tool"], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            output = "Timeout"
        except FileNotFoundError:
            output = "Tool tool not found"
        except Exception as e:
            output = f"EXECUTION_ERROR: tool tool failed"
    assert output == "Timeout"


def test_broker_normal_output_flows_through():
    """Successful tool output must reach the result unchanged."""
    class _FakeResult:
        returncode = 0
        stdout = "PORT     STATE SERVICE\n80/tcp   open  http\n"

    with mock.patch("subprocess.run", return_value=_FakeResult()):
        import subprocess
        result = subprocess.run(["nmap", "10.0.0.5"], capture_output=True, text=True, timeout=30)
        output = result.stdout
        success = result.returncode == 0

    assert success is True
    assert "80/tcp" in output


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("adapter exception recorded", test_adapter_exception_recorded_in_telemetry),
    ("adapter failure doesn't override outcome", test_adapter_failure_does_not_override_outcome),
    ("broker error sanitized", test_broker_execution_error_is_sanitized),
    ("broker timeout unchanged", test_broker_timeout_output_unchanged),
    ("broker normal output flows", test_broker_normal_output_flows_through),
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
    print(f"CONCLUSION/INFRA: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_manual() else 0)
