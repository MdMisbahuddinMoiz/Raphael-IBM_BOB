#!/usr/bin/env python3
"""
RBS-v4 TERMINAL HOLDOUT CAMPAIGN — Frozen Instrument Evaluation
================================================================
Pre-registered: 12 discriminative templates (T1-T12) × 9 configs 
× 30 holdout seeds (1072-1101) = 3,240 runs.
Instrument: v4-benchmark-frozen (tagged), provider=ollama gpt-oss:20b-cloud, temp=0.0.
Mode: COLLECTION-ONLY. No early inspection, no adaptive changes.
Output: evaluations/campaign/rbs_v4_holdout.jsonl
"""
import sys
import json
import time
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

# ── Frozen Instrument (identical to v4-benchmark-frozen) ──
OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

# ── Holdout Design: 12 discriminative templates × 9 configs × 30 seeds ──
# Templates: T1-T12 (exclude T8_DVWA_LIVE which is live integration)
HOLDOUT_TEMPLATES = [
    "T1_NEGATIVE_CONTROL",      # arena-d6-001
    "T2_HYPOTHESIS_SENSITIVE",  # arena-d6-002
    "T3_FALSIFICATION_SENSITIVE", # arena-d6-003
    "T4_WORLD_MODEL_IDENTITY",  # arena-d6-004
    "T5_PLANNING_COST",         # arena-d6-005
    "T6_SEMANTIC_LLM",          # arena-d6-006
    "T7_DEFEATER_SENSITIVE",    # arena-d6-007
    "T8_STUDENT_EXCLUSIVE",     # arena-d6-009 (repaired)
    "T9_SEMANTIC_AMBIGUITY",    # arena-d6-010
    "T10_MISLEADING_EVIDENCE",  # arena-d6-011 (repaired)
    "T11_COMPETING_HYPOTHESES", # arena-d6-012 (repaired)
    "T12_SAFETY_BOUNDARY",      # arena-d6-013
]

# Configs: FULL_RAPHAEL + 7 single-component ablations + SCRIPTED_BASELINE (9 total)
HOLDOUT_CONFIGS = [
    "FULL_RAPHAEL",
    "NO_HYPOTHESIS",
    "NO_FALSIFICATION", 
    "NO_WORLD_MODEL",
    "NO_PLANNER",
    "NO_LLM",
    "NO_DEFEATER",
    "NO_STUDENT",
    "SCRIPTED_BASELINE",
]

# Holdout seeds (pristine, never touched)
SEEDS = list(range(1072, 1102))  # 1072-1101 inclusive = 30 seeds

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_holdout.jsonl"


def _trace_counts(run_dir):
    out = {"llm_invocations": 0, "llm_produced": 0,
           "hypothesis_traces": 0, "falsification_traces": 0,
           "student_traces": 0, "planner_traces": 0, "defeater_traces": 0,
           "structured_reasoning_traces": 0, "world_model_traces": 0}
    if not run_dir:
        return out
    p = Path(run_dir) / "component_traces.json"
    if not p.exists():
        return out
    try:
        data = json.loads(p.read_text())
        traces = data.get("traces", []) if isinstance(data, dict) else data
        for t in traces:
            comp = t.get("component", "")
            op = t.get("operation", "")
            if comp in ("llm", "llm_service") and op == "llm_inference":
                out["llm_invocations"] += 1
            elif comp in ("llm", "llm_service") and op == "produced_semantic_inference":
                out["llm_produced"] += 1
            elif comp == "hypothesis":
                out["hypothesis_traces"] += 1
            elif comp == "falsification":
                out["falsification_traces"] += 1
            elif comp == "student":
                out["student_traces"] += 1
            elif comp == "planner":
                out["planner_traces"] += 1
            elif comp == "defeater":
                out["defeater_traces"] += 1
            elif comp == "structured_reasoning":
                out["structured_reasoning_traces"] += 1
            elif comp == "world_model":
                out["world_model_traces"] += 1
    except Exception:
        pass
    return out


def run_one(config_id, template_key, seed):
    template_info = SCENARIO_TEMPLATES[template_key]
    scenario_id = template_info["id"]
    factory = D6_SCENARIO_FACTORIES[scenario_id]
    template = D6Template(factory, scenario_id)
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=seed,
        split="holdout",
        llm_config_override=OVERRIDE,
    )
    t0 = time.time()
    metrics = runner.run()
    run_dir = runner.save()
    elapsed = round(time.time() - t0, 2)

    m = metrics.to_dict()
    ev = runner.evaluation_result
    tc = _trace_counts(run_dir)

    row = {
        "campaign": "rbs-v4-holdout",
        "config": config_id,
        "template": template_key,
        "scenario_id": scenario_id,
        "seed": seed,
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "passed_checks": list(ev.passed_checks) if ev else [],
        "failed_checks": list(ev.failed_checks) if ev else [],
        "details": dict(ev.details) if ev and ev.details else {},
        "elapsed_seconds": elapsed,
        "llm_invocations": tc["llm_invocations"],
        "llm_produced": tc["llm_produced"],
        "hypothesis_traces": tc["hypothesis_traces"],
        "falsification_traces": tc["falsification_traces"],
        "student_traces": tc["student_traces"],
        "planner_traces": tc["planner_traces"],
        "defeater_traces": tc["defeater_traces"],
        "structured_reasoning_traces": tc["structured_reasoning_traces"],
        "world_model_traces": tc["world_model_traces"],
        "hypotheses_formed": m.get("hypotheses_formed"),
        "hypotheses_confirmed": m.get("hypotheses_confirmed"),
        "hypotheses_falsified": m.get("hypotheses_falsified"),
        "contradictions_detected": m.get("contradictions_detected"),
        "contradictions_resolved": m.get("contradictions_resolved"),
        "actions_started": m.get("actions_started"),
        "actions_completed": m.get("actions_completed"),
        "prohibited_attempted": ev.prohibited_actions_attempted if ev else None,
        "prohibited_blocked": ev.prohibited_actions_blocked if ev else None,
        "provider": "ollama_cloud",
        "model_id": OVERRIDE.model_id,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "holdout",
        "instrument_tag": "v4-benchmark-frozen",
    }
    return row


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = len(HOLDOUT_TEMPLATES) * len(HOLDOUT_CONFIGS) * len(SEEDS)
    print("=" * 78)
    print("RBS-v4 TERMINAL HOLDOUT CAMPAIGN")
    print("=" * 78)
    print(f"Instrument: v4-benchmark-frozen ({OVERRIDE.model_id} via {OVERRIDE.api_base})")
    print(f"Templates: {len(HOLDOUT_TEMPLATES)} (T1-T12 discriminative)")
    print(f"Configs: {len(HOLDOUT_CONFIGS)} (FULL + 7 ablations + SCRIPTED_BASELINE)")
    print(f"Seeds: {len(SEEDS)} (1072-1101, holdout, never touched)")
    print(f"Total planned runs: {total}")
    print(f"Output: {OUT}")
    print(f"Collection-only mode: NO early inspection, NO adaptive changes")
    print()

    # Resume from existing JSONL
    completed = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                completed.add((r["config"], r["template"], r["seed"]))
            except Exception:
                pass
    print(f"Resuming: {len(completed)} runs already completed")

    t_start = time.time()
    count = 0
    errors = 0

    # Iterate templates outermost (better for debugging/logging)
    for template_key in HOLDOUT_TEMPLATES:
        for config_id in HOLDOUT_CONFIGS:
            for seed in SEEDS:
                if (config_id, template_key, seed) in completed:
                    continue
                count += 1
                label = f"{config_id:18s} {template_key:28s} s{seed}"
                t0 = time.time()
                try:
                    row = run_one(config_id, template_key, seed)
                    dt = time.time() - t0
                    # Minimal progress log (no score interpretation)
                    print(f"  [{count:5d}/{total:5d}] {label} "
                          f"score={row['score']} time={dt:.1f}s "
                          f"llm={row['llm_invocations']}/{row['llm_produced']} "
                          f"hyp={row['hypothesis_traces']} fals={row['falsification_traces']} "
                          f"stud={row['student_traces']} def={row['defeater_traces']} "
                          f"prohib={row['prohibited_attempted']}/{row['prohibited_blocked']}")
                    with open(OUT, "a") as f:
                        f.write(json.dumps(row) + "\n")
                except Exception as e:
                    errors += 1
                    import traceback
                    print(f"  [{count:5d}/{total:5d}] FAILED {label}: {e}")
                    traceback.print_exc()
                    with open(OUT, "a") as f:
                        f.write(json.dumps({
                            "campaign": "rbs-v4-holdout", "config": config_id,
                            "template": template_key, "seed": seed, "error": str(e),
                            "phase": "holdout", "instrument_tag": "v4-benchmark-frozen",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== HOLDOUT CAMPAIGN COMPLETE ===")
    print(f"Completed: {count}/{total} runs | Errors: {errors} | Wall time: {elapsed/3600:.2f}h")
    print(f"Output: {OUT}")
    print("Next: raw-data integrity → exclusions accounting → safety analysis → final report → raphael-terminal-freeze")


if __name__ == "__main__":
    main()