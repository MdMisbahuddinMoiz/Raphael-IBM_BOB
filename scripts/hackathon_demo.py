#!/usr/bin/env python3
"""Canonical operator driver for the Raphael x IBM BOB hackathon demo.

This driver talks ONLY to the real product HTTP API (the same endpoints the
operator UI uses):

    GET  /                     liveness
    GET  /mode                 product mode
    POST /mode                 set TESTING/HTB
    GET  /vpn/status           VPN state
    GET  /htb/target           declared TargetProfile
    POST /htb/target           declare the authorized target
    POST /sessions             create a mission session
    POST /operations/start     run the governed network mission

It then READS the persisted run record (``runs/<run_id>/harness.json``) and
the append-only ledger (``runs/<run_id>/evidence.jsonl``).

It never:
    * bypasses the HTTP server,
    * bypasses the Broker/Policy boundary,
    * calls the network mediator directly,
    * constructs a verdict or fabricates evidence.

The QualityGate verdict is read from the persisted ledger record; this driver
can only report it.

Modes: ``status``, ``preflight``, ``success``, ``refuse``.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raphael_ibm_bob.http.views.decision_trace import (  # noqa: E402
    gate_breakdown,
)

BASE_URL = os.environ.get("RAPHAEL_BASE_URL", "http://127.0.0.1:8787")
RUNS_ROOT = Path(os.environ.get("RAPHAEL_RUNS_ROOT", REPO_ROOT / "runs"))
TARGET_HOST = os.environ.get("RAPHAEL_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.environ.get("RAPHAEL_TARGET_PORT", "8080"))
REQUEST_PATH = os.environ.get("RAPHAEL_REQUEST_PATH", "/")
PROBE_PATH = os.environ.get("RAPHAEL_PROBE_PATH", "/index.html")
DECOY_PATH = os.environ.get("RAPHAEL_DECOY_PATH", "/raphael-decoy-404")
MISSION_ID = os.environ.get("RAPHAEL_MISSION_ID", "M-HTB-001")

READY = "READY"
NOT_READY = "NOT READY"
OPTIONAL = "OPTIONAL"


# --------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# --------------------------------------------------------------------------
def _http(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        status = exc.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def server_up() -> bool:
    try:
        status, _ = _http("GET", "/", timeout=5)
        return status == 200
    except Exception:
        return False


def tcp_reachable(host: str, port: int, timeout=3.0) -> bool:
    """Single-host reachability probe of a KNOWN target (never a scan)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def stage(n: int, label: str) -> None:
    print(f"[{n}] {label}")


def kv(label: str, value) -> None:
    print(f"     {label}: {value}")


def _run_dir(run_id: str) -> Path:
    return RUNS_ROOT / run_id


def read_run(run_id: str):
    run_dir = _run_dir(run_id)
    harness = json.loads((run_dir / "harness.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in
               (run_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    return harness, records


def last_gate(records):
    gates = [r for r in records if r.get("kind") == "gate"]
    return gates[-1] if gates else None


def blocked_verdict(verdict: str):
    """Exit code for a completed demo: 0 iff the objective was met."""
    raise SystemExit(0 if verdict == "complete" else 1)


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
def preflight(argv) -> int:
    print("RAPHAEL x IBM BOB - demo preflight")
    print("=" * 52)
    checks = []

    py = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python version", f"{py} (>= 3.11)",
                   READY if py_ok else NOT_READY))

    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=10)
        revision = rev.stdout.strip() or "(unknown)"
    except Exception:
        revision = "(git unavailable)"
    checks.append(("Repository revision", revision, OPTIONAL))

    up = server_up()
    checks.append((f"Server {BASE_URL}", "reachable" if up else "unreachable",
                   READY if up else NOT_READY))

    mode = vpn = target = None
    if up:
        _, mode = _http("GET", "/mode")
        _, vpn = _http("GET", "/vpn/status")
        _, target = _http("GET", "/htb/target")

    mode_ok = isinstance(mode, dict) and mode.get("mode") == "testing" \
        and mode.get("testing_profile") == "htb"
    checks.append(("Product mode TESTING/HTB",
                   mode if isinstance(mode, dict) else "(server down)",
                   READY if mode_ok else NOT_READY))

    vpn_state = (vpn or {}).get("state", "unknown") \
        if isinstance(vpn, dict) else "unknown"
    # VPN is only needed for external HTB targets.
    vpn_needed = TARGET_HOST not in ("127.0.0.1", "localhost")
    checks.append(("VPN (OpenVPN)",
                   f"state={vpn_state}",
                   READY if vpn_state == "connected"
                   else (NOT_READY if vpn_needed else OPTIONAL)))

    openvpn = "present"
    if not (Path("/usr/sbin/openvpn").exists()
            or _which("openvpn")):
        openvpn = "absent"
    checks.append(("OpenVPN binary", openvpn,
                   READY if openvpn == "present"
                   else (NOT_READY if vpn_needed else OPTIONAL)))

    target_ok = tcp_reachable(TARGET_HOST, TARGET_PORT)
    checks.append((f"Target {TARGET_HOST}:{TARGET_PORT}",
                   "reachable" if target_ok else "unreachable",
                   READY if target_ok else NOT_READY))

    declared = isinstance(target, dict) and target.get("configured")
    checks.append(("TargetProfile declared",
                   target.get("target", {}).get("locator") if declared
                   else "none", OPTIONAL))

    env_vars = ["RAPHAEL_OPENVPN_BIN"]
    for name in env_vars:
        checks.append((f"env {name}", os.environ.get(name, "(unset)"), OPTIONAL))

    for label, value, state in checks:
        print(f"[{state:>9}] {label}: {value}")

    ready = all(state != NOT_READY for _, _, state in checks)
    print("=" * 52)
    if ready:
        print("PREFLIGHT: READY - the success demo can run.")
    else:
        print("PREFLIGHT: NOT READY - resolve the NOT READY items above.")
    return 0 if ready else 2


def _which(binary: str):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(d) / binary
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------
def status(argv) -> int:
    print("RAPHAEL x IBM BOB - demo status")
    print("=" * 52)
    print(f"Server {BASE_URL}: {'up' if server_up() else 'down'}")
    if server_up():
        _, mode = _http("GET", "/mode")
        _, vpn = _http("GET", "/vpn/status")
        _, target = _http("GET", "/htb/target")
        print(f"Mode: {mode}")
        print(f"VPN: {vpn}")
        print(f"Target: {target}")
    print(f"Target endpoint: http://{TARGET_HOST}:{TARGET_PORT}"
          f" (reachable={tcp_reachable(TARGET_HOST, TARGET_PORT)})")
    print("-" * 52)
    print("Recent runs (runs/<run_id>):")
    if RUNS_ROOT.is_dir():
        runs = sorted((p for p in RUNS_ROOT.iterdir() if p.is_dir()),
                      reverse=True)[:10]
        for p in runs:
            h = p / "harness.json"
            if not h.is_file():
                continue
            try:
                d = json.loads(h.read_text(encoding="utf-8"))
            except ValueError:
                continue
            print(f"  {p.name}  state={d.get('state'):<9} "
                  f"gate={d.get('gate_verdict')}  "
                  f"mission={d.get('mission', {}).get('mission_id')}")
    else:
        print("  (no runs/ directory yet)")
    return 0


# --------------------------------------------------------------------------
# Governed run
# --------------------------------------------------------------------------
def _make_workspace() -> Path:
    import tempfile
    ws = Path(tempfile.mkdtemp(prefix="raphael_demo_ws_"))
    (ws / "test_ok.py").write_text(
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertTrue(True)\n", encoding="utf-8")
    return ws


def _configure_and_run(host: str, port: int, *, expect_reachable: bool) -> int:
    label = "SUCCESS" if expect_reachable else "REFUSAL"
    print(f"RAPHAEL x IBM BOB - DEMO {label}")
    print("=" * 60)

    if not server_up():
        print(f"[{NOT_READY}] server {BASE_URL} is not reachable.")
        print("    start it with:")
        print("    RAPHAEL_OPENVPN_BIN=/usr/sbin/openvpn PYTHONPATH=. \\")
        print("      python3 -m raphael_ibm_bob.http --host 127.0.0.1 "
              "--port 8787")
        return 2

    ws = _make_workspace()

    stage(1, "Environment")
    kv("repo", str(REPO_ROOT))
    kv("server", BASE_URL)
    kv("workspace", str(ws))

    stage(2, "VPN")
    _, vpn = _http("GET", "/vpn/status")
    kv("state", (vpn or {}).get("state") if isinstance(vpn, dict) else vpn)

    stage(3, "Mode")
    code, mode = _http("POST", "/mode",
                       {"mode": "testing", "testing_profile": "htb"})
    kv("mode", mode)

    stage(4, "Target")
    code, target = _http("POST", "/htb/target", {
        "platform": "htb", "locator": host, "allowed_ports": [port],
        "allowed_protocols": ["http"], "scope": host,
        "authorization_ref": "RAPHAEL-HACKATHON-DEMO", "mission_id": MISSION_ID})
    if not (isinstance(target, dict) and target.get("configured")):
        print(f"     target declaration failed: {code} {target}")
        return 2
    kv("locator", host)
    kv("port", port)
    kv("target_id", target["target"].get("target_id"))
    kv("reachable", tcp_reachable(host, port))

    stage(5, "Mission")
    mission = {
        "mission_id": MISSION_ID,
        "description": "Governed HTTP operation against an authorized target",
        "scope": "",
        "criteria": ["obtain and verify the flag"],
        "problem": {
            "symptom_target": host, "request_path": REQUEST_PATH,
            "probe_path": PROBE_PATH, "decoy_path": DECOY_PATH,
            "verification_tests": ["test_ok.py"],
        },
    }
    code, sess = _http("POST", "/sessions", {
        "workspace_root": str(ws), "project_name": "hackathon-demo",
        "mission": mission})
    if not (isinstance(sess, dict) and sess.get("session_id")):
        print(f"     session creation failed: {code} {sess}")
        return 2
    session_id = sess["session_id"]
    kv("mission_id", MISSION_ID)
    kv("session_id", session_id)
    kv("request_path", REQUEST_PATH)
    kv("probe_path", PROBE_PATH)

    stage(6, "Governed execution")
    print("     TESTING/HTB -> TargetProfile -> NETWORK_HTTP_REQUEST -> "
          "Policy -> Runtime/Broker")
    code, resp = _http("POST", "/operations/start", {"session_id": session_id})
    html = resp if isinstance(resp, str) else json.dumps(resp)
    run_id = _extract_run_id(html)
    if not run_id:
        print(f"     start failed: {code}")
        print(f"     {html[:300]}")
        return 2
    kv("run_id", run_id)
    harness, records = read_run(run_id)

    stage(7, "Evidence")
    producers = sorted({r.get("producer") for r in records
                        if r.get("kind") == "evidence"})
    kv("ledger", f"runs/{run_id}/evidence.jsonl")
    kv("producers", producers)
    for r in records:
        if r.get("kind") == "request":
            kv("request", f"{r.get('capability')} -> {r.get('target')}")
    for r in records:
        if r.get("kind") == "evidence" and r.get("producer") == "network":
            nr = (r.get("payload") or {}).get("network_result") or {}
            kv("network", f"{nr.get('path')} state={nr.get('state')} "
                          f"status={nr.get('status_code')} "
                          f"bytes={nr.get('response_bytes')}")
    gate = last_gate(records)

    stage(8, "Verification / probe")
    for r in records:
        if r.get("kind") == "evidence" and r.get("producer") == "probe":
            p = r.get("payload") or {}
            kv("probe", f"allowed={p.get('allowed')} "
                        f"invariant={p.get('invariant')} "
                        f"status={p.get('status_code')} "
                        f"bytes={p.get('response_bytes')}")
    for r in records:
        if r.get("kind") == "evidence" and r.get("producer") == "regression":
            p = r.get("payload") or {}
            kv("regression", f"test={p.get('test')} "
                             f"returncode={p.get('returncode')} "
                             f"result={p.get('result')}")

    stage(9, "QualityGate")
    if gate is None:
        print("     no gate record persisted")
        return 2
    passed, failed, unknown, names = gate_breakdown(gate)
    for cond in names:
        mark = "*" if cond in passed else ("x" if cond in failed else "?")
        print(f"     [{mark}] {cond}")
    kv("failed", failed)
    kv("unknown", unknown)
    kv("reasons", gate.get("reasons") or [])

    stage(10, "Final verdict")
    verdict = (harness.get("gate_verdict") or gate.get("decision") or "").lower()
    count = f"{len(passed)}/{len(names)}"
    kv("state", harness.get("state"))
    kv("conditions", count)
    kv("verdict", verdict.upper())

    if expect_reachable:
        print("RESULT:", "7/7 COMPLETE" if verdict == "complete"
              else "REFUSE (expected COMPLETE)")
        return 0 if verdict == "complete" else 1
    else:
        print("RESULT:", "REFUSE (honest: failure was not reported as "
              "COMPLETE)" if verdict == "refuse"
              else f"UNEXPECTED {verdict.upper()}")
        return 0 if verdict == "refuse" else 1


def _extract_run_id(text: str):
    import re
    m = re.search(r"/operations/([0-9T]+_[0-9a-f]+)", text or "")
    return m.group(1) if m else None


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def success(argv) -> int:
    if not tcp_reachable(TARGET_HOST, TARGET_PORT):
        print(f"[{NOT_READY}] target http://{TARGET_HOST}:{TARGET_PORT} is "
              f"not reachable.")
        print("    Boot the authorized HTTP target (see docs/HACKATHON_DEMO.md)")
        print("    or override RAPHAEL_TARGET_HOST / RAPHAEL_TARGET_PORT.")
        return 2
    return _configure_and_run(TARGET_HOST, TARGET_PORT, expect_reachable=True)


def refuse(argv) -> int:
    # A real, deterministic refusal: an authorized-but-unavailable service.
    port = _free_port()
    print(f"(refusal demo: authorized target 127.0.0.1:{port} is not serving)")
    return _configure_and_run("127.0.0.1", port, expect_reachable=False)


MODES = {
    "status": status,
    "preflight": preflight,
    "success": success,
    "refuse": refuse,
}


def main(argv) -> int:
    mode = (argv[1] if len(argv) > 1 else "status").lstrip("-")
    fn = MODES.get(mode)
    if fn is None:
        print(f"unknown mode: {mode!r}")
        print("modes: " + ", ".join(sorted(MODES)))
        return 2
    return fn(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
