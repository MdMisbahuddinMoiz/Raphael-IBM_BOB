#!/usr/bin/env python3
"""Export a persisted run into a machine-readable demo evidence bundle.

    python3 scripts/demo_export.py <run_id> <out_dir>

Reads (never modifies) ``runs/<run_id>/`` and writes:

    <out_dir>/run.json        the persisted Harness run record
    <out_dir>/ledger.jsonl    an exact copy of the append-only ledger
    <out_dir>/gate.json       the persisted QualityGate record
    <out_dir>/summary.json    derived, reproducible summary (A-G + chain)
    <out_dir>/transcript.txt  human-readable transcript of the chain

The bundle is reproducible from the run: re-running reproduces byte-for-byte
summary.json/transcript.txt for the same ledger.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = Path(__import__("os").environ.get("RAPHAEL_RUNS_ROOT",
                                             REPO_ROOT / "runs"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raphael_ibm_bob.http.views.decision_trace import (  # noqa: E402
    gate_breakdown,
)


def export(run_id: str, out_dir: Path) -> Path:
    run_dir = RUNS_ROOT / run_id
    if not run_dir.is_dir():
        raise SystemExit(f"no such run: {run_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    harness = json.loads((run_dir / "harness.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in
               (run_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]

    # 1. exact copies (original ledger untouched).
    (out_dir / "run.json").write_text(
        json.dumps(harness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copyfile(run_dir / "evidence.jsonl", out_dir / "ledger.jsonl")

    gates = [r for r in records if r.get("kind") == "gate"]
    gate = gates[-1] if gates else None
    (out_dir / "gate.json").write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    passed, failed, unknown, names = gate_breakdown(gate)
    requests = [
        {"seq": r.get("seq"), "capability": r.get("capability"),
         "target": r.get("target")}
        for r in records if r.get("kind") == "request"]
    network = []
    probe = None
    regression = None
    producers = []
    for r in records:
        if r.get("kind") != "evidence":
            continue
        producers.append(r.get("producer"))
        if r.get("producer") == "network":
            nr = (r.get("payload") or {}).get("network_result") or {}
            network.append({
                "path": nr.get("path"), "state": nr.get("state"),
                "status_code": nr.get("status_code"),
                "response_bytes": nr.get("response_bytes"),
                "invocation_id": nr.get("invocation_id")})
        if r.get("producer") == "probe":
            probe = r.get("payload")
        if r.get("producer") == "regression":
            regression = r.get("payload")

    summary = {
        "run_id": run_id,
        "mission_id": (harness.get("mission") or {}).get("mission_id"),
        "state": harness.get("state"),
        "gate_verdict": harness.get("gate_verdict"),
        "conditions": {
            "passed": passed, "failed": failed, "unknown": unknown,
            "names": list(names), "count": f"{len(passed)}/{len(names)}"},
        "producers": sorted({p for p in producers if p}),
        "requests": requests,
        "network_observations": network,
        "probe": probe,
        "regression": regression,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"RAPHAEL x IBM BOB - demo evidence transcript",
        f"run_id      : {run_id}",
        f"mission_id  : {summary['mission_id']}",
        f"state       : {summary['state']}",
        f"verdict     : {summary['gate_verdict']}",
        f"conditions  : {summary['conditions']['count']}",
        "",
        "Governed requests (order):",
    ]
    for r in requests:
        lines.append(f"  #{r['seq']:<3} {r['capability']:<22} {r['target']}")
    lines.append("")
    lines.append("Network observations:")
    for n in network:
        lines.append(f"  {n['path']:<16} state={n['state']:<8} "
                     f"status={n['status_code']} bytes={n['response_bytes']}")
    lines.append("")
    lines.append("Independent probe:")
    lines.append(f"  {json.dumps(probe, sort_keys=True)}")
    lines.append("")
    lines.append("Regression:")
    lines.append(f"  {json.dumps(regression, sort_keys=True)}")
    lines.append("")
    lines.append("QualityGate conditions:")
    for cond in names:
        mark = "PASS" if cond in passed else ("FAIL" if cond in failed
                                              else "UNKNOWN")
        lines.append(f"  [{mark:>7}] {cond}")
    lines.append("")
    lines.append(f"FINAL: {summary['gate_verdict'].upper()} "
                 f"({summary['conditions']['count']})")
    (out_dir / "transcript.txt").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
    return out_dir


def main(argv):
    if len(argv) != 3:
        print("usage: python3 scripts/demo_export.py <run_id> <out_dir>")
        return 2
    export(argv[1], Path(argv[2]))
    print(f"exported {argv[1]} -> {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
