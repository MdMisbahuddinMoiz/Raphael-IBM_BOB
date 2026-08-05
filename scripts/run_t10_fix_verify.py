#!/usr/bin/env python3
"""Re-run T10 FULL vs NO_FALSIFICATION with corrected evaluator check 3."""
import sys, json, time
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
logging.getLogger().setLevel(logging.ERROR)

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.d6_manifest import D6_SCENARIO_FACTORIES, SCENARIO_TEMPLATES
from d6c_holdout_runner import D6Template
from arena.semantic_inference import LLMProviderConfig

OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud", provider="ollama",
    api_base="http://localhost:11434/v1", api_key="ollama",
    timeout_seconds=180, temperature=0.0, max_tokens=16384,
)

SEEDS = [1042, 1043, 1044, 1045, 1046, 1047]
OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_repair_verify_t10fix.jsonl"

def run_one(config_id, seed):
    template_info = SCENARIO_TEMPLATES["T10_MISLEADING_EVIDENCE"]
    scenario_id = template_info["id"]
    factory = D6_SCENARIO_FACTORIES[scenario_id]
    template = D6Template(factory, scenario_id)
    runner = AblationRunner(
        template=template, config=ABLATION_PRESETS[config_id],
        seed=seed, split="validation", llm_config_override=OVERRIDE,
    )
    t0 = time.time()
    metrics = runner.run()
    run_dir = runner.save()
    ev = runner.evaluation_result
    # read traces from run dir
    from pathlib import Path as P
    tp = P(run_dir) / "component_traces.json"
    tc = {"llm": 0, "hypothesis": 0, "falsification": 0, "student": 0}
    if tp.exists():
        data = json.loads(tp.read_text())
        for t in data.get("traces", []):
            c = t.get("component", "")
            if c in tc:
                tc[c] += 1
    row = {
        "campaign": "rbs-v4-repair-verify-t10fix",
        "config": config_id, "template": "T10_MISLEADING_EVIDENCE",
        "scenario_id": scenario_id, "seed": seed,
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "passed_checks": list(ev.passed_checks) if ev else [],
        "failed_checks": list(ev.failed_checks) if ev else [],
        "details": dict(ev.details) if ev and ev.details else {},
        "falsification_traces": tc["falsification"],
        "elapsed_seconds": round(time.time() - t0, 2),
        "run_dir": str(run_dir),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "repair_verify_t10fix",
    }
    return row

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                completed.add((r["config"], r["seed"]))
            except Exception:
                pass
    count = 0
    for config_id in ("FULL_RAPHAEL", "NO_FALSIFICATION"):
        for seed in SEEDS:
            if (config_id, seed) in completed:
                continue
            count += 1
            try:
                row = run_one(config_id, seed)
                print(f"  [{count}] {config_id:16s} s{seed} score={row['score']} "
                      f"passed={len(row['passed_checks'])} fals={row['falsification_traces']}")
                with open(OUT, "a") as f:
                    f.write(json.dumps(row) + "\n")
            except Exception as e:
                import traceback
                print(f"  [{count}] FAILED {config_id} s{seed}: {e}")
                traceback.print_exc()

    print("\n=== T10 FIXED-EVALUATOR SUMMARY ===")
    rows = []
    with OUT.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("campaign") == "rbs-v4-repair-verify-t10fix" and r.get("score") is not None:
                    rows.append(r)
            except Exception:
                pass
    import statistics
    full = [r["score"] for r in rows if r["config"] == "FULL_RAPHAEL"]
    abl = [r["score"] for r in rows if r["config"] == "NO_FALSIFICATION"]
    if full and abl:
        mf, ma = statistics.mean(full), statistics.mean(abl)
        print(f"FULL={mf:.3f} NO_FALSIFICATION={ma:.3f} delta={mf-ma:+.3f}")
    for r in rows:
        print(f"  {r['config']:16s} s{r['seed']}: {r['score']} pass={r['passed_checks']}")
        print(f"      details={r['details']}")

if __name__ == "__main__":
    main()
