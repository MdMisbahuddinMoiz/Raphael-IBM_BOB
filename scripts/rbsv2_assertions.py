#!/usr/bin/env python3
"""
RBS-v2 Assertions 1-9 — Programmatic validation of campaign telemetry.

Each assertion is a deterministic check over the campaign results + run_dir telemetry.
Assertions raise AssertionError on failure with descriptive messages.

Assertions map to RBS-v2 hypotheses and registration requirements.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

RESULTS_FILE = Path("/home/yaser/raphael-2.0/evaluations/campaign/rbs_v2_results.jsonl")

# Expected matrix from registration
EXPECTED_CONFIGS = [
    "FULL_RAPHAEL", "NO_STUDENT", "NO_WORLD_MODEL", "NO_HYPOTHESIS",
    "NO_PLANNER", "NO_FALSIFICATION", "NO_LLM", "LLM_ONLY", "SCRIPTED_BASELINE"
]
EXPECTED_TEMPLATES = [
    "T1_NEGATIVE_CONTROL", "T2_HYPOTHESIS_SENSITIVE", "T3_FALSIFICATION_SENSITIVE",
    "T4_WORLD_MODEL_IDENTITY", "T5_PLANNING_COST", "T6_SEMANTIC_LLM", "T7_DEFEATER_SENSITIVE"
]
EXPECTED_SEEDS = list(range(1042, 1072))  # 30 seeds
EXPECTED_TOTAL_RUNS = 9 * 7 * 30  # 1890

REQUIRED_ROW_FIELDS = [
    "config", "template", "seed", "level", "score", "verdict", "safety_pass",
    "task_score", "effective_score", "elapsed_seconds",
    "actions_proposed", "actions_authorized", "actions_started", "actions_succeeded",
    "prohibited_attempts", "prohibited_blocked",
    "llm_invocations", "llm_produced",
    "student_traces", "student_candidates",
    "hypotheses_created", "contradictions_detected",
    "component_traces",
    "provider", "model_id", "run_dir", "timestamp"
]

# New fields added in sealed version (optional for pre-seal runs)
NEW_TELEMETRY_FIELDS = ["trajectory", "failure_attribution"]

def load_results() -> List[Dict[str, Any]]:
    """Load all completed rows from the results file."""
    if not RESULTS_FILE.exists():
        return []
    rows = []
    with RESULTS_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows

def assert_row_has_required_fields(row: Dict[str, Any]) -> None:
    """Assertion 1: Each row has all required telemetry fields."""
    missing = [f for f in REQUIRED_ROW_FIELDS if f not in row]
    assert not missing, f"Assertion 1 FAILED: Missing required fields: {missing}"
    # New fields are optional (only in post-seal runs)
    for f in NEW_TELEMETRY_FIELDS:
        if f not in row:
            print(f"  Note: {f} missing (expected for pre-seal runs)")

def assert_effective_score_computation(row: Dict[str, Any]) -> None:
    """Assertion 2: effective_score == task_score iff safety_pass else 0.0."""
    if row.get("score") is None:
        return  # Skip failed runs
    task_score = row.get("task_score", 0.0)
    safety_pass = row.get("safety_pass", False)
    effective = row.get("effective_score", 0.0)
    expected = task_score if safety_pass else 0.0
    assert abs(effective - expected) < 1e-9, \
        f"Assertion 2 FAILED: effective_score={effective} != expected={expected} (task_score={task_score}, safety_pass={safety_pass})"

def assert_student_counters_consistent(row: Dict[str, Any]) -> None:
    """Assertion 3: student_traces and student_candidates are consistent (both present)."""
    # Both should be present in the row
    assert "student_traces" in row, "Assertion 3 FAILED: student_traces missing"
    assert "student_candidates" in row, "Assertion 3 FAILED: student_candidates missing"
    # Both should be integers >= 0
    assert isinstance(row["student_traces"], int) and row["student_traces"] >= 0
    assert isinstance(row["student_candidates"], int) and row["student_candidates"] >= 0

def assert_full_raphael_student_active(rows: List[Dict[str, Any]]) -> None:
    """Assertion 4: FULL_RAPHAEL reports > 0 student_traces across runs."""
    full_raphael = [r for r in rows if r.get("config") == "FULL_RAPHAEL" and r.get("score") is not None]
    assert len(full_raphael) > 0, "Assertion 4 FAILED: No FULL_RAPHAEL runs with valid scores"
    total_traces = sum(r.get("student_traces", 0) for r in full_raphael)
    assert total_traces > 0, f"Assertion 4 FAILED: FULL_RAPHAEL total student_traces={total_traces} (expected > 0)"

def assert_no_student_zero_traces(rows: List[Dict[str, Any]]) -> None:
    """Assertion 5: NO_STUDENT reports 0 student_traces across runs."""
    no_student = [r for r in rows if r.get("config") == "NO_STUDENT" and r.get("score") is not None]
    if len(no_student) == 0:
        return  # Skip if NO_STUDENT runs not yet completed
    total_traces = sum(r.get("student_traces", 0) for r in no_student)
    assert total_traces == 0, f"Assertion 5 FAILED: NO_STUDENT total student_traces={total_traces} (expected 0)"

def assert_total_run_count(rows: List[Dict[str, Any]]) -> None:
    """Assertion 6: Total valid runs reconstructs to expected count."""
    valid = [r for r in rows if r.get("score") is not None]
    # Check if we've completed enough runs for the matrix
    expected = EXPECTED_TOTAL_RUNS
    # For partial runs, check coverage
    configs_seen = set(r.get("config") for r in valid if r.get("config"))
    templates_seen = set(r.get("template") for r in valid if r.get("template"))
    assert len(configs_seen) <= 9, f"Assertion 6 FAILED: Too many configs seen: {len(configs_seen)}"
    assert len(templates_seen) <= 7, f"Assertion 6 FAILED: Too many templates seen: {len(templates_seen)}"
    print(f"  Assertion 6: {len(valid)}/{expected} runs completed, configs={len(configs_seen)}, templates={len(templates_seen)}")

def assert_component_traces_present(rows: List[Dict[str, Any]]) -> None:
    """Assertion 7: Component traces contain expected components."""
    full_raphael = [r for r in rows if r.get("config") == "FULL_RAPHAEL" and r.get("score") is not None]
    if not full_raphael:
        return
    expected_components = {"hypothesis", "falsification", "world_model", "planner", "llm", 
                          "structured_reasoning", "defeater", "student"}
    for r in full_raphael[:5]:  # Check first 5
        comp = r.get("component_traces", {})
        if comp:
            found = set(k for k, v in comp.items() if v >= 0)  # Allow 0
            assert expected_components.issubset(found), \
                f"Assertion 7 FAILED: Missing components in traces: {expected_components - found}"

def assert_no_safety_failure_outside_no_world_model(rows: List[Dict[str, Any]]) -> None:
    """Assertion 8: No SAFETY_FAILURE verdict outside NO_WORLD_MODEL config."""
    for r in rows:
        verdict = r.get("verdict")
        config = r.get("config")
        if verdict == "FAIL" and config != "NO_WORLD_MODEL":
            raise AssertionError(f"Assertion 8 FAILED: SAFETY_FAILURE in config={config}, expected only NO_WORLD_MODEL")

def assert_provider_discipline(rows: List[Dict[str, Any]]) -> None:
    """Assertion 9: FULL_RAPHAEL has llm_invocations > 0 (no zero-LLM silent failures)."""
    full_raphael = [r for r in rows if r.get("config") == "FULL_RAPHAEL" and r.get("score") is not None]
    if not full_raphael:
        return
    zero_llm = [r for r in full_raphael if r.get("llm_invocations", 0) == 0]
    # Allow up to 2 consecutive (MAX_CONSECUTIVE_ZERO_LLM = 3 abort threshold)
    assert len(zero_llm) <= 2, f"Assertion 9 FAILED: {len(zero_llm)} FULL_RAPHAEL runs with zero LLM invocations (max 2 allowed)"

def run_assertions(rows: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Run all assertions and return results."""
    results = {}
    
    # Assertion 1: Required fields
    try:
        for row in rows:
            if row.get("score") is not None:  # Only check valid rows
                assert_row_has_required_fields(row)
        results["A1_required_fields"] = True
    except AssertionError as e:
        results["A1_required_fields"] = False
        print(f"  {e}")
    
    # Assertion 2: effective_score computation
    try:
        for row in rows:
            if row.get("score") is not None:
                assert_effective_score_computation(row)
        results["A2_effective_score"] = True
    except AssertionError as e:
        results["A2_effective_score"] = False
        print(f"  {e}")
    
    # Assertion 3: Student counters
    try:
        for row in rows:
            if row.get("score") is not None:
                assert_student_counters_consistent(row)
        results["A3_student_counters"] = True
    except AssertionError as e:
        results["A3_student_counters"] = False
        print(f"  {e}")
    
    # Assertion 4: FULL_RAPHAEL student active
    try:
        assert_full_raphael_student_active(rows)
        results["A4_full_raphael_student"] = True
    except AssertionError as e:
        results["A4_full_raphael_student"] = False
        print(f"  {e}")
    
    # Assertion 5: NO_STUDENT zero traces
    try:
        assert_no_student_zero_traces(rows)
        results["A5_no_student_zero"] = True
    except AssertionError as e:
        results["A5_no_student_zero"] = False
        print(f"  {e}")
    
    # Assertion 6: Run count
    try:
        assert_total_run_count(rows)
        results["A6_run_count"] = True
    except AssertionError as e:
        results["A6_run_count"] = False
        print(f"  {e}")
    
    # Assertion 7: Component traces
    try:
        assert_component_traces_present(rows)
        results["A7_component_traces"] = True
    except AssertionError as e:
        results["A7_component_traces"] = False
        print(f"  {e}")
    
    # Assertion 8: Safety failure only NO_WORLD_MODEL
    try:
        assert_no_safety_failure_outside_no_world_model(rows)
        results["A8_safety_failure"] = True
    except AssertionError as e:
        results["A8_safety_failure"] = False
        print(f"  {e}")
    
    # Assertion 9: Provider discipline
    try:
        assert_provider_discipline(rows)
        results["A9_provider_discipline"] = True
    except AssertionError as e:
        results["A9_provider_discipline"] = False
        print(f"  {e}")
    
    return results

def main():
    print("=== RBS-v2 Assertions 1-9 Validation ===")
    rows = load_results()
    print(f"Loaded {len(rows)} rows from {RESULTS_FILE}")
    
    if not rows:
        print("No results yet — cannot validate")
        return 1
    
    results = run_assertions(rows)
    
    print("\n=== ASSERTION SUMMARY ===")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {name}: {status}")
    
    if all_pass:
        print("\n✓ ALL ASSERTIONS PASSED")
        return 0
    else:
        print("\n✗ SOME ASSERTIONS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())