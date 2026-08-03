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
    model_id="nemotron-3-ultra:cloud",
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
    """Count STUDENT-origin candidates from episodes.jsonl."""
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
                if ep.get("candidate_origin") == "STUDENT":
                    count += 1
        return count
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
    
    # Compute safety_pass and effective_score
    safety_pass = True
    if ev and hasattr(ev, "verdict"):
        safety_pass = (ev.verdict.value == "PASS")
    elif ev and hasattr(ev, "score"):
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
                        print(f"  [{completed:04d}] OK  {row['config']} | {row['template']} | seed={row['seed']} | score={score:.3f} eff={effective:.3f} stu_traces={stu_traces} stu_cands={stu_cands}")
                        
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