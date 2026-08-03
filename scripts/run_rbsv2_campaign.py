#!/usr/bin/env python3
"""
RBS-v2 Campaign Driver with local-Ollama LLM override.

Executes the full RBS-v2 factorial design:
- Configurations: 9 (FULL_RAPHAEL, NO_STUDENT, NO_WORLD_MODEL, NO_HYPOTHESIS,
  NO_PLANNER, NO_FALSIFICATION, NO_LLM, LLM_ONLY, SCRIPTED_BASELINE)
- Templates: 7 (T1-T7 redesigned for STACK_MAP coverage)
- Seeds: 30 per cell (N=30)
- Total Runs: 1,680 (9 × 7 × 30)
- Headline Metric: effective_score = task_score * safety_pass

Does NOT modify frozen scripts/ or src/. Injects the project-designated provider
(Ollama, per baseline manifest) via AblationRunner.llm_config_override, persists
every run's raw telemetry via runner.save(), and appends each run's metrics to
evaluations/campaign/rbs_v2_results.jsonl.
"""

from pathlib import Path
import sys
import json
import os
import time
from datetime import datetime, timezone

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent)
_SRC = _REPO_ROOT + "/src"
for p in (_SCRIPTS, _SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
# Final order must mirror the frozen scripts: _SRC first, then _SCRIPTS,
# then _REPO_ROOT — so scripts/arena.py can never shadow src/arena/.
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _SRC)

import logging
logging.getLogger().setLevel(logging.WARNING)
import urllib.request

# Rule 35 (Provider Discipline): fail fast instead of silently recording
# invalid runs. Probe provider once at startup; abort if it cannot produce a
# valid semantic inference. During the run, abort if consecutive FULL_RAPHAEL
# runs produce zero semantic inferences (the provider went down mid-campaign,
# exactly the silent failure SENTINEL invalidated).
HEALTH_PROBE_MESSAGE = (
    'Reply with exactly: {"claim": "echo", "category": "connection"}'
)
MAX_CONSECUTIVE_ZERO_LLM = 3


def _provider_health_check() -> bool:
    payload = json.dumps({
        "model": OVERRIDE.model_id,
        "messages": [{"role": "user", "content": HEALTH_PROBE_MESSAGE}],
        "max_tokens": 4096,
        "temperature": 0.0,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        OVERRIDE.api_base + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {OVERRIDE.api_key or 'ollama'}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            d = json.loads(resp.read())
        content = d["choices"][0]["message"].get("content", "")
        return "claim" in content
    except Exception:
        return False


from arena.semantic_inference import LLMProviderConfig
from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.d6_manifest import D6_SCENARIO_FACTORIES, SCENARIO_TEMPLATES
from d6c_holdout_runner import D6Template

OVERRIDE = LLMProviderConfig(
    model_id="bjoernb/gemma4-31b-think:latest",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=120,
    temperature=0.0,
    max_tokens=4096,
)

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v2_results.jsonl"

# RBS-v2 Experimental Design (from registration.json)
# 30 seeds per cell, N=30
SEEDS = list(range(1042, 1072))  # 1042-1071 inclusive = 30 seeds

CONFIGS = [
    "FULL_RAPHAEL",
    "NO_STUDENT",
    "NO_WORLD_MODEL",
    "NO_HYPOTHESIS",
    "NO_PLANNER",
    "NO_FALSIFICATION",
    "NO_LLM",
    "LLM_ONLY",
    "SCRIPTED_BASELINE",
]

TEMPLATES = [
    "T1_NEGATIVE_CONTROL",
    "T2_HYPOTHESIS_SENSITIVE",
    "T3_FALSIFICATION_SENSITIVE",
    "T4_WORLD_MODEL_IDENTITY",
    "T5_PLANNING_COST",
    "T6_SEMANTIC_LLM",
    "T7_DEFEATER_SENSITIVE",
]

# Template level mapping for difficulty scaling (H2-5)
TEMPLATE_LEVELS = {
    "T1_NEGATIVE_CONTROL": "Level_1",
    "T2_HYPOTHESIS_SENSITIVE": "Level_2",
    "T3_FALSIFICATION_SENSITIVE": "Level_3",
    "T4_WORLD_MODEL_IDENTITY": "Level_2",
    "T5_PLANNING_COST": "Level_1",
    "T6_SEMANTIC_LLM": "Level_3",
    "T7_DEFEATER_SENSITIVE": "Level_3",
}


def _llm_engagement_from_traces(run_dir):
    """Ground truth for LLM engagement from component_traces.json."""
    if not run_dir:
        return None, None
    p = Path(run_dir) / "component_traces.json"
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text())
        traces = data.get("traces", []) if isinstance(data, dict) else data
        inv = sum(1 for t in traces
                  if t.get("component") == "llm_service"
                  and t.get("operation") == "llm_inference")
        prod = sum(1 for t in traces
                   if t.get("component") == "llm_service"
                   and t.get("operation") == "produced_semantic_inference")
        return inv, prod
    except Exception:
        return None, None


def _student_engagement_from_traces(run_dir):
    """Track Student candidate generation from component_traces.json."""
    if not run_dir:
        return 0
    p = Path(run_dir) / "component_traces.json"
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
        traces = data.get("traces", []) if isinstance(data, dict) else data
        student_traces = sum(1 for t in traces
                            if t.get("component") == "student")
        return student_traces
    except Exception:
        return 0


def _student_candidates_from_run(run_dir):
    """Count STUDENT-origin candidates from episodes.jsonl.

    NOTE: candidate_origin lives on EACH candidate action inside the
    episode's candidate_actions list, and on selected_action. The
    episode dict itself has no candidate_origin field.
    """
    if not run_dir:
        return 0
    p = Path(run_dir) / "episodes.jsonl"
    if not p.exists():
        return 0
    try:
        count = 0
        with p.open() as f:
            for line in f:
                ep = json.loads(line)
                for cand in ep.get("candidate_actions", []) or []:
                    if isinstance(cand, dict) and cand.get("candidate_origin") == "STUDENT":
                        count += 1
        return count
    except Exception:
        return 0


def _student_selection_from_run(run_dir):
    """Count episodes where a STUDENT-origin candidate was SELECTED.

    selected_action carries candidate_origin="STUDENT" when the planner
    chose a Student-proposed action. Distinguishes 'component active but
    ineffective' (generated but never chosen) from 'component active AND
    consumed by planner'.
    """
    if not run_dir:
        return 0
    p = Path(run_dir) / "episodes.jsonl"
    if not p.exists():
        return 0
    try:
        count = 0
        with p.open() as f:
            for line in f:
                ep = json.loads(line)
                sa = ep.get("selected_action") or {}
                if isinstance(sa, dict) and sa.get("candidate_origin") == "STUDENT":
                    count += 1
        return count
    except Exception:
        return 0


def _student_consumed_by_planner(run_dir):
    """Count STUDENT-origin candidates that the planner RANKED (scored).

    Planner scoring of a Student candidate proves the planner 'saw' it,
    even if a different candidate was ultimately selected. A candidate
    appears in candidate_actions AND in planner_scores with the same
    action_id.
    """
    if not run_dir:
        return 0
    p = Path(run_dir) / "episodes.jsonl"
    if not p.exists():
        return 0
    try:
        consumed = 0
        with p.open() as f:
            for line in f:
                ep = json.loads(line)
                student_ids = set()
                for cand in ep.get("candidate_actions", []) or []:
                    if isinstance(cand, dict) and cand.get("candidate_origin") == "STUDENT":
                        cid = cand.get("action_id")
                        if cid:
                            student_ids.add(cid)
                if not student_ids:
                    continue
                # planner_scores entries may be {action: type, score} or
                # {action_id, score} depending on planner version
                for ps in ep.get("planner_scores", []) or []:
                    psid = ps.get("action_id") or ps.get("action")
                    if psid in student_ids:
                        consumed += 1
                        student_ids.discard(psid)
        return consumed
    except Exception:
        return 0


def _extract_trajectory(run_dir):
    """Extract action trajectory from episodes.jsonl."""
    if not run_dir:
        return None
    p = Path(run_dir) / "episodes.jsonl"
    if not p.exists():
        return None
    try:
        trajectory = []
        with p.open() as f:
            for line in f:
                ep = json.loads(line)
                trajectory.append({
                    "sequence": ep.get("sequence_number"),
                    "objective": ep.get("objective"),
                    "selected_action": ep.get("selected_action", {}).get("action_type"),
                    "selected_origin": ep.get("selected_action", {}).get("candidate_origin"),
                    "objective_progress": ep.get("objective_progress"),
                    "evidence_created": len(ep.get("evidence_created", [])),
                })
        return trajectory
    except Exception:
        return None


def _extract_failure_attribution(run_dir):
    """Extract failure attribution from verification.json."""
    if not run_dir:
        return None
    p = Path(run_dir) / "verification.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        isolation = data.get("isolation", {})
        safety = data.get("safety", {})
        return {
            "isolation_pass": isolation.get("pass"),
            "isolation_failures": isolation.get("failures", []),
            "safety_pass": safety.get("pass"),
            "safety_failures": safety.get("failures", []),
            "prohibited_escaped": safety.get("prohibited_escaped", 0),
        }
    except Exception:
        return None


def run_one(config_id, template_key, seed):
    template_info = SCENARIO_TEMPLATES[template_key]
    factory = D6_SCENARIO_FACTORIES[template_info["id"]]
    template = D6Template(factory, template_info["id"])
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=seed,
        split="validation",
        llm_config_override=OVERRIDE,
    )
    t0 = time.time()
    metrics = runner.run()
    run_dir = runner.save()  # save() returns the run_dir Path
    elapsed = round(time.time() - t0, 2)

    m = metrics.to_dict()
    ev = runner.evaluation_result
    llm_invoked, llm_produced = _llm_engagement_from_traces(run_dir)
    student_traces = _student_engagement_from_traces(run_dir)
    student_candidates = _student_candidates_from_run(run_dir)
    student_selected = _student_selection_from_run(run_dir)
    student_consumed = _student_consumed_by_planner(run_dir)
    
    # Compute safety_pass and effective_score
    # ── D15-FIX: safety_pass MUST come from the actual safety verification
    # (SafetyVerifier output persisted in verification.json), NOT from the
    # task evaluation verdict. RBS-v2 conflated these, causing:
    #   (a) verdict enum value "pass" (lowercase) != "PASS" → all 690
    #       successful runs marked unsafe;
    #   (b) safety_pass defaulted True when ev was None → 410 invalid runs
    #       'passed' safety;
    #   (c) the real SafetyVerifier result was extracted (failure_attribution)
    #       but never used.
    fa = _extract_failure_attribution(run_dir)
    if fa is not None and fa.get("safety_pass") is not None:
        safety_pass = bool(fa["safety_pass"])
    else:
        # Fallback: correct lowercase verdict comparison
        safety_pass = True
        if ev and hasattr(ev, "verdict") and ev.verdict is not None:
            safety_pass = (ev.verdict.value == "pass")
        elif ev and hasattr(ev, "score") and ev.score is not None:
            safety_pass = (ev.score > 0.5)  # heuristic if verdict missing
    
    task_score = ev.score if ev else 0.0
    effective_score = task_score if safety_pass else 0.0
    
    row = {
        "config": config_id,
        "template": template_key,
        "seed": seed,
        "level": TEMPLATE_LEVELS.get(template_key, "unknown"),
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "safety_pass": safety_pass,
        "task_score": task_score,
        "effective_score": effective_score,
        "elapsed_seconds": round(time.time() - time.time() + elapsed, 2) if False else elapsed,  # use elapsed directly
        "actions_proposed": m.get("actions_proposed"),
        "actions_authorized": m.get("actions_authorized"),
        "actions_started": m.get("actions_started"),
        "actions_succeeded": m.get("actions_succeeded"),
        "prohibited_attempts": m.get("prohibited_attempts"),
        "prohibited_blocked": m.get("prohibited_blocked"),
        "llm_invocations": llm_invoked,
        "llm_produced": llm_produced,
        "student_traces": student_traces,
        "student_candidates": student_candidates,
        "student_candidates_consumed": student_consumed,
        "student_candidates_selected": student_selected,
        "hypotheses_created": m.get("hypotheses_created"),
        "contradictions_detected": m.get("contradictions_detected"),
        "component_traces": m.get("component_traces"),
        "trajectory": _extract_trajectory(run_dir),
        "failure_attribution": _extract_failure_attribution(run_dir),
        "provider": "ollama",
        "model_id": OVERRIDE.model_id,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return row, run_dir


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total_planned = len(CONFIGS) * len(TEMPLATES) * len(range(1042, 1072))
    print(f"[CAMPAIGN] RBS-v2 Campaign")
    print(f"[CAMPAIGN] planned runs: {total_planned}")
    print(f"[CAMPAIGN] output: {OUT}")
    print(f"[CAMPAIGN] provider: {OVERRIDE.model_id} via {OVERRIDE.api_base}")
    print(f"[CAMPAIGN] configs: {len(CONFIGS)} | templates: {len(TEMPLATES)} | seeds: 30")
    print(f"[CAMPAIGN] max_tokens: {OVERRIDE.max_tokens}")

    # ── Resume: Load completed (config, template, seed) tuples ──
    completed_keys = set()
    if OUT.exists():
        with open(OUT, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    cfg = row.get("config")
                    tmpl = row.get("template")
                    seed = row.get("seed")
                    # Skip if run completed (has score OR no error field indicating crash)
                    if cfg and tmpl is not None and seed is not None:
                        has_score = row.get("score") is not None
                        no_error = "error" not in row
                        if has_score or no_error:
                            completed_keys.add((cfg, tmpl, seed))
                except json.JSONDecodeError:
                    continue
    if completed_keys:
        print(f"[CAMPAIGN] Resume mode: {len(completed_keys)} valid runs already completed, will skip")
    
    print("[CAMPAIGN] provider health check...")
    if not _provider_health_check():
        print("[CAMPAIGN] ABORT: provider health check FAILED (no valid semantic inference).")
        sys.exit(1)
    print("[CAMPAIGN] provider health check PASSED")

    print()

    completed = 0
    failed = 0
    consecutive_zero_llm = 0
    MAX_CONSECUTIVE_ZERO_LLM = 3
    
    with open(OUT, "a") as f:
        for config_id in CONFIGS:
            for template_key in TEMPLATES:
                for seed in range(1042, 1072):  # 30 seeds
                    key = (config_id, template_key, seed)
                    if key in completed_keys:
                        continue  # Skip already completed run
                    label = f"{config_id} | {template_key} | seed={seed}"
                    try:
                        row, run_dir = run_one(config_id, template_key, seed)
                        
                        # Save detailed run directory
                        if run_dir:
                            # runner.save() already called in AblationRunner.run() via _run_with_save pattern
                            pass
                        
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        completed += 1
                        
                        # Rule 35: Provider discipline
                        if config_id == "FULL_RAPHAEL":
                            llm_produced = row.get("llm_produced", 0)
                            if llm_produced > 0:
                                consecutive_zero_llm = 0
                            else:
                                consecutive_zero_llm += 1
                                if consecutive_zero_llm >= 3:
                                    print(f"[CAMPAIGN] ABORT: 3 consecutive FULL_RAPHAEL runs with zero LLM output. Provider down.")
                                    print(f"[CAMPAIGN] partial results retained in: {OUT}")
                                    sys.exit(2)
                        
                        score = row.get('score')
                        effective = row.get('effective_score')
                        stu_traces = row.get('student_traces', 0)
                        stu_cands = row.get('student_candidates', 0)
                        score_str = f"{score:.3f}" if score is not None else "N/A"
                        eff_str = f"{effective:.3f}" if effective is not None else "N/A"
                        print(f"  [{completed:04d}] OK  {row['config']} | {row['template']} | seed={row['seed']} | score={score_str} eff={eff_str} stu_traces={stu_traces} stu_cands={stu_cands}")
                        
                    except Exception as e:
                        failed += 1
                        row = {
                            "config": config_id, 
                            "template": template_key,
                            "seed": seed,
                            "score": None, 
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        print(f"  [{completed:04d}] FAIL {label} | error={e}")

    print()
    print(f"[CAMPAIGN] COMPLETED: {completed} | FAILED: {failed} | TOTAL: {completed + failed}")
    print(f"[CAMPAIGN] Results saved to: {OUT}")


if __name__ == "__main__":
    main()