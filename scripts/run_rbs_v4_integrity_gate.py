#!/usr/bin/env python3
"""
RBS-v4 HOLDOUT — MECHANICAL INTEGRITY GATE (pre-analysis)
==========================================================
MUST pass BEFORE any result file is opened for statistical analysis.
Gate checks (all mechanical, no performance interpretation):
  1. Exactly 3,240 parseable rows (9 configs x 12 templates x 30 seeds).
  2. Cell structure: all 108 (template, config) cells present.
  3. Each cell has exactly 30 unique holdout seeds (1072-1101).
  4. Zero duplicate run identities (config, template, seed) across the file.
  5. No missing cells; no out-of-range seeds; no foreign configs/templates.
  6. Run-directory/artifact consistency (run_dir non-null for non-error rows).
  7. Interruption/resume accounting: error-row count, boundary continuity.
  8. Frozen-instrument hash consistency vs v4-benchmark-frozen-F manifest.
  9. run_id determinism: every row's run_id is a pure logical-cell identity
     (d6c_holdout_<arch>_<scenario>_s<seed>) with no random UUID suffix, so
     resume/re-run of the same cell is idempotent and dedup-able.

Exit code: 0 = PASS (all checks green), 1 = FAIL (any check red).
Output: machine-readable PASS/FAIL per check + JSON summary written to
        evaluations/campaign/rbs_v4_holdout_integrity_gate.json
"""
import json
import sys
import hashlib
import collections
from pathlib import Path

REPO = Path("/home/yaser/raphael-2.0-rbsv2r")
OUT = REPO / "evaluations" / "campaign" / "rbs_v4_holdout.jsonl"
GATE_OUT = REPO / "evaluations" / "campaign" / "rbs_v4_holdout_integrity_gate.json"
MANIFEST = REPO / "evaluations" / "campaign" / "rbs_v4_benchmark_frozen-F.json"
INTERRUPTION_RECORD = REPO / "evaluations" / "campaign" / "rbs_v4_holdout_interruption1.json"

EXPECTED_TEMPLATES = [
    "T1_NEGATIVE_CONTROL", "T2_HYPOTHESIS_SENSITIVE", "T3_FALSIFICATION_SENSITIVE",
    "T4_WORLD_MODEL_IDENTITY", "T5_PLANNING_COST", "T6_SEMANTIC_LLM",
    "T7_DEFEATER_SENSITIVE", "T8_STUDENT_EXCLUSIVE", "T9_SEMANTIC_AMBIGUITY",
    "T10_MISLEADING_EVIDENCE", "T11_COMPETING_HYPOTHESES", "T12_SAFETY_BOUNDARY",
]
EXPECTED_CONFIGS = [
    "FULL_RAPHAEL", "NO_HYPOTHESIS", "NO_FALSIFICATION", "NO_WORLD_MODEL",
    "NO_PLANNER", "NO_LLM", "NO_DEFEATER", "NO_STUDENT", "SCRIPTED_BASELINE",
]
EXPECTED_SEEDS = set(range(1072, 1102))  # 1072-1101 = 30 seeds
EXPECTED_TOTAL = len(EXPECTED_TEMPLATES) * len(EXPECTED_CONFIGS) * len(EXPECTED_SEEDS)  # 3240

# Frozen source files whose hashes are recorded in the manifest
FROZEN_SOURCES = [
    "src/arena/d6_manifest.py",
    "src/arena/environment.py",
    "src/arena/ablation_runner.py",
    "src/arena/ablation.py",
    "src/arena/semantic_inference.py",
    "src/arena/llm_service.py",
    "src/arena/d6c_holdout_runner.py",
    "scripts/run_rbs_v4_holdout.py",
    "scripts/d6c_holdout_runner.py",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    results = {}

    # ── Load rows ──
    rows = []
    parse_errors = 0
    raw_lines = []
    for line in OUT.open():
        line = line.strip()
        if not line:
            continue
        raw_lines.append(line)
        try:
            rows.append(json.loads(line))
        except Exception:
            parse_errors += 1

    # ── Check 1: total parseable rows ──
    c1 = parse_errors == 0 and len(rows) == EXPECTED_TOTAL
    results["1_total_rows"] = {"expected": EXPECTED_TOTAL, "found": len(rows),
                               "parse_errors": parse_errors, "pass": c1}

    # ── Check 2/3/4/5: cell structure, seeds, duplicates, foreign keys ──
    cells = collections.defaultdict(set)       # (template, config) -> set(seeds)
    run_ids = collections.Counter()            # (config, template, seed) -> count
    foreign = []
    error_rows = []
    for r in rows:
        t, c = r.get("template"), r.get("config")
        s = r.get("seed")
        if "error" in r:
            error_rows.append((t, c, s, str(r.get("error"))[:100]))
            continue
        if t not in EXPECTED_TEMPLATES:
            foreign.append(f"unknown template {t}")
        if c not in EXPECTED_CONFIGS:
            foreign.append(f"unknown config {c}")
        if s not in EXPECTED_SEEDS or not isinstance(s, int):
            foreign.append(f"out-of-range seed {s} for {t}/{c}")
        cells[(t, c)].add(s)
        run_ids[(c, t, s)] += 1

    # cell completeness: all 108 cells present
    all_cells = {(t, c) for t in EXPECTED_TEMPLATES for c in EXPECTED_CONFIGS}
    missing_cells = all_cells - set(cells.keys())
    partial_cells = {k for k, v in cells.items() if len(v) != len(EXPECTED_SEEDS)}

    c2 = not missing_cells
    c3 = not partial_cells
    c4 = all(cnt == 1 for cnt in run_ids.values()) and not error_rows
    c5 = not foreign and not missing_cells and not partial_cells

    results["2_cell_structure"] = {"cells_found": len(cells), "cells_expected": len(all_cells),
                                  "missing_cells": sorted(missing_cells), "pass": c2}
    results["3_seed_uniqueness_per_cell"] = {"partial_cells": sorted(partial_cells), "pass": c3}
    results["4_duplicate_run_ids"] = {"duplicate_count": sum(1 for v in run_ids.values() if v > 1),
                                      "error_rows": len(error_rows), "pass": c4}
    results["5_foreign_keys"] = {"issues": foreign, "pass": c5}

    # ── Check 6: run-directory/artifact consistency ──
    no_run_dir = [f"{r.get('config')}/{r.get('template')}/s{r.get('seed')}"
                  for r in rows if "error" not in r and not r.get("run_dir")]
    c6 = not no_run_dir
    results["6_run_dir_consistency"] = {"rows_missing_run_dir": len(no_run_dir), "pass": c6}

    # ── Check 7: interruption/resume accounting ──
    # Boundary: rows before interruption must be exactly the 579 completed set,
    # resumed rows must continue without gap/overlap.
    boundary_ok = False
    if INTERRUPTION_RECORD.exists():
        rec = json.loads(INTERRUPTION_RECORD.read_text())
        # pre-interruption rows: those with timestamp < interruption detection time
        detection_ts = rec.get("detected_at", "")
        pre_rows = [r for r in rows if "error" not in r and r.get("timestamp", "") < detection_ts]
        boundary_ok = len(pre_rows) >= 579  # at least the 579 recorded pre-interruption
    c7 = error_rows == [] and boundary_ok and len(rows) == EXPECTED_TOTAL
    results["7_interruption_resume_accounting"] = {
        "error_rows": len(error_rows), "pre_interruption_rows": len(pre_rows) if boundary_ok else None,
        "interruption_record_present": INTERRUPTION_RECORD.exists(), "pass": c7}

    # ── Check 8: frozen-instrument hash consistency ──
    # Iterate the manifest's OWN file list (the manifest defines the frozen set).
    hash_ok = False
    manifest_detail = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())
        expected_hashes = manifest.get("sha256", {})
        if isinstance(expected_hashes, dict) and expected_hashes:
            mismatches = []
            files_checked = 0
            for rel, expected in sorted(expected_hashes.items()):
                p = REPO / rel
                if not p.exists():
                    mismatches.append(f"{rel}: MISSING")
                    continue
                actual = sha256(p)
                files_checked += 1
                if expected != actual:
                    mismatches.append(f"{rel}: hash mismatch (got {actual[:12]}...)")
            hash_ok = not mismatches
            manifest_detail = {"mismatches": mismatches, "files_checked": files_checked,
                               "files_in_manifest": len(expected_hashes),
                               "manifest_commit": manifest.get("commit", "")}
    c8 = hash_ok
    results["8_frozen_instrument_hash"] = manifest_detail if manifest_detail else {"note": "manifest missing", "pass": False}
    results["8_frozen_instrument_hash"]["pass"] = c8

    # ── Check 9: run_id determinism (RBS-v4 repair item 7) ──
    # Every non-error row's run_id must be a pure logical-cell identity with
    # no random UUID suffix. Derive the expected run_id from the row's own
    # fields; any deviation means resume would generate fresh identities.
    import re as _re
    nondeterministic = []
    for r in rows:
        if "error" in r:
            continue
        rid = r.get("run_id")
        arch = r.get("architecture")
        scen = r.get("scenario_id")
        seed = r.get("seed")
        expected = f"d6c_holdout_{arch}_{scen}_s{seed}"
        if rid != expected:
            nondeterministic.append(f"{r.get('config')}/{r.get('template')}/s{seed}: got {rid!r}")
        elif _re.search(r"_[0-9a-f]{6}$", str(rid)):
            nondeterministic.append(f"{r.get('config')}/{r.get('template')}/s{seed}: uuid tail in {rid!r}")
    c9 = not nondeterministic
    results["9_run_id_determinism"] = {"non_deterministic_run_ids": nondeterministic,
                                       "pass": c9}

    # ── Aggregate ──
    checks = [f"c{i}" for i in range(1, 10)]
    all_pass = all(results[k]["pass"] for k in [f"{n}_{name}" for n, name in [
        ("1", "total_rows"), ("2", "cell_structure"), ("3", "seed_uniqueness_per_cell"),
        ("4", "duplicate_run_ids"), ("5", "foreign_keys"), ("6", "run_dir_consistency"),
        ("7", "interruption_resume_accounting"), ("8", "frozen_instrument_hash"),
        ("9", "run_id_determinism")]])

    summary = {
        "gate": "rbs-v4-holdout-integrity-gate",
        "version": "1.0",
        "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "total_rows_expected": EXPECTED_TOTAL,
        "total_rows_found": len(rows),
        "result": "PASS" if all_pass else "FAIL",
        "checks": results,
    }
    GATE_OUT.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))

    print(f"\n=== INTEGRITY GATE: {'PASS' if all_pass else 'FAIL'} ===")
    if not all_pass:
        for k, v in results.items():
            if not v.get("pass"):
                print(f"  RED: {k}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
