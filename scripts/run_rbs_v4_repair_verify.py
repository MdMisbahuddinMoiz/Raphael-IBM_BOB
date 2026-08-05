#!/usr/bin/env python3
"""
RBS-v4 REPAIR VERIFICATION — T8/T10/T11 (SENTINEL Option A, arena-instrument repair)
=====================================================================================
Scope: 3 repaired templates x 6 dev seeds (1042-1047) x 2 configs (FULL + target ablation)
      = 36 runs.
Purpose: verify MECHANISM CHAINS (NOT score deltas):
  T8 : Stack detected -> Student invoked -> glassfish candidate generated
       -> reaches Planner (plan_decisions) -> selection/execution observable
       (broker log direct_probe). NO_STUDENT must have 0 student traces.
  T10: Decoy presented -> falsification activity observable (contradiction)
       -> environment responds (decoy resolution) -> discriminator executed.
       NO_FALSIFICATION must have 0 contradictions.
  T11: Hypotheses instantiated (FULL) vs NoOp (NO_HYPOTHESIS); LLM operational
       in BOTH: llm_invocations > 0 in NO_HYPOTHESIS while hypothesis traces == 0.
REGRESSION ASSERTION (T11): LLM(NO_HYPOTHESIS) == operational,
                            HypothesisManager(NO_HYPOTHESIS) == disabled.
Output: evaluations/campaign/rbs_v4_repair_verify.jsonl
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

VERIFY_TEMPLATES = {
    "T8_STUDENT_EXCLUSIVE": {"ablation": "NO_STUDENT"},
    "T10_MISLEADING_EVIDENCE": {"ablation": "NO_FALSIFICATION"},
    "T11_COMPETING_HYPOTHESES": {"ablation": "NO_HYPOTHESIS"},
}
SEEDS = [1042, 1043, 1044, 1045, 1046, 1047]
OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_repair_verify.jsonl"


def _trace_counts(run_dir):
    """Per-component trace counts + llm invocation/produced counts."""
    out = {
        "llm_invocations": 0, "llm_produced": 0,
        "hypothesis_traces": 0, "falsification_traces": 0,
        "student_traces": 0, "planner_traces": 0,
        "structured_reasoning_traces": 0,
    }
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
            if comp == "llm" or comp == "llm_service":
                op = t.get("operation", "")
                if op == "llm_inference":
                    out["llm_invocations"] += 1
                elif op == "produced_semantic_inference":
                    out["llm_produced"] += 1
            elif comp == "hypothesis":
                out["hypothesis_traces"] += 1
            elif comp == "falsification":
                out["falsification_traces"] += 1
            elif comp == "student":
                out["student_traces"] += 1
            elif comp == "planner":
                out["planner_traces"] += 1
            elif comp == "structured_reasoning":
                out["structured_reasoning_traces"] += 1
    except Exception:
        pass
    return out


def _student_candidates(run_dir):
    if not run_dir:
        return 0
    p = Path(run_dir) / "episodes.jsonl"
    if not p.exists():
        return 0
    count = 0
    try:
        with p.open() as f:
            for line in f:
                ep = json.loads(line)
                for cand in ep.get("candidate_actions", []) or []:
                    if isinstance(cand, dict) and cand.get("candidate_origin") == "STUDENT":
                        count += 1
    except Exception:
        pass
    return count


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
        "campaign": "rbs-v4-repair-verify",
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
        "structured_reasoning_traces": tc["structured_reasoning_traces"],
        "student_candidates": _student_candidates(run_dir),
        "hypotheses_formed": m.get("hypotheses_formed"),
        "contradictions_detected": m.get("contradictions_detected"),
        "action_count": ev.action_count if ev else None,
        "provider": "ollama_cloud",
        "model_id": OVERRIDE.model_id,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "repair_verify",
    }
    return row


def report_verification(path):
    rows = []
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("campaign") == "rbs-v4-repair-verify" and r.get("score") is not None:
                    rows.append(r)
            except Exception:
                pass

    print("\n" + "=" * 78)
    print("MECHANISM-CHAIN VERIFICATION (per SENTINEL Option A — NOT score deltas)")
    print("=" * 78)

    for template_key, spec in VERIFY_TEMPLATES.items():
        full = [r for r in rows if r["template"] == template_key and r["config"] == "FULL_RAPHAEL"]
        abl = [r for r in rows if r["template"] == template_key and r["config"] == spec["ablation"]]
        print(f"\n--- {template_key} (FULL n={len(full)} | {spec['ablation']} n={len(abl)}) ---")

        if template_key == "T8_STUDENT_EXCLUSIVE":
            fs_traces = [r["student_traces"] for r in full]
            as_traces = [r["student_traces"] for r in abl]
            fs_cands = [r["student_candidates"] for r in full]
            as_cands = [r["student_candidates"] for r in abl]
            sel = [r["details"].get("student_selected") for r in full]
            probe = [r["details"].get("probe_executed") for r in full]
            print(f"  FULL student_traces      : {fs_traces}")
            print(f"  FULL student_candidates  : {fs_cands}")
            print(f"  FULL student_selected    : {sel}")
            print(f"  FULL probe_executed      : {probe}")
            print(f"  {spec['ablation']:26s} student_traces: {as_traces}")
            print(f"  {spec['ablation']:26s} student_candidates: {as_cands}")
            chain = all(t > 0 for t in fs_traces) if fs_traces else False
            noab = all(t == 0 for t in as_traces) if as_traces else False
            obs = any(sel) or any(probe)
            print(f"  [{'PASS' if chain else 'FAIL'}] Student chain fires in FULL (all seeds)")
            print(f"  [{'PASS' if noab else 'FAIL'}] Student silent in {spec['ablation']} (all seeds)")
            print(f"  [{'PASS' if obs else 'FAIL'}] Selection OR execution observable in FULL")

        elif template_key == "T10_MISLEADING_EVIDENCE":
            fc = [r["details"].get("contradiction_count", r.get("contradictions_detected")) for r in full]
            ac = [r["details"].get("contradiction_count", r.get("contradictions_detected")) for r in abl]
            de = [r["details"].get("discriminator_executed") for r in full]
            dr = [r["details"].get("decoy_resolved") for r in full]
            ff = [r["falsification_traces"] for r in full]
            af = [r["falsification_traces"] for r in abl]
            print(f"  FULL contradictions      : {fc}")
            print(f"  FULL discriminator_exec  : {de}")
            print(f"  FULL decoy_resolved      : {dr}")
            print(f"  FULL falsification_traces: {ff}")
            print(f"  {spec['ablation']:26s} contradictions: {ac}")
            print(f"  {spec['ablation']:26s} falsification_traces: {af}")
            chain = (fc and all(c > 0 for c in fc) and any(de)) if fc else False
            noab = (ac and all(c == 0 for c in ac)) if ac else False
            print(f"  [{'PASS' if chain else 'FAIL'}] Contradiction + discriminator chain fires in FULL")
            print(f"  [{'PASS' if noab else 'FAIL'}] Falsification absent in {spec['ablation']}")

        elif template_key == "T11_COMPETING_HYPOTHESES":
            fh = [r["hypothesis_traces"] for r in full]
            ah = [r["hypothesis_traces"] for r in abl]
            fl = [r["llm_invocations"] for r in full]
            al = [r["llm_invocations"] for r in abl]
            fp = [r["details"].get("hypothesis_count", r.get("hypotheses_formed")) for r in full]
            ap = [r["details"].get("hypothesis_count", r.get("hypotheses_formed")) for r in abl]
            print(f"  FULL hypothesis_traces   : {fh}")
            print(f"  FULL llm_invocations     : {fl}")
            print(f"  FULL hypotheses_formed   : {fp}")
            print(f"  {spec['ablation']:26s} hypothesis_traces: {ah}")
            print(f"  {spec['ablation']:26s} llm_invocations  : {al}")
            print(f"  {spec['ablation']:26s} hypotheses_formed: {ap}")
            active = (fh and all(t > 0 for t in fh)) if fh else False
            regress = (ah and all(t == 0 for t in ah) and al and all(i > 0 for i in al)) if ah and al else False
            print(f"  [{'PASS' if active else 'FAIL'}] HypothesisManager active in FULL (all seeds)")
            print(f"  [{'PASS' if regress else 'FAIL'}] REGRESSION ASSERTION: LLM operational + HypothesisManager disabled in NO_HYPOTHESIS")

    # Scores (informational only, NOT a gate per SENTINEL)
    print("\n--- SCORE SUMMARY (informational; delta NOT a repair gate) ---")
    import statistics
    for template_key, spec in VERIFY_TEMPLATES.items():
        full = [r["score"] for r in rows if r["template"] == template_key and r["config"] == "FULL_RAPHAEL"]
        abl = [r["score"] for r in rows if r["template"] == template_key and r["config"] == spec["ablation"]]
        if full and abl:
            mf, ma = statistics.mean(full), statistics.mean(abl)
            print(f"  {template_key:28s} FULL={mf:.3f} {spec['ablation']}={ma:.3f} delta={mf-ma:+.3f}")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = len(VERIFY_TEMPLATES) * len(SEEDS) * 2
    print("=== RBS-v4 REPAIR VERIFICATION (T8/T10/T11, seeds 1042-1047) ===")
    print(f"Provider: {OVERRIDE.model_id} via {OVERRIDE.api_base}")
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
    for template_key, spec in VERIFY_TEMPLATES.items():
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
                          f"llm={row['llm_invocations']}/{row['llm_produced']} "
                          f"hyp={row['hypothesis_traces']} fals={row['falsification_traces']} "
                          f"stud={row['student_traces']} t={dt:.1f}s")
                    with open(OUT, "a") as f:
                        f.write(json.dumps(row) + "\n")
                except Exception as e:
                    import traceback
                    print(f"  [{count:4d}/{total:4d}] FAILED {label}: {e}")
                    traceback.print_exc()
                    with open(OUT, "a") as f:
                        f.write(json.dumps({
                            "campaign": "rbs-v4-repair-verify", "config": config_id,
                            "template": template_key, "seed": seed, "error": str(e),
                            "phase": "repair_verify",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== REPAIR VERIFICATION COMPLETE: {count}/{total} runs | {elapsed/60:.1f}min ===")
    report_verification(OUT)


if __name__ == "__main__":
    main()
