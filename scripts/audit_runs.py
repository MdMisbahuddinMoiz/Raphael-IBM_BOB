#!/usr/bin/env python3
"""scripts.audit_runs — M10.2 evidence-backed metrics aggregation.

Reads durable run evidence::

    runs/<run_id>/evidence.jsonl

validates each run, and writes a deterministic ``metrics.json``.

Measurement-only: every number is traced to persisted ledger records.
Nothing is inferred from console output, filenames, or timestamps
(``generated_at`` is metadata only). The parser is intentionally
stdlib-only and does NOT import ``raphael_ibm_bob``: the JSONL schema is
the contract, so measurement stays valid even as implementation
details move.

Material assumptions (see also docs/metrics.md):

- A run is VALID only if its evidence parses, sequence numbers are
  dense from 1, at least one gate record exists, the last gate
  record's ``run_id`` matches the directory name, and every result
  artifact reference resolves on this machine. Anything else is
  INVALID with machine-readable reasons and is excluded from
  aggregates (never silently).
- The LAST gate record by sequence decides a run's verdict.
- ``plan_depth = 1 + <replanner evidence records>``; a replan is
  counted from ``producer="replanner"`` evidence, plan linkage from
  its payload. Successful-recovery claims use the explicit
  ``complete_with_replan_runs`` definition below.
- No mode/baseline provenance exists in current evidence, so mode
  aggregation is reported UNKNOWN with an empty breakdown.
- M10.3: runs carrying a `producer="benchmark"` evidence record with
  a string ``payload.mode`` aggregate under `by_mode` per mode value
  (e.g. baseline/raphael). Runs without one stay `mode="unknown"`
  and are excluded from `by_mode` (never relabeled). The top-level
  `mode` field remains `"unknown"`: the whole population has no
  single mode.
- Timestamps are never metric inputs.

CLI::

    python3 scripts/audit_runs.py --runs-root runs --output metrics.json

Exit 0 on success (invalid runs are findings, not fatal). Exit 2 on
fatal invocation errors (missing runs root, unwritable output).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "m10.2-v1"

KNOWN_KINDS = frozenset(
    {"request", "decision", "result", "evidence", "finding", "gate"}
)


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def _read_records(path: Path) -> Tuple[Optional[List[Dict[str, Any]]],
                                       List[str]]:
    """Parse JSONL; blank lines skipped. Returns (records, reasons)."""
    reasons: List[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"unreadable-evidence:{type(exc).__name__}"]
    records: List[Dict[str, Any]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            return None, [f"unparseable-line:{lineno}"]
        if not isinstance(obj, dict):
            return None, [f"non-object-record:{lineno}"]
        records.append(obj)
    return records, reasons


def validate_run(run_dir: Path) -> Tuple[bool, List[str],
                                         Optional[List[Dict[str, Any]]]]:
    """Validate one run directory. Returns (valid, reasons, records)."""
    reasons: List[str] = []
    if not run_dir.is_dir():
        return False, ["not-a-directory"], None
    ledger_path = run_dir / "evidence.jsonl"
    if not ledger_path.is_file():
        return False, ["missing-evidence-jsonl"], None
    records, parse_reasons = _read_records(ledger_path)
    reasons.extend(parse_reasons)
    if records is None:
        return False, reasons, None
    if not records:
        return False, ["empty-evidence"], None
    for idx, rec in enumerate(records, start=1):
        kind = rec.get("kind")
        if kind not in KNOWN_KINDS:
            reasons.append(f"unknown-or-missing-kind:line-{idx}")
        seq = rec.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) \
                or seq < 1:
            reasons.append(f"bad-seq:line-{idx}")
    if reasons:
        return False, sorted(set(reasons)), None
    seqs = [rec["seq"] for rec in records]
    if sorted(seqs) != list(range(1, len(records) + 1)):
        return False, ["non-dense-sequence"], None
    gates = [r for r in records if r.get("kind") == "gate"]
    if not gates:
        return False, ["missing-gate-record"], None
    last_gate = max(gates, key=lambda r: r["seq"])
    if last_gate.get("run_id") != run_dir.name:
        reasons.append("run-id-mismatch")
    for rec in records:
        if rec.get("kind") != "result":
            continue
        ref = rec.get("artifact_ref", "")
        if not ref or not Path(ref).is_file():
            reasons.append(f"broken-artifact-reference:seq-{rec['seq']}")
    if reasons:
        return False, sorted(set(reasons)), None
    return True, [], records


# -----------------------------------------------------------------------------
# Per-run metrics (valid runs only)
# -----------------------------------------------------------------------------

def _by_kind(records: List[Dict[str, Any]],
             kind: str) -> List[Dict[str, Any]]:
    return [r for r in records if r.get("kind") == kind]


def run_mode(records: List[Dict[str, Any]]) -> Optional[str]:
    """Extract benchmark-mode provenance from a run's records.

    M10.3: the harness records one `producer="benchmark"` evidence
    record carrying a string ``payload.mode``. The FIRST such record
    by sequence wins. Runs without one keep ``None`` (reported as
    ``"unknown"``): mode is never inferred from directory names,
    timestamps, or narrative text.
    """
    for rec in sorted(records, key=lambda r: r.get("seq", 0)):
        if rec.get("kind") != "evidence":
            continue
        if rec.get("producer") != "benchmark":
            continue
        payload = rec.get("payload", {})
        if isinstance(payload, dict) and isinstance(
                payload.get("mode"), str):
            return payload["mode"]
    return None


def per_run_metrics(run_id: str,
                    records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive one run's metrics from its validated records."""
    requests = _by_kind(records, "request")
    decisions = _by_kind(records, "decision")
    results = _by_kind(records, "result")
    evidences = _by_kind(records, "evidence")
    findings = _by_kind(records, "finding")
    gates = _by_kind(records, "gate")

    requested_by_cap: Dict[str, int] = {}
    for r in requests:
        cap = str(r.get("capability", "unknown"))
        requested_by_cap[cap] = requested_by_cap.get(cap, 0) + 1

    allows = sum(1 for d in decisions if d.get("decision") == "allow")
    denies = sum(1 for d in decisions if d.get("decision") == "deny")

    cap_by_request = {r.get("seq"): str(r.get("capability", "unknown"))
                      for r in requests}
    executed_by_cap: Dict[str, int] = {}
    for r in results:
        cap = cap_by_request.get(r.get("request_seq"), "unknown")
        executed_by_cap[cap] = executed_by_cap.get(cap, 0) + 1

    allowed_request_seqs = {d.get("request_seq") for d in decisions
                            if d.get("decision") == "allow"}
    success_by_request = {r.get("request_seq"): r.get("success") is True
                          for r in results}
    successful_run_tests = sum(
        1 for r in requests
        if r.get("capability") == "run_test"
        and r.get("seq") in allowed_request_seqs
        and success_by_request.get(r.get("seq"), False))

    replans = sum(1 for e in evidences
                  if e.get("producer") == "replanner")

    terminal: Dict[str, str] = {}
    for f in sorted(findings, key=lambda r: r["seq"]):
        terminal[str(f.get("finding_id"))] = str(f.get("state"))
    terminal_counts: Dict[str, int] = {}
    for state in terminal.values():
        terminal_counts[state] = terminal_counts.get(state, 0) + 1

    last_gate = max(gates, key=lambda r: r["seq"])
    verdict = str(last_gate.get("decision", "unknown"))

    artifact_refs = [r.get("artifact_ref", "") for r in results]
    resolved = sum(1 for ref in artifact_refs
                   if ref and Path(ref).is_file())

    return {
        "run_id": run_id,
        "mission_id": str(last_gate.get("mission_id", "unknown")),
        "mode": run_mode(records) or "unknown",
        "verdict": verdict,
        "record_count": len(records),
        "counts_by_kind": {
            kind: len(_by_kind(records, kind))
            for kind in sorted(KNOWN_KINDS)
        },
        "requested": len(requests),
        "requested_by_capability": dict(sorted(requested_by_cap.items())),
        "allows": allows,
        "denies": denies,
        "executed": len(results),
        "executed_by_capability": dict(sorted(executed_by_cap.items())),
        "successful_run_test_executions": successful_run_tests,
        "replans": replans,
        "plan_depth": 1 + replans,
        "findings": len(terminal),
        "finding_terminal_states": dict(sorted(terminal_counts.items())),
        "finding_transitions": len(findings),
        "artifact_refs": len(artifact_refs),
        "artifact_refs_resolved": resolved,
        "gate_present": True,
    }


# -----------------------------------------------------------------------------
# Aggregation (deterministic: sorted inputs, sorted keys at dump time)
# -----------------------------------------------------------------------------

def aggregate(valid: List[Tuple[str, Dict[str, Any]]],
                _nested: bool = False) -> Dict[str, Any]:
    """Aggregate per-run metric dicts (already sorted by run_id)."""
    complete = sum(1 for _, m in valid if m["verdict"] == "complete")
    refuse = sum(1 for _, m in valid if m["verdict"] == "refuse")
    n = len(valid)
    requested: Dict[str, int] = {}
    executed: Dict[str, int] = {}
    terminal: Dict[str, int] = {}
    gate_decisions: Dict[str, int] = {}
    for _, m in valid:
        for cap, c in m["requested_by_capability"].items():
            requested[cap] = requested.get(cap, 0) + c
        for cap, c in m["executed_by_capability"].items():
            executed[cap] = executed.get(cap, 0) + c
        for state, c in m["finding_terminal_states"].items():
            terminal[state] = terminal.get(state, 0) + c
        gate_decisions[m["verdict"]] = \
            gate_decisions.get(m["verdict"], 0) + 1
    replans = [m["replans"] for _, m in valid]
    return {
        "valid_runs": n,
        "complete_runs": complete,
        "refused_runs": refuse,
        "completion_rate": (complete / n) if n else None,
        "refusal_rate": (refuse / n) if n else None,
        "complete_with_replan_runs": sum(
            1 for _, m in valid
            if m["verdict"] == "complete" and m["replans"] > 0),
        "refused_with_replan_runs": sum(
            1 for _, m in valid
            if m["verdict"] == "refuse" and m["replans"] > 0),
        "average_ledger_records": (
            sum(m["record_count"] for _, m in valid) / n) if n else None,
        "average_replans": (sum(replans) / n) if n else None,
        "max_replans_observed": max(replans) if replans else 0,
        "policy_allows": sum(m["allows"] for _, m in valid),
        "policy_denies": sum(m["denies"] for _, m in valid),
        "requested_by_capability": dict(sorted(requested.items())),
        "executed_by_capability": dict(sorted(executed.items())),
        "finding_terminal_states": dict(sorted(terminal.items())),
        "finding_transitions": sum(
            m["finding_transitions"] for _, m in valid),
        "distinct_findings": sum(m["findings"] for _, m in valid),
        "gate_decisions": dict(sorted(gate_decisions.items())),
        "artifact_refs": sum(m["artifact_refs"] for _, m in valid),
        "artifact_refs_resolved": sum(
            m["artifact_refs_resolved"] for _, m in valid),
        "successful_run_test_executions": sum(
            m["successful_run_test_executions"] for _, m in valid),
        "mode": "unknown",
        "by_mode": {} if _nested else {
            mode: aggregate([(rid, m) for rid, m in valid
                             if m["mode"] == mode], _nested=True)
            for mode in sorted({m["mode"] for _, m in valid
                               if m["mode"] != "unknown"})
        },
    }


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

def audit_runs(runs_root: Path) -> Dict[str, Any]:
    """Validate + aggregate every run directory under runs_root."""
    names = sorted(p.name for p in runs_root.iterdir() if p.is_dir())
    run_entries: List[Dict[str, Any]] = []
    validation: List[Dict[str, Any]] = []
    valid: List[Tuple[str, Dict[str, Any]]] = []
    invalid = 0
    for name in names:
        ok, reasons, records = validate_run(runs_root / name)
        validation.append({
            "run_id": name,
            "valid": ok,
            "reasons": sorted(reasons),
        })
        if not ok or records is None:
            invalid += 1
            continue
        metrics = per_run_metrics(name, records)
        valid.append((name, metrics))
        run_entries.append(metrics)
    valid.sort(key=lambda t: t[0])
    run_entries.sort(key=lambda m: m["run_id"])
    return {
        "run_count": len(names),
        "valid_run_count": len(valid),
        "invalid_run_count": invalid,
        "metrics": aggregate(valid),
        "runs": run_entries,
        "validation": validation,
    }


# -----------------------------------------------------------------------------
# Seal verification (T1-3; single shared implementation lives in
# raphael_ibm_bob.seal and is imported lazily so the default
# aggregation path stays stdlib-only)
# -----------------------------------------------------------------------------

def _verify_seal_cli(run_dir: Path) -> int:
    if not run_dir.is_dir():
        print(f"error: run directory not found: {run_dir}",
              file=sys.stderr)
        return 2
    try:
        from raphael_ibm_bob.seal import verify_seal
    except ImportError as exc:
        print(f"error: cannot load seal module: {exc}", file=sys.stderr)
        return 2
    ok, reason = verify_seal(run_dir)
    if ok:
        print(f"seal-ok {run_dir.name}")
        return 0
    print(f"seal-invalid {run_dir.name} {reason}")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate RAPHAEL durable run evidence "
                    "into metrics.json (M10.2, measurement-only).")
    parser.add_argument("--runs-root", default="runs",
                        help="directory containing <run_id>/ run dirs")
    parser.add_argument("--output", default="metrics.json",
                        help="where to write the metrics document")
    parser.add_argument("--verify-seal", default=None, metavar="RUN_DIR",
                        help="verify the T1-3 evidence seal of one run "
                             "directory instead of aggregating")
    args = parser.parse_args(argv)

    if args.verify_seal is not None:
        return _verify_seal_cli(Path(args.verify_seal))

    runs_root = Path(args.runs_root)
    if not runs_root.is_dir():
        print(f"error: runs root not found: {runs_root}", file=sys.stderr)
        return 2

    report = audit_runs(runs_root)
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "run_root": str(runs_root),
        **report,
    }
    try:
        Path(args.output).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 2

    print(f"runs={report['run_count']} "
          f"valid={report['valid_run_count']} "
          f"invalid={report['invalid_run_count']} "
          f"-> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
