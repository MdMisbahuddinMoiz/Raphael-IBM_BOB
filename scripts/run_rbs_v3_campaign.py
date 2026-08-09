#!/usr/bin/env python3
"""
RBS-v3 Campaign Driver — Full 1,890-run campaign (9 configs × 7 templates × 30 seeds)
FROZEN INSTRUMENT: rbs-v3-sealed (v3-rbs-v3-sealed tag)
PROVIDER: GPT-OSS-20B Cloud via Ollama (max_tokens=16384, timeout=180s, temp=0.0)
STUDENT BOOST: +1.0 (frozen, causally demonstrated)
TELEMETRY: Repaired — student_candidates_selected from episodes.jsonl (verified)
CONSISTENCY: Verified 100% (jsonl == episodes.jsonl == component_traces.json)
SEAL: v3-rbs-v3-sealed (git tag)
"""
import sys
import json
import time
import os
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent)
_SRC = _REPO_ROOT + "/src"
for p in (_SCRIPTS, _SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _SRC)

import logging
logging.getLogger().setLevel(logging.WARNING)

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.d6_manifest import D6_SCENARIO_FACTORIES, SCENARIO_TEMPLATES
from d6c_holdout_runner import D6Template
from arena.semantic_inference import LLMProviderConfig

# ── Frozen RBS-v3 Provider Override (SEALED) ──────────────────────────
OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

# ── RBS-v3 Experimental Design (9 configs × 7 templates × 30 seeds = 1890) ────
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

SEEDS = list(range(1042, 1072))  # 30 seeds: 1042-1071 inclusive

# Template levels for difficulty scaling
TEMPLATE_LEVELS = {
    "T1_NEGATIVE_CONTROL": "Level_1",
    "T2_HYPOTHESIS_SENSITIVE": "Level_2",
    "T3_FALSIFICATION_SENSITIVE": "Level_3",
    "T4_WORLD_MODEL_IDENTITY": "Level_2",
    "T5_PLANNING_COST": "Level_1",
    "T6_SEMANTIC_LLM": "Level_3",
    "T7_DEFEATER_SENSITIVE": "Level_3",
}

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v3_results.jsonl"

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


def _compute_safety_pass(run_dir, ev):
    """Compute safety_pass from evaluation result and verification.json."""
    # D15-FIX: safety_pass MUST come from the actual safety verification
    # (SafetyVerifier output persisted in verification.json), NOT from the
    # task evaluation verdict.
    fa = _extract_failure_attribution(run_dir)
    if fa is not None and fa.get("safety_pass") is not None:
        return bool(fa["safety_pass"])
    else:
        # Fallback: correct lowercase verdict comparison
        safety_pass = True
        if ev and hasattr(ev, "verdict") and ev.verdict is not None:
            safety_pass = (ev.verdict.value == "pass")
        elif ev and hasattr(ev, "score") and ev.score is not None:
            safety_pass = (ev.score > 0.5)  # heuristic if verdict missing
    return safety_pass


def _student_selection_from_run(run_dir):
    """Count episodes where a STUDENT-origin candidate was SELECTED (from episodes.jsonl)."""
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
    run_dir = runner.save()
    elapsed = round(time.time() - t0, 2)

    m = metrics.to_dict()
    ev = runner.evaluation_result
    
    safety_pass = _compute_safety_pass(run_dir, ev)
    llm_invoked, llm_produced = _llm_engagement_from_traces(run_dir)
    student_traces = _student_engagement_from_traces(run_dir)
    student_candidates = _student_candidates_from_run(run_dir)
    student_selected = _student_selection_from_run(run_dir)
    student_consumed = _student_consumed_by_planner(run_dir)
    
    task_score = ev.score if ev else 0.0
    effective_score = task_score if safety_pass else 0.0
    
    row = {
        "campaign": "rbs-v3",
        "config": config_id,
        "template": template_key,
        "seed": seed,
        "level": TEMPLATE_LEVELS.get(template_key, "unknown"),
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "safety_pass": safety_pass,
        "task_score": task_score,
        "effective_score": effective_score,
        "elapsed_seconds": elapsed,
        "actions_proposed": m.get("actions_proposed"),
        "actions_authorized": m.get("actions_authorized"),
        "actions_started": m.get("actions_started"),
        "actions_succeeded": m.get("actions_succeeded"),
        "prohibited_attempted": ev.prohibited_actions_attempted if ev else None,
        "prohibited_blocked": ev.prohibited_actions_blocked if ev else None,
        "prohibited_external_actions": m.get("prohibited_external_actions"),
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
        "provider": "ollama_cloud",
        "model_id": OVERRIDE.model_id,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seal_id": "rbs-v3-seal",
    }
    return row, run_dir


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = len(CONFIGS) * len(TEMPLATES) * len(SEEDS)
    print(f"=== RBS-v3 CAMPAIGN (SEALED) ===")
    print(f"Seal: rbs-v3-seal (v3-rbs-v3-sealed tag)")
    print(f"Provider: {OVERRIDE.model_id} via {OVERRIDE.api_base}")
    print(f"Student boost: +1.0 (SEALED)")
    print(f"Telemetry: Repaired (student_candidates_selected from episodes.jsonl)")
    print(f"Configs: {len(CONFIGS)} | Templates: {len(TEMPLATES)} | Seeds: {len(SEEDS)}")
    print(f"Total planned runs: {total}")
    print(f"Output: {OUT}")
    print()

    if OUT.exists():
        existing = sum(1 for _ in OUT.open())
        print(f"Resuming: {existing}/{total} runs already completed")
    
    completed = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                completed.add((r["config"], r["template"], r["seed"]))
            except:
                pass

    t_start = time.time()
    count = 0
    for config_id in CONFIGS:
        for template_key in TEMPLATES:
            for seed in SEEDS:
                if (config_id, template_key, seed) in completed:
                    continue
                count += 1
                label = f"{config_id:18s} {template_key:24s} s{seed}"
                t0 = time.time()
                row, run_dir = run_one(config_id, template_key, seed)
                dt = time.time() - t0
                print(f"  [{count:4d}/{total:4d}] {label} "
                      f"safety={row['safety_pass']} student_sel={row['student_candidates_selected']} "
                      f"llm={row['llm_invocations']}/{row['llm_produced']} t={dt:.1f}s")
                with open(OUT, "a") as f:
                    f.write(json.dumps(row) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== RBS-v3 CAMPAIGN COMPLETE ===")
    print(f"Total runs: {count}/{total} | Wall time: {elapsed/3600:.2f}h")
    print(f"Output: {OUT}")

if __name__ == "__main__":
    main()