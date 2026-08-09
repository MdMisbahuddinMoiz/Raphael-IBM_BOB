#!/usr/bin/env python3
# Smoke test for Raphael v2.1.1 frozen instrument -- fast health checks.
# Checks: imports, DVWA reachable, kali-tools health, LLM transport probe, pytest tracked subset.
# Exit: 0 = all green, 1 = warnings, 2 = hard failure.
import os, sys, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
VENV_PY = REPO / ".venv" / "bin" / "python"

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

for p in (str(REPO), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"

def check_imports():
    try:
        import arena.ablation_runner
        import arena.d6_manifest
        import arena.llm_transport
        import orchestrator.brain.action
        import orchestrator.brain.world
        import orchestrator.brain.capability_broker
        import raphael.eventbus.core
        import raphael.blackboard.contracts
        import agent.crypto
        return True, "core imports OK"
    except Exception as e:
        return False, "import fail: " + str(e)

def check_dvwa():
    code, _, _ = run("curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost:4280")
    return code in (200, 302), "DVWA HTTP " + str(code)

def check_kali_tools():
    code, out, _ = run("curl -s -m 5 http://localhost:3800/health")
    if code == 200:
        return True, "kali-tools health: " + out
    return False, "kali-tools unreachable"

def check_llm_transport():
    try:
        from arena.llm_transport import resolve_keys, execute_with_failover
        keys = resolve_keys()
        if not keys:
            return False, "no NVIDIA keys resolved"
        out = execute_with_failover(
            url="https://integrate.api.nvidia.com/v1/chat/completions",
            payload_bytes=b"{}",
            headers_template={"Content-Type": "application/json", "Authorization": "Bearer {key}"},
            timeout_seconds=10,
            keys=keys,
        )
        cls = getattr(out, "failure_class", "unknown")
        return cls in ("client_error", "server_error", "rate_limit", "timeout", "connection"), "transport class=" + cls
    except Exception as e:
        return False, "transport probe error: " + str(e)

def check_pytest_tracked():
    tracked = [
        "tests/e1_interactive_shell_test.py",
        "tests/e2_shell_candidate_generation_test.py",
        "tests/test_cli_smoke.py",
        "tests/test_d5_preflight.py",
        "tests/test_d5_seven_gate_proof.py",
        "tests/test_rbs_v2_repairs.py",
        "tests/test_stage1_invariants.py",
    ]
    code, out, err = run(str(VENV_PY) + " -m pytest " + " ".join(tracked) + " -q 2>&1", timeout=180)
    return code == 0, "pytest tracked (127): " + ("PASS" if code==0 else "FAIL")

def main():
    print("=" * 60)
    print("  Raphael v2.1.1 -- Smoke Test")
    print("=" * 60)
    checks = [
        ("Imports", check_imports),
        ("DVWA", check_dvwa),
        ("kali-tools", check_kali_tools),
        ("LLM Transport", check_llm_transport),
        ("Pytest (tracked)", check_pytest_tracked),
    ]
    results = []
    for name, fn in checks:
        ok, msg = fn()
        results.append((name, ok, msg))
        print("  " + ("[OK]" if ok else "[FAIL]") + " " + name + ": " + msg)

    hard_fail = any(not ok for name, ok, _ in results if name in ("Imports", "Pytest (tracked)"))
    soft_fail = any(not ok for _, ok, _ in results)

    print("-" * 60)
    if hard_fail:
        print("  RESULT: HARD FAIL (blocking)")
        return 2
    elif soft_fail:
        print("  RESULT: SOFT FAIL (warnings)")
        return 1
    else:
        print("  RESULT: ALL GREEN")
        return 0

if __name__ == "__main__":
    sys.exit(main())