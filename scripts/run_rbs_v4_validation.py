#!/usr/bin/env python3
"""
RBS-v4 VALIDATION RUN — repaired T8/T10/T11 on seeds 1048-1053
===============================================================
Per SENTINEL mandate: after repair verification passes (mechanism chains
verified on 1042-1047), run validation on the next 6 seeds to classify the
repaired templates. 3 templates x 6 seeds x 2 configs = 36 runs.
Output: evaluations/campaign/rbs_v4_validation.jsonl
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

OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

VALIDATE_TEMPLATES = {
    "T8_STUDENT_EXCLUSIVE": {"ablation": "NO_STUDENT"},
    "T10_MISLEADING_EVIDENCE": {"ablation": "NO_FALSIFICATION"},
    "T11_COMPETING_HYPOTHESES": {"ablation": "NO_HYPOTHESIS"},
}
SEEDS = [1048, 1049, 1050, 1051, 1052, 1053]
OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_validation.jsonl"


def _trace_counts(run_dir):
    out = {"llm_invocations": 0, "hypothesis_traces": 0, "falsification_traces": 0,
           "student_traces": 0, "planner_traces": 0}
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
            if comp in ("llm", "llm_service") and t.get("operation") == "llm_inference":
                out["llm_invocations"] += 1
            elif comp == "hypothesis":
                out["hypothesis_traces"] += 1
            elif comp == "falsification":
                out["falsification_traces"] += 1
            elif comp == "student":
                out["student_traces"] += 1
            elif comp == "planner":
                out["planner_traces"] += 1
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
        split="validation",
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
        "campaign": "rbs-v4-validation",
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
        "hypothesis_traces": tc["hypothesis_traces"],
        "falsification_traces": tc["falsification_traces"],
        "student_traces": tc["student_traces"],
        "planner_traces": tc["planner_traces"],
        "hypotheses_formed": m.get("hypotheses_formed"),
        "contradictions_detected": m.get("contradictions_detected"),
        "provider": "ollama_cloud",
        "model_id": OVERRIDE.model_id,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "validation",
    }
    return row


def report(path):
    rows = []
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("campaign") == "rbs-v4-validation" and r.get("score") is not None:
                    rows.append(r)
            except Exception:
                pass
    import statistics
    print("\n" + "=" * 80)
    print("VALIDATION CLASSIFICATION (seeds 1048-1053, repaired instrument)")
    print("=" * 80)
    for template_key, spec in VALIDATE_TEMPLATES.items():
        full = [r["score"] for r in rows if r["template"] == template_key and r["config"] == "FULL_RAPHAEL"]
        abl = [r["score"] for r in rows if r["template"] == template_key and r["config"] == spec["ablation"]]
        if not full or not abl:
            print(f"  {template_key}: INCOMPLETE (full={len(full)} abl={len(abl)})")
            continue
        mf, ma = statistics.mean(full), statistics.mean(abl)
        sf, sa = (statistics.stdev(full) if len(full) > 1 else 0.0,
                  statistics.stdev(abl) if len(abl) > 1 else 0.0)
        n = len(full)
        ci_f = 1.96 * sf / (n ** 0.5)
        ci_a = 1.96 * sa / (n ** 0.5)
        delta = mf - ma
        status = "DISCRIMINATIVE" if delta >= 0.30 else ("INERT" if delta < 0.10 else "MARGINAL")
        print(f"\n  {template_key}")
        print(f"    FULL={mf:.3f}±{ci_f:.3f} (sd={sf:.3f})   {spec['ablation']}={ma:.3f}±{ci_a:.3f} (sd={sa:.3f})")
        print(f"    delta={delta:+.3f} -> [{status}]")
        print(f"    FULL scores: {[round(x,2) for x in full]}")
        print(f"    {spec['ablation']:16s} scores: {[round(x,2) for x in abl]}")
        # mechanism chain checks for validation seeds
        if template_key == "T11_COMPETING_HYPOTHESES":
            fl = [r["llm_invocations"] for r in rows if r["template"] == template_key and r["config"] == "FULL_RAPHAEL"]
            al = [r["llm_invocations"] for r in rows if r["template"] == template_key and r["config"] == spec["ablation"]]
            ah = [r["hypothesis_traces"] for r in rows if r["template"] == template_key and r["config"] == spec["ablation"]]
            print(f"    T11 regression: NO_HYPOTHESIS llm_invoc={al} hypothesis_traces={ah}")
            ok = all(i > 0 for i in al) and all(h == 0 for h in ah) and all(i > 0 for i in fl)
            print(f"    [{'PASS' if ok else 'FAIL'}] LLM operational in NO_HYPOTHESIS + HypothesisManager disabled")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = len(VALIDATE_TEMPLATES) * len(SEEDS) * 2
    print("=== RBS-v4 VALIDATION (repaired T8/T10/T11, seeds 1048-1053) ===")
    print(f"Total planned runs: {total}")
    print(f"Output: {OUT}")
    print()

    completed = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                completed.add((r["config"], r["template"], r["seed"]))
            except Exception:
                pass

    t_start = time.time()
    count = 0
    for template_key, spec in VALIDATE_TEMPLATES.items():
        for config_id in ("FULL_RAPHAEL", spec["ablation"]):
            for seed in SEEDS:
                if (config_id, template_key, seed) in completed:
                    continue
                count += 1
                label = f"{config_id:18s} {template_key:24s} s{seed}"
                t0 = time.time()
                try:
                    row = run_one(config_id, template_key, seed)
                    dt = time.time() - t0
                    print(f"  [{count:4d}/{total:4d}] {label} score={row['score']} "
                          f"llm={row['llm_invocations']} hyp={row['hypothesis_traces']} "
                          f"fals={row['falsification_traces']} stud={row['student_traces']} t={dt:.1f}s")
                    with open(OUT, "a") as f:
                        f.write(json.dumps(row) + "\n")
                except Exception as e:
                    import traceback
                    print(f"  [{count:4d}/{total:4d}] FAILED {label}: {e}")
                    traceback.print_exc()
                    with open(OUT, "a") as f:
                        f.write(json.dumps({
                            "campaign": "rbs-v4-validation", "config": config_id,
                            "template": template_key, "seed": seed, "error": str(e),
                            "phase": "validation",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== VALIDATION COMPLETE: {count}/{total} runs | {elapsed/60:.1f}min ===")
    report(OUT)


if __name__ == "__main__":
    main()
