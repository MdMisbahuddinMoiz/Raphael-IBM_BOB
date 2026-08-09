#!/usr/bin/env python3
"""
RBS-v4 100-RUN VALIDATION CAMPAIGN
===================================
Quick sanity check before terminal holdout:
- 5 seeds (relative 0..4 -> abs 2000..2004)
- 5 families
- 4 arms
= 100 runs

Model: nvidia/llama-3.3-nemotron-super-49b-v1 (49B, gate-passing)
Purpose: Verify L-028 fix restored discrimination across ALL arms.
"""
import sys, json, os, time, hashlib
from pathlib import Path

_NO_SCRIPTS = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_REPO_ROOT, "src")
for p in (_SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _SRC)
os.chdir(_REPO_ROOT)

import logging
logging.getLogger().setLevel(logging.WARNING)

def _load_dotenv(path: str) -> None:
    if not os.path.exists(path): return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k and k not in os.environ: os.environ[k] = v.strip()

_here = os.path.dirname(os.path.abspath(__file__))
_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.templates import TEMPLATE_REGISTRY, ScenarioSplit
from arena.d6_manifest import ITERATION_BUDGET

MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
CAMPAIGN = "rbs-v4-validation-100"
INSTRUMENT_TAG = "validation-100"
PROMPT_FREEZE_SHA = "e9d6a0fdb4a9a5462dd5a8e7d95f82affea082c8bb1aaec887e5b1b89412bb67"

FAMILIES = ["known-observable", "signal-noise", "false-lead", "contradiction", "forbidden-proximity"]
ARMS = ["FULL_RAPHAEL", "NO_WORLD_MODEL", "PROMPTED_AGENT", "SCRIPTED_BASELINE"]

SEED_COUNT = 5  # relative 0..4 -> abs 2000..2004
ACTION_CAP = 5
SPLIT_NAME = "holdout"

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_validation_100.jsonl"
RUN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign" / "validation_100_runs"

def _abs_seed(rel): 
    from arena.templates.base import resolve_seed
    abs_s = resolve_seed(rel, ScenarioSplit.HOLDOUT)
    assert 2000 <= abs_s < 10000
    return abs_s

def _world_hash(tmpl, rel):
    from arena.templates.base import resolve_seed
    abs_s = resolve_seed(rel, ScenarioSplit.HOLDOUT)
    sc = tmpl.generate(seed=rel, split=ScenarioSplit.HOLDOUT)
    pol = sc.policy
    canon = {"scenario_id": sc.scenario_id, "name": sc.name, "description": sc.description,
             "allowed_targets": sorted(pol.allowed_targets or []), "prohibited_targets": sorted(pol.prohibited_targets or []),
             "allowed_action_types": sorted(pol.allowed_action_types or []), "prohibited_action_types": sorted(pol.prohibited_action_types or []),
             "allowed_capabilities": sorted(pol.allowed_capabilities or []), "prohibited_capabilities": sorted(pol.prohibited_capabilities or []),
             "starting_assets": sc.evaluator_truth.get("starting_assets", []), "objective": sc.evaluator_truth.get("objective", "")}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, default=str).encode()).hexdigest()

def run_one(config_id, family_id, rel_seed):
    tmpl = TEMPLATE_REGISTRY[family_id]
    abs_s = _abs_seed(rel_seed)
    expected_sid = f"{tmpl.family_id}-s{abs_s:04d}"
    wh = _world_hash(tmpl, rel_seed)
    runner = AblationRunner(template=tmpl, config=ABLATION_PRESETS[config_id],
                            seed=rel_seed, split=SPLIT_NAME, output_dir=str(RUN_DIR),
                            llm_config_override=None)
    t0 = time.time()
    metrics = runner.run()
    rdir = runner.save()
    elapsed = round(time.time() - t0, 2)
    m = metrics.to_dict()
    ev = runner.evaluation_result
    row = {
        "campaign": CAMPAIGN, "phase": "validation", "config": config_id, "arm": config_id,
        "template": family_id, "scenario_id": expected_sid, "seed": rel_seed, "abs_seed": abs_s,
        "run_id": runner.run_id, "world_hash": wh,
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "passed_checks": list(ev.passed_checks) if ev else [],
        "failed_checks": list(ev.failed_checks) if ev else [],
        "details": dict(ev.details) if ev and ev.details else {},
        "elapsed_seconds": elapsed,
        "actions_dispatched": m.get("actions_dispatched"),
        "iterations_used": m.get("iterations_used"),
        "provider_failures": m.get("provider_failures"),
        "model_failures": m.get("model_failures"),
        "llm_calls": m.get("llm_calls"),
        "decision_outcome": m.get("decision_outcome"),
        "outcome": m.get("outcome"),
        "outcome_reason": m.get("outcome_reason"),
        "evaluator_name": "evaluate_runconclusion",
        "adapter_name": type(getattr(runner, "_conclusion", None).__class__).__name__ if getattr(runner, "_conclusion", None) else "None",
        "model_id": MODEL_ID, "provider": "nvidia",
        "prompt_freeze_sha": PROMPT_FREEZE_SHA, "instrument_tag": INSTRUMENT_TAG,
        "run_dir": str(rdir) if rdir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _svc = getattr(runner, "_llm_service", None)
    if _svc:
        row.update({
            "envelope_failures": getattr(_svc, "envelope_failures", None),
            "logical_llm_calls": getattr(_svc, "logical_llm_calls", None),
            "provider_attempts": getattr(_svc, "provider_attempts", None),
            "failover_count": getattr(_svc, "failover_count", None),
            "final_key_alias": getattr(_svc, "final_key_alias", None),
            "failure_class": getattr(_svc, "failure_class", None),
        })
    return row

def run_validation():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cells = [(cfg, fam, sd) for fam in FAMILIES for cfg in ARMS for sd in range(SEED_COUNT)]
    total = len(cells)
    completed = set()
    if OUT.exists():
        for ln in OUT.open():
            try:
                r = json.loads(ln)
                if r.get("campaign") == CAMPAIGN and "error" not in r:
                    completed.add((r["config"], r["template"], r["seed"]))
            except: pass
    print(f"=== VALIDATION-100: {len(cells)} cells planned, {len(completed)} completed ===")
    t_start = time.time()
    for i, (cfg, fam, sd) in enumerate(cells, 1):
        if (cfg, fam, sd) in completed: continue
        t0 = time.time()
        try:
            r = run_one(cfg, fam, sd)
            dt = time.time() - t0
            print(f"  [{i}/{total}] {cfg:18s} {fam:20s} s{sd} -> score={r['score']} verdict={r['verdict']} disp={r['actions_dispatched']} pf={r['provider_failures']} t={dt:.1f}s")
            with open(OUT, "a") as f: f.write(json.dumps(r) + "\n")
        except Exception as e:
            import traceback
            print(f"  [{i}/{total}] FAILED {cfg} {fam} s{sd}: {e}")
            traceback.print_exc()
            with open(OUT, "a") as f:
                f.write(json.dumps({"campaign": CAMPAIGN, "config": cfg, "template": fam, "seed": sd,
                                   "error": str(e), "phase": "validation", "instrument_tag": INSTRUMENT_TAG,
                                   "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    print(f"\n=== VALIDATION-100: {(time.time()-t_start)/60:.1f}min total ===")

if __name__ == "__main__":
    run_validation()