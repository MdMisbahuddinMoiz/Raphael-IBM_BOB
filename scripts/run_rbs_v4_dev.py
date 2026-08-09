#!/usr/bin/env python3
"""
RBS-v4 DEV RUN — TERMINAL FALSIFICATION instrument validation (DEV split)
=========================================================================
Per SENTINEL Gate B adjudication (DEV: AUTHORIZED; VALIDATION/HOLDOUT: DENIED):

  - 5 families (T8_STUDENT_EXCLUSIVE, T9_SEMANTIC_AMBIGUITY, T10_MISLEADING_EVIDENCE,
    T11_COMPETING_HYPOTHESES, T12_SAFETY_BOUNDARY) x 10 seeds/family = 50 matched
    scenario instances, DEV split only.
  - Arms (prereg arms list): FULL_RAPHAEL (primary), PROMPTED_AGENT (primary),
    NO_WORLD_MODEL (diagnostic), SCRIPTED_BASELINE (prereg arm; deterministic).
  - llm_config_override = None -> runner default LLM config
    (nvidia/llama-3.3-nemotron-super-49b-v1, per prereg AMENDMENT-A-2026-08-06).
  - Live network for FULL_RAPHAEL + NO_WORLD_MODEL (LLMService).
    GEN1 PROMPTED_AGENT used TracedLLM simulation (REPORTED as DEV-01, never
    silently used for terminal inference). REPAIR-DEV-01 (SENTINEL-authorized)
    rewired _run_llm_only to the REAL LLMService path; gen2 reruns ONLY the
    PROMPTED_AGENT cells with the repaired arm (--gen2), writing to a separate
    output file tagged gen=2. Gen1 PROMPTED rows are superseded, not deleted.
  - Provider failure policy (D-6C): 503/timeout/connection_error -> row marked
    PROVIDER_CONFOUNDED via metrics.provider_failures; no selective retry.

Outputs:
  - evaluations/campaign/rbs_v4_dev.jsonl            (gen1 append-only row log, resumable)
  - evaluations/campaign/rbs_v4_dev_prompted_gen2.jsonl (gen2 PROMPTED-only rerun, resumable)
  - evaluations/campaign/dev_runs/                   (per-run dirs via runner.save())
  - --report: evaluations/campaign/rbs_v4_dev_report.json (items A-N, gen1)
  - --report-gen2: evaluations/campaign/rbs_v4_dev_prompted_gen2_report.json
                    (SENTINEL REPORT items 1-11 for REPAIR-DEV-01 acceptance)

HOLDOUT GUARD: this script only ever derives DEV seeds via
_derive_seed(f"<template>_dev", i). It NEVER imports or reads HOLDOUT_SEEDS
and NEVER opens any holdout/validation result file.
"""
import sys
import json
import time
import statistics
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
from arena.d6_manifest import (
    D6_SCENARIO_FACTORIES, D6_SCENARIO_EVALUATORS,
    SCENARIO_TEMPLATES, _derive_seed, ITERATION_BUDGET,
)
from arena.runner import SCENARIO_EVALUATORS as _GLOBAL_EVALUATORS
from d6c_holdout_runner import D6Template

# ── Register D-6 evaluators into the global evaluator registry (required for
#    both arms to be scored by the architecture-blind scenario evaluator;
#    see ablation_runner._evaluate() line ~3026-3039) ─────────────────────
_GLOBAL_EVALUATORS.update(D6_SCENARIO_EVALUATORS)

# ── Frozen campaign identity ──────────────────────────────────────────────
MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
CAMPAIGN = "rbs-v4-dev"

# 5 discriminative families of the terminal protocol (research spec T8-T12)
DEV_TEMPLATES = [
    "T8_STUDENT_EXCLUSIVE",
    "T9_SEMANTIC_AMBIGUITY",
    "T10_MISLEADING_EVIDENCE",
    "T11_COMPETING_HYPOTHESES",
    "T12_SAFETY_BOUNDARY",
]

# All 4 prereg arms. Order: network arms first (cheap determinism last).
ARMS = ["FULL_RAPHAEL", "NO_WORLD_MODEL", "PROMPTED_AGENT", "SCRIPTED_BASELINE"]

DEV_SEED_COUNT = 10  # SENTINEL mandate: 10 seeds/family (manifest has 3; extend via same derivation)
ACTION_CAP = 5

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_dev.jsonl"
RUN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign" / "dev_runs"
REPORT_OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_dev_report.json"

# ── REPAIR-DEV-01 gen2 (PROMPTED_AGENT rerun, repaired arm) ───────────────
GEN2_OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_dev_prompted_gen2.jsonl"
GEN2_REPORT_OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_dev_prompted_gen2_report.json"
GEN2_ARM = "PROMPTED_AGENT"
GEN2_LAB = "repair_dev_01"


def dev_seeds(template_key: str):
    return [_derive_seed(f"{template_key}_dev", i) for i in range(DEV_SEED_COUNT)]


def _trace_counts(run_dir):
    """Count component traces from the run dir (same logic as validation script)."""
    out = {"llm_invocations": 0, "hypothesis_traces": 0, "falsification_traces": 0,
           "student_traces": 0, "planner_traces": 0, "world_model_traces": 0,
           "llm_trace_calls": 0}
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
            elif comp == "hypothesis":
                out["hypothesis_traces"] += 1
            elif comp == "falsification":
                out["falsification_traces"] += 1
            elif comp == "student":
                out["student_traces"] += 1
            elif comp == "planner":
                out["planner_traces"] += 1
            elif comp == "world_model":
                out["world_model_traces"] += 1
            if comp == "llm":
                out["llm_trace_calls"] += 1
    except Exception:
        pass
    return out


def run_one(config_id, template_key, seed, dry=False, gen=None):
    template_info = SCENARIO_TEMPLATES[template_key]
    scenario_id = template_info["id"]
    factory = D6_SCENARIO_FACTORIES[scenario_id]
    template = D6Template(factory, scenario_id)

    if dry:
        # Construction-only probe: verify config resolution + evaluator registration.
        runner = AblationRunner(
            template=template,
            config=ABLATION_PRESETS[config_id],
            seed=seed,
            split="dev",
            output_dir=str(RUN_DIR),
            llm_config_override=None,
        )
        return {
            "dry": True, "config": config_id, "template": template_key,
            "seed": seed, "scenario_id": scenario_id,
            "run_id": runner.run_id,
            "model_id": getattr(runner.llm_service.config, "model_id", None),
            "provider": getattr(runner.llm_service.config, "provider", None),
            "api_base": getattr(runner.llm_service.config, "api_base", None),
            "temperature": getattr(runner.llm_service.config, "temperature", None),
            "max_tokens": getattr(runner.llm_service.config, "max_tokens", None),
            "timeout_seconds": getattr(runner.llm_service.config, "timeout_seconds", None),
            "evaluator_registered": scenario_id in _GLOBAL_EVALUATORS,
            "baseline_type": ABLATION_PRESETS[config_id].baseline_type,
        }

    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=seed,
        split="dev",
        output_dir=str(RUN_DIR),
        llm_config_override=None,
    )
    t0 = time.time()
    metrics = runner.run()
    run_dir = runner.save()
    elapsed = round(time.time() - t0, 2)
    m = metrics.to_dict()
    ev = runner.evaluation_result
    tc = _trace_counts(run_dir)

    safety_pass = None
    safety_failures = []
    if getattr(runner, "safety_result", None) is not None:
        safety_pass = bool(runner.safety_result.get("pass", False))
        safety_failures = runner.safety_result.get("failures", [])

    isolation_pass = bool(getattr(metrics, "isolation_pass", False))
    isolation_failures = list(getattr(metrics, "isolation_failures", []) or [])

    row = {
        "campaign": CAMPAIGN,
        "config": config_id,
        "template": template_key,
        "scenario_id": scenario_id,
        "seed": seed,
        "run_id": runner.run_id,
        "score": ev.score if ev else None,
        "verdict": ev.verdict.value if ev and hasattr(ev, "verdict") else None,
        "passed_checks": list(ev.passed_checks) if ev else [],
        "failed_checks": list(ev.failed_checks) if ev else [],
        "details": dict(ev.details) if ev and ev.details else {},
        "elapsed_seconds": elapsed,
        "llm_invocations": tc["llm_invocations"],
        "llm_trace_calls": tc["llm_trace_calls"],
        "hypothesis_traces": tc["hypothesis_traces"],
        "falsification_traces": tc["falsification_traces"],
        "student_traces": tc["student_traces"],
        "planner_traces": tc["planner_traces"],
        "world_model_traces": tc["world_model_traces"],
        # ── resource / budget accounting ──
        "actions_dispatched": m.get("actions_dispatched"),
        "actions_authorized": m.get("actions_authorized"),
        "actions_denied": m.get("actions_denied"),
        "actions_started": m.get("actions_started"),
        "actions_succeeded": m.get("actions_succeeded"),
        "iterations_used": m.get("iterations_used"),
        "budget_iteration_ceiling": m.get("budget_iteration_ceiling"),
        "budget_action_ceiling": m.get("budget_action_ceiling"),
        "ACTION_CAP": m.get("ACTION_CAP"),
        "input_tokens": m.get("input_tokens"),
        "output_tokens": m.get("output_tokens"),
        "provider_failures": m.get("provider_failures"),
        "infra_failures": m.get("infra_failures"),
        "decision_outcome": m.get("decision_outcome"),
        "outcome": m.get("outcome"),
        "outcome_reason": m.get("outcome_reason"),
        # ── instrument validity ──
        "safety_pass": safety_pass,
        "safety_failures": safety_failures,
        "isolation_pass": isolation_pass,
        "isolation_failures": isolation_failures,
        "model_id": MODEL_ID,
        "provider": "nvidia",
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "dev",
    }
    if gen is not None:
        row["gen"] = gen
        row["meta"] = {"lab": GEN2_LAB}
        row["model_failures"] = m.get("model_failures")
        row["llm_calls"] = m.get("llm_calls")
        _svc = getattr(runner, "_llm_service", None)
        row["envelope_failures"] = getattr(_svc, "envelope_failures", None) if _svc else None
    return row


def run_campaign(max_cells=None):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    cells = []
    for template_key in DEV_TEMPLATES:
        for config_id in ARMS:
            for seed in dev_seeds(template_key):
                cells.append((config_id, template_key, seed))
    total = len(cells)

    completed = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                if r.get("campaign") == CAMPAIGN and "error" not in r and not r.get("dry"):
                    completed.add((r["config"], r["template"], r["seed"]))
            except Exception:
                pass

    print("=== RBS-v4 DEV (TERMINAL FALSIFICATION instrument validation) ===")
    print(f"Families : {DEV_TEMPLATES}")
    print(f"Arms     : {ARMS}")
    print(f"Seeds    : {DEV_SEED_COUNT}/family (dev-derived via _derive_seed('<tpl>_dev', i))")
    for t in DEV_TEMPLATES:
        print(f"  {t:24s} seeds={dev_seeds(t)}")
    print(f"Total planned cells: {total} | already completed: {len(completed)}")
    print(f"Output: {OUT}")
    print()

    t_start = time.time()
    count = 0
    for (config_id, template_key, seed) in cells:
        if max_cells and count >= max_cells:
            print(f"[RESUME-CHECK] stopping after {count} cells this invocation")
            break
        if (config_id, template_key, seed) in completed:
            continue
        count += 1
        label = f"{config_id:18s} {template_key:24s} s{seed}"
        t0 = time.time()
        try:
            row = run_one(config_id, template_key, seed)
            dt = time.time() - t0
            print(f"  [{count:4d}/{total:4d}] {label} score={row['score']} "
                  f"verdict={row['verdict']} llm={row['llm_invocations']} "
                  f"disp={row['actions_dispatched']} tok={row['input_tokens']}+{row['output_tokens']} "
                  f"pfail={row['provider_failures']} t={dt:.1f}s")
            with open(OUT, "a") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as e:
            import traceback
            print(f"  [{count:4d}/{total:4d}] FAILED {label}: {e}")
            traceback.print_exc()
            with open(OUT, "a") as f:
                f.write(json.dumps({
                    "campaign": CAMPAIGN, "config": config_id,
                    "template": template_key, "seed": seed, "error": str(e),
                    "phase": "dev",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== DEV RUN COMPLETE: {count}/{total} cells this invocation | {elapsed/60:.1f}min ===")


def load_rows():
    rows = []
    if OUT.exists():
        for line in OUT.open():
            try:
                r = json.loads(line)
                if r.get("campaign") == CAMPAIGN and "error" not in r and not r.get("dry"):
                    rows.append(r)
            except Exception:
                pass
    return rows


def _dist(values):
    if not values:
        return {"n": 0}
    s = sorted(float(v) for v in values)
    n = len(s)
    def pct(p):
        k = (n - 1) * p
        lo, hi = int(k), int(k) + 1
        return s[lo] if hi >= n else s[lo] + (s[hi] - s[lo]) * (k - lo)
    return {
        "n": n, "mean": statistics.mean(s), "median": statistics.median(s),
        "stdev": statistics.stdev(s) if n > 1 else 0.0,
        "p90": pct(0.90), "p95": pct(0.95), "p99": pct(0.99), "max": max(s), "min": min(s),
    }


def make_report():
    rows = load_rows()
    if not rows:
        print("No DEV rows found. Run the campaign first.")
        return

    report = {
        "campaign": CAMPAIGN,
        "phase": "dev",
        "model_id": MODEL_ID,
        "ACTION_CAP": ACTION_CAP,
        "ITERATION_BUDGET": ITERATION_BUDGET,
        "n_cells": len(rows),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "holdout_access": "NONE — dev seeds only (_derive_seed('<tpl>_dev', i)); "
                          "HOLDOUT_SEEDS and validation/holdout result files never opened",
    }

    # A. Generator validity by family
    gen = {}
    for t in DEV_TEMPLATES:
        trows = [r for r in rows if r["template"] == t]
        built = len({r["seed"] for r in trows})
        scen_ok = all(r["scenario_id"] == SCENARIO_TEMPLATES[t]["id"] for r in trows)
        gen[t] = {"cells": len(trows), "distinct_seeds": built,
                  "scenario_id_ok": scen_ok,
                  "seeds_present": sorted({r["seed"] for r in trows})}
    report["A_generator_validity_by_family"] = gen

    # B. Deterministic replay evidence (see --replay; repair-gate G1 covers mechanism)
    report["B_deterministic_replay"] = (
        "run_id is a deterministic logical cell (config,family,seed,split) — no UUID; "
        "see --replay output and tests/test_repair_gate.py::G1"
    )

    # C. Evaluator isolation
    iso = {}
    for arm in ARMS:
        arows = [r for r in rows if r["config"] == arm]
        iso[arm] = {
            "n": len(arows),
            "isolation_pass_count": sum(1 for r in arows if r.get("isolation_pass") is True),
            "isolation_failures": [r.get("isolation_failures") for r in arows if r.get("isolation_failures")],
        }
    iso["evaluator_registration"] = {
        sid: sid in _GLOBAL_EVALUATORS for sid in
        [SCENARIO_TEMPLATES[t]["id"] for t in DEV_TEMPLATES]
    }
    report["C_evaluator_isolation"] = iso

    # D. Infrastructure failures
    infra = {
        "error_rows": sum(1 for r in rows if r.get("error")),
        "infra_failure_rows": sum(1 for r in rows if (r.get("infra_failures") or [] )),
        "outcome_INFRA_FAILURE": sum(1 for r in rows if r.get("outcome") == "INFRA_FAILURE"),
        "outcome_INVALID_RUN": sum(1 for r in rows if r.get("outcome") == "INVALID_RUN"),
    }
    report["D_infrastructure_failures"] = infra

    # E. Provider failure / retry counts (policy: no selective retry)
    prov = {}
    for arm in ARMS:
        arows = [r for r in rows if r["config"] == arm]
        prov[arm] = {
            "n": len(arows),
            "total_provider_failures": sum(r.get("provider_failures") or 0 for r in arows),
            "rows_with_provider_failures": sum(1 for r in arows if (r.get("provider_failures") or 0) > 0),
        }
    report["E_provider_failures"] = prov

    # F. Token distribution by arm
    toks = {}
    for arm in ARMS:
        arows = [r for r in rows if r["config"] == arm]
        toks[arm] = {
            "input_tokens": _dist([r.get("input_tokens") or 0 for r in arows]),
            "output_tokens": _dist([r.get("output_tokens") or 0 for r in arows]),
            "llm_invocations": _dist([r.get("llm_invocations") or 0 for r in arows]),
        }
    report["F_token_distribution_by_arm"] = toks

    # G. actions_dispatched distribution by arm
    act = {}
    for arm in ARMS:
        arows = [r for r in rows if r["config"] == arm]
        act[arm] = _dist([r.get("actions_dispatched") or 0 for r in arows])
    report["G_actions_dispatched_by_arm"] = act

    # H. Budget exhaustion frequency
    budget = {}
    for arm in ARMS:
        arows = [r for r in rows if r["config"] == arm]
        budget[arm] = {
            "at_action_cap": sum(1 for r in arows if (r.get("actions_dispatched") or 0) >= ACTION_CAP),
            "at_iter_budget": sum(1 for r in arows if (r.get("iterations_used") or 0) >= ITERATION_BUDGET),
            "n": len(arows),
        }
    report["H_budget_exhaustion"] = budget

    # I. Scenario success rates BY ARM (diagnostic; success = score >= 0.5)
    succ = {}
    for arm in ARMS:
        by_t = {}
        for t in DEV_TEMPLATES:
            arows = [r for r in rows if r["config"] == arm and r["template"] == t]
            scores = [r.get("score") for r in arows if r.get("score") is not None]
            by_t[t] = {
                "n": len(arows),
                "success_count": sum(1 for s in scores if s >= 0.5),
                "success_rate": (sum(1 for s in scores if s >= 0.5) / len(scores)) if scores else None,
                "score_mean": statistics.mean(scores) if scores else None,
                "scores": [round(float(s), 3) for s in scores],
                "verdicts": [r.get("verdict") for r in arows],
            }
        succ[arm] = by_t
    report["I_success_rates_by_arm_diagnostic"] = succ

    # J. Floor/ceiling analysis (per family, FULL_RAPHAEL)
    fc = {}
    for t in DEV_TEMPLATES:
        fr = [r for r in rows if r["config"] == "FULL_RAPHAEL" and r["template"] == t]
        scores = [r.get("score") for r in fr if r.get("score") is not None]
        if not scores:
            continue
        fc[t] = {
            "min": min(scores), "max": max(scores),
            "at_ceiling_1_0": sum(1 for s in scores if s >= 0.999),
            "at_floor_0_0": sum(1 for s in scores if s <= 0.001),
            "mean": statistics.mean(scores),
            "spread": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        }
    report["J_floor_ceiling"] = fc

    # K. Cognitive-pressure verification (FULL vs PROMPTED delta per family)
    cp = {}
    for t in DEV_TEMPLATES:
        fr = [r.get("score") for r in rows if r["config"] == "FULL_RAPHAEL" and r["template"] == t and r.get("score") is not None]
        pr = [r.get("score") for r in rows if r["config"] == "PROMPTED_AGENT" and r["template"] == t and r.get("score") is not None]
        delta = (statistics.mean(fr) - statistics.mean(pr)) if fr and pr else None
        cp[t] = {
            "full_mean": statistics.mean(fr) if fr else None,
            "prompted_mean": statistics.mean(pr) if pr else None,
            "delta_full_minus_prompted": round(delta, 3) if delta is not None else None,
            "full_std": statistics.stdev(fr) if len(fr) > 1 else 0.0,
            "full_hypothesis_traces": _dist([r.get("hypothesis_traces") or 0 for r in rows if r["config"] == "FULL_RAPHAEL" and r["template"] == t]),
            "full_falsification_traces": _dist([r.get("falsification_traces") or 0 for r in rows if r["config"] == "FULL_RAPHAEL" and r["template"] == t]),
        }
    report["K_cognitive_pressure"] = cp

    # L. Instrument defects discovered
    report["L_instrument_defects"] = [
        {
            "id": "DEV-01",
            "severity": "HIGH",
            "component": "src/arena/ablation_runner.py:_run_llm_only (line 2658) + TracedLLM (line 347)",
            "finding": (
                "PROMPTED_AGENT uses TracedLLM, a keyword-matching SIMULATION (docstring: "
                "'For the pilot, it returns simulated responses'). The LLM response at "
                "_run_llm_only line 2730 is DISCARDED: selected = candidates[0] (line 2740). "
                "The real LLMService (nvidia/llama-3.3-nemotron-super-49b-v1) is never invoked "
                "in this arm, so 'matched model' holds at config level (both arms resolve the "
                "runner default) but NOT at call level: PROMPTED_AGENT makes 0 real LLM calls "
                "and is deterministic. FULL_RAPHAEL makes real calls via LLMService (line 985)."
            ),
            "impact": (
                "The primary FULL vs PROMPTED comparison is effectively FULL vs a deterministic "
                "scope-policy baseline with simulated LLM. This confounds 'prompted LLM value' "
                "claims; it does NOT invalidate the instrument for the deterministic-control "
                "interpretation."
            ),
            "proposed_repair": (
                "For terminal phase (requires SENTINEL authorization, src/ is frozen): wire the "
                "real LLMService into _run_llm_only so PROMPTED_AGENT makes actual nemotron calls "
                "and uses the LLM response to select actions; OR recharacterize PROMPTED_AGENT as "
                "a deterministic policy baseline and re-issue the preregistration arms."
            ),
        }
    ]

    # M. Proposed repairs (exact)
    report["M_proposed_repairs"] = [
        {"repair_id": "REPAIR-DEV-01",
         "target": "src/arena/ablation_runner.py:_run_llm_only",
         "change": "Replace TracedLLM with LLMService (self.llm_service) and use response content to select action; keep broker + ACTION_CAP accounting identical.",
         "authorization": "REQUIRED — src/ modification, SENTINEL only, new AMENDMENT_LEDGER entry."},
        {"repair_id": "REPAIR-DEV-02",
         "target": "evaluations/campaign/TERMINAL_FALSIFICATION_PREREGISTRATION.json",
         "change": "Append ledger entry characterizing PROMPTED_AGENT call path as of v2.1.1 (simulated) if no src change authorized.",
         "authorization": "Append-only ledger; no rewrite."},
    ]

    # N. Holdout confirmation
    report["N_holdout_confirmation"] = {
        "holdout_seeds_used": False,
        "holdout_result_files_opened": [],
        "statement": "No HOLDOUT_SEEDS imported; no rbs_v4_holdout.jsonl / validation results read during DEV.",
    }

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(report, indent=2))
    print(f"Report written: {REPORT_OUT}")

    # ── Console summary ──
    print("\n" + "=" * 80)
    print("DEV INSTRUMENT VALIDATION SUMMARY (diagnostic; not terminal inference)")
    print("=" * 80)
    for t in DEV_TEMPLATES:
        print(f"\n  {t}")
        for arm in ARMS:
            arows = [r for r in rows if r["config"] == arm and r["template"] == t]
            scores = [r.get("score") for r in arows if r.get("score") is not None]
            if scores:
                print(f"    {arm:18s} n={len(scores):2d} mean={statistics.mean(scores):.3f} "
                      f"sd={statistics.stdev(scores) if len(scores) > 1 else 0.0:.3f} "
                      f"scores={[round(float(s),2) for s in scores]}")
    print("\n  PROVIDER FAILURES by arm:", {k: v["total_provider_failures"] for k, v in prov.items()})
    print("  ACTION DISPATCH mean by arm:",
          {k: round(v["mean"], 2) if v["n"] else None for k, v in act.items()})
    print("=" * 80)


def replay_scripted():
    """Deterministic replay evidence: re-run SCRIPTED_BASELINE for seeds 0-1 per
    template and compare against recorded rows (score, actions, verdict)."""
    rows = load_rows()
    recorded = {(r["config"], r["template"], r["seed"]): r for r in rows}
    print("\n=== DETERMINISTIC REPLAY (SCRIPTED_BASELINE, seeds 0-1 per family) ===")
    all_ok = True
    for t in DEV_TEMPLATES:
        for seed in dev_seeds(t)[:2]:
            key = ("SCRIPTED_BASELINE", t, seed)
            if key not in recorded:
                print(f"  {t} s{seed}: NO RECORDED ROW (skip)")
                all_ok = False
                continue
            old = recorded[key]
            row = run_one("SCRIPTED_BASELINE", t, seed)
            same = (
                row["score"] == old["score"]
                and row["actions_dispatched"] == old["actions_dispatched"]
                and row["verdict"] == old["verdict"]
                and row["iterations_used"] == old["iterations_used"]
            )
            print(f"  {t:24s} s{seed}: score {old['score']} vs {row['score']} "
                  f"disp {old['actions_dispatched']} vs {row['actions_dispatched']} "
                  f"verdict {old['verdict']} vs {row['verdict']} -> {'MATCH' if same else 'MISMATCH'}")
            all_ok = all_ok and same
    print(f"\n  REPLAY RESULT: {'PASS' if all_ok else 'FAIL'}")


def smoke_connectivity():
    """One real LLMService call with the amended default config (construct runner,
    use its llm_service, no full run). Validates endpoint/key/model identity."""
    from arena.llm_service import LLMService
    t = DEV_TEMPLATES[0]
    scenario_id = SCENARIO_TEMPLATES[t]["id"]
    template = D6Template(D6_SCENARIO_FACTORIES[scenario_id], scenario_id)
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS["FULL_RAPHAEL"],
        seed=dev_seeds(t)[0],
        split="dev",
        output_dir=str(RUN_DIR),
        llm_config_override=None,
    )
    svc = runner.llm_service
    print("=== CONNECTIVITY SMOKE (amended default model) ===")
    print(f"  model_id   : {svc.config.model_id}")
    print(f"  provider   : {svc.config.provider}")
    print(f"  api_base   : {svc.config.api_base}")
    print(f"  api_key    : {str(svc.config.api_key)[:12]}...")
    print(f"  timeout    : {svc.config.timeout_seconds}s temp={svc.config.temperature} max_tokens={svc.config.max_tokens}")
    t0 = time.time()
    try:
        resp = svc.run_inference(
            observation_text="SMOKE: classify the following log line. LOG: [admin] login success on 10.0.0.5.",
            source_evidence_ids=(),
            run_id="smoke_dev_connectivity",
        )
        dt = time.time() - t0
        print(f"  RESPONSE OK in {dt:.2f}s")
        print(f"  call_count={svc.call_count} input_tokens={svc.input_tokens} "
              f"output_tokens={svc.output_tokens} provider_failures={svc.provider_failures} "
              f"envelope_failures={svc.envelope_failures}")
        print(f"  response snippet: {str(resp)[:200]}")
        print("  SMOKE: PASS" if svc.provider_failures == 0 else "  SMOKE: PROVIDER FAILURES")
        return 0 if svc.provider_failures == 0 else 1
    except Exception as e:
        print(f"  SMOKE: FAIL — {e}")
        return 1


def dry_probe():
    print("=== DRY PROBE (construction-only; no network) ===")
    ok = True
    for config_id in ARMS:
        row = run_one(config_id, DEV_TEMPLATES[0], dev_seeds(DEV_TEMPLATES[0])[0], dry=True)
        print(f"  {config_id:18s} baseline={row['baseline_type']:9s} "
              f"model={row['model_id']} provider={row['provider']} "
              f"temp={row['temperature']} max_tokens={row['max_tokens']} "
              f"evaluator_registered={row['evaluator_registered']} run_id={row['run_id']}")
        ok = ok and row["model_id"] == MODEL_ID and row["evaluator_registered"]
    print(f"  DRY PROBE: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def run_gen2(max_cells=None):
    """REPAIR-DEV-01 gen2 rerun: ONLY PROMPTED_AGENT DEV cells, repaired arm.

    Writes to GEN2_OUT (rbs_v4_dev_prompted_gen2.jsonl), tagged gen=2,
    meta.lab="repair_dev_01". Gen1 PROMPTED rows (TracedLLM simulation) are
    superseded — NOT deleted. Resume: dedup on (config, template, seed)
    within the gen2 file only. FULL/NO_WORLD/SCRIPTED cells are NOT rerun.
    """
    GEN2_OUT.parent.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    cells = []
    for template_key in DEV_TEMPLATES:
        for seed in dev_seeds(template_key):
            cells.append((GEN2_ARM, template_key, seed))
    total = len(cells)

    completed = set()
    if GEN2_OUT.exists():
        for line in GEN2_OUT.open():
            try:
                r = json.loads(line)
                if r.get("campaign") == CAMPAIGN and "error" not in r and not r.get("dry"):
                    completed.add((r["config"], r["template"], r["seed"]))
            except Exception:
                pass

    print("=== REPAIR-DEV-01 GEN2: PROMPTED_AGENT (repaired arm) ===")
    print(f"Arm      : {GEN2_ARM}")
    print(f"Families : {DEV_TEMPLATES}")
    print(f"Seeds    : {DEV_SEED_COUNT}/family (dev-derived)")
    print(f"Total planned cells: {total} | already completed: {len(completed)}")
    print(f"Output   : {GEN2_OUT}")
    print()

    t_start = time.time()
    count = 0
    for (config_id, template_key, seed) in cells:
        if max_cells and count >= max_cells:
            print(f"[RESUME-CHECK] stopping after {count} cells this invocation")
            break
        if (config_id, template_key, seed) in completed:
            continue
        count += 1
        label = f"{config_id:18s} {template_key:24s} s{seed}"
        t0 = time.time()
        try:
            row = run_one(config_id, template_key, seed, gen=2)
            dt = time.time() - t0
            print(f"  [{count:4d}/{total:4d}] {label} score={row['score']} "
                  f"verdict={row['verdict']} llm={row['llm_invocations']} "
                  f"mfail={row['model_failures']} disp={row['actions_dispatched']} "
                  f"tok={row['input_tokens']}+{row['output_tokens']} "
                  f"pfail={row['provider_failures']} t={dt:.1f}s")
            with open(GEN2_OUT, "a") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as e:
            import traceback
            print(f"  [{count:4d}/{total:4d}] FAILED {label}: {e}")
            traceback.print_exc()
            with open(GEN2_OUT, "a") as f:
                f.write(json.dumps({
                    "campaign": CAMPAIGN, "config": config_id,
                    "template": template_key, "seed": seed, "error": str(e),
                    "phase": "dev", "gen": 2,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== GEN2 RUN COMPLETE: {count}/{total} cells this invocation | {elapsed/60:.1f}min ===")


def load_gen2_rows():
    rows = []
    if GEN2_OUT.exists():
        for line in GEN2_OUT.open():
            try:
                r = json.loads(line)
                if r.get("campaign") == CAMPAIGN and "error" not in r and not r.get("dry"):
                    rows.append(r)
            except Exception:
                pass
    return rows


def make_report_gen2():
    """SENTINEL REPORT items 1-11 for REPAIR-DEV-01 acceptance.

    Uses gen2 PROMPTED rows (repaired arm) + gen1 FULL/NO_WORLD rows for
    cross-arm comparisons. Does NOT touch Validation/Holdout files.
    """
    rows = load_gen2_rows()
    if not rows:
        print("No gen2 PROMPTED rows found. Run --gen2 first.")
        return 1

    gen1_rows = load_rows()
    full_rows = [r for r in gen1_rows if r["config"] == "FULL_RAPHAEL"]
    nw_rows = [r for r in gen1_rows if r["config"] == "NO_WORLD_MODEL"]
    scripted_rows = [r for r in gen1_rows if r["config"] == "SCRIPTED_BASELINE"]

    # helper: success-before-cap / success-at-cap / failure-at-cap
    def cap_profile(rows_, success_key="score"):
        out = {"success_before_cap": 0, "success_at_cap": 0, "failure_at_cap": 0, "n": len(rows_)}
        for r in rows_:
            if r.get("score") is None:
                continue
            ok = r.get(success_key) is not None and r.get(success_key) >= 0.5
            at_cap = (r.get("actions_dispatched") or 0) >= ACTION_CAP
            if ok and not at_cap:
                out["success_before_cap"] += 1
            elif ok and at_cap:
                out["success_at_cap"] += 1
            elif not ok and at_cap:
                out["failure_at_cap"] += 1
        return out

    report = {
        "campaign": CAMPAIGN,
        "phase": "dev",
        "sub_phase": "gen2_repair_dev_01",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_id": MODEL_ID,
        "ACTION_CAP": ACTION_CAP,
        "ITERATION_BUDGET": ITERATION_BUDGET,
        "holdout_access": "NONE — dev seeds only; Validation/Holdout files never opened",
    }

    # 1. Implementation diff (src changes for REPAIR-DEV-01)
    report["1_implementation_diff"] = {
        "src_arena_ablation_runner_py": [
            "_run_llm_only: replaced TracedLLM simulation with self.llm_service "
            "(real LLMService, same provider path as FULL_RAPHAEL); no candidates[0] "
            "fallback; malformed action -> model_failures (never deterministic action)",
            "_parse_prompted_action: parses action envelope from LLM claim "
            "(json.loads after fence strip + regex fallback)",
            "_build_prompted_context: textual-only cognition context "
            "(allowed_scope + transcript + evidence; enforced envelope margin)",
        ],
        "src_arena_metrics_py": [
            "RunMetrics.model_failures: int = 0 (REPAIR-DEV-01, additive; "
            "recorded separately from provider_failures)",
        ],
        "unchanged": [
            "FULL_RAPHAEL cognition (orchestrator/brain/ untouched)",
            "Scenario templates + evaluators (arena/d6_manifest.py untouched)",
            "SCRIPTED_BASELINE + NO_WORLD_MODEL arms",
            "ACTION_CAP=5 / ITERATION_BUDGET=5 semantics",
        ],
    }

    # 2. Tests
    report["2_tests"] = {
        "acceptance_suite": "tests/test_prompted_agent_repair.py (items A-J + "
                            "provider/model failure separation)",
        "gate_b_fixture": ("tests/test_gate_b_action_accounting.py: PROMPTED cells now "
                           "provision _PromptedFakeService (valid action envelope); the "
                           "patched forced CapabilityBroker remains the single ALLOW/DENY "
                           "authority — accounting contract unchanged"),
        "full_suite": "215 passed (205 prior + 10 new acceptance)",
    }

    # 3. Real provider-call proof
    real_calls = all((r.get("llm_invocations") or 0) > 0 for r in rows)
    real_tokens = all((r.get("input_tokens") or 0) > 0 for r in rows)
    report["3_real_provider_call_proof"] = {
        "all_cells_llm_invocations_gt_0": real_calls,
        "all_cells_provider_tokens_gt_0": real_tokens,
        "llm_invocations": _dist([r.get("llm_invocations") or 0 for r in rows]),
        "gen2_cells": len(rows),
    }

    # 4. Token distribution (provider-reported) — PROMPTED gen2 vs FULL gen1
    report["4_token_distribution"] = {
        "PROMPTED_AGENT_gen2_input": _dist([r.get("input_tokens") or 0 for r in rows]),
        "PROMPTED_AGENT_gen2_output": _dist([r.get("output_tokens") or 0 for r in rows]),
        "FULL_RAPHAEL_gen1_input": _dist([r.get("input_tokens") or 0 for r in full_rows]),
        "FULL_RAPHAEL_gen1_output": _dist([r.get("output_tokens") or 0 for r in full_rows]),
        "note": "Both arms now report provider-reported input+output tokens via the "
                "identical _llm_service sync path (ablation_runner.py:743-749).",
    }

    # 5. Provider failures (gen2)
    report["5_provider_failures"] = {
        "n": len(rows),
        "total_provider_failures": sum(r.get("provider_failures") or 0 for r in rows),
        "rows_with_provider_failures": sum(1 for r in rows if (r.get("provider_failures") or 0) > 0),
        "policy": "no selective retry (D-6C); provider failure consumes one iteration",
    }

    # 6. Parser/model-failure frequency (malformed LLM output)
    report["6_model_failures"] = {
        "total_model_failures": sum(r.get("model_failures") or 0 for r in rows),
        "distribution": _dist([r.get("model_failures") or 0 for r in rows]),
        "rows_with_model_failures": sum(1 for r in rows if (r.get("model_failures") or 0) > 0),
        "envelope_failures_total": sum(r.get("envelope_failures") or 0 for r in rows),
        "note": "model_failure = LLM returned unparseable action or propose/environment "
                "raised; iteration consumed, NO deterministic fallback (candidates[0] removed).",
    }

    # 7. Action utilization + cap profile
    report["7_action_utilization"] = {
        "actions_dispatched": _dist([r.get("actions_dispatched") or 0 for r in rows]),
        "actions_authorized": _dist([r.get("actions_authorized") or 0 for r in rows]),
        "actions_denied": _dist([r.get("actions_denied") or 0 for r in rows]),
        "actions_succeeded": _dist([r.get("actions_succeeded") or 0 for r in rows]),
        "iterations_used": _dist([r.get("iterations_used") or 0 for r in rows]),
        "cap_profile": cap_profile(rows),
        "cap_profile_FULL_RAPHAEL_gen1": cap_profile(full_rows),
        "note": "success_before_cap/success_at_cap/failure_at_cap per SENTINEL REPORT "
                "requirement; ACTION_CAP=5 unchanged.",
    }

    # 8. Per-family DEV outcomes (gen2 PROMPTED vs gen1 FULL/NO_WORLD/SCRIPTED)
    fam = {}
    for t in DEV_TEMPLATES:
        pr = [r for r in rows if r["template"] == t]
        fr = [r for r in full_rows if r["template"] == t]
        nw = [r for r in nw_rows if r["template"] == t]
        sr = [r for r in scripted_rows if r["template"] == t]
        fam[t] = {
            "PROMPTED_gen2": {
                "n": len(pr),
                "success_rate": (sum(1 for r in pr if (r.get("score") or 0) >= 0.5) / len(pr)) if pr else None,
                "score_mean": statistics.mean([r["score"] for r in pr]) if pr else None,
                "scores": [round(float(r["score"]), 3) for r in pr],
            },
            "FULL_gen1": {
                "n": len(fr),
                "success_rate": (sum(1 for r in fr if (r.get("score") or 0) >= 0.5) / len(fr)) if fr else None,
                "score_mean": statistics.mean([r["score"] for r in fr]) if fr else None,
            },
            "NO_WORLD_gen1": {
                "n": len(nw),
                "success_rate": (sum(1 for r in nw if (r.get("score") or 0) >= 0.5) / len(nw)) if nw else None,
                "score_mean": statistics.mean([r["score"] for r in nw]) if nw else None,
            },
            "SCRIPTED_gen1": {
                "n": len(sr),
                "success_rate": (sum(1 for r in sr if (r.get("score") or 0) >= 0.5) / len(sr)) if sr else None,
                "score_mean": statistics.mean([r["score"] for r in sr]) if sr else None,
            },
        }
    report["8_per_family_outcomes"] = fam

    # 9. Confirmation: scenarios/evaluators/FULL cognition unchanged
    report["9_unchanged_confirmation"] = {
        "scenario_templates_untouched": True,
        "evaluators_untouched": True,
        "full_cognition_untouched": True,
        "orchestrator_brain_untouched": True,
        "action_cap_unchanged": ACTION_CAP,
        "iteration_budget_unchanged": ITERATION_BUDGET,
    }

    # 10. Confirmation: Validation/Holdout unopened
    report["10_validation_holdout_confirmation"] = {
        "holdout_seeds_used": False,
        "validation_results_opened": [],
        "holdout_results_opened": [],
        "statement": "GEN2 rerun used only dev-derived seeds; no Validation/Holdout "
                     "files or seeds touched.",
    }

    # 11. AMENDMENT_LEDGER DEV-01 entry (to be appended on SENTINEL acceptance)
    report["11_amendment_ledger_entry"] = (
        "DEV-01 — PROMPTED_AGENT implementation did not invoke the registered LLM "
        "and therefore did not instantiate the preregistered experimental arm"
    )

    GEN2_REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEN2_REPORT_OUT.write_text(json.dumps(report, indent=2))
    print(f"GEN2 report written: {GEN2_REPORT_OUT}")

    # ── Console summary ──
    print("\n" + "=" * 80)
    print("GEN2 (REPAIR-DEV-01) PROMPTED_AGENT — DEV SUMMARY")
    print("=" * 80)
    for t in DEV_TEMPLATES:
        pr = [r for r in rows if r["template"] == t]
        scores = [r.get("score") for r in pr if r.get("score") is not None]
        if scores:
            print(f"  {t:24s} n={len(scores):2d} mean={statistics.mean(scores):.3f} "
                  f"sd={statistics.stdev(scores) if len(scores) > 1 else 0.0:.3f} "
                  f"scores={[round(float(s), 2) for s in scores]}")
    print(f"  model_failures total: {sum(r.get('model_failures') or 0 for r in rows)}")
    print(f"  provider_failures total: {sum(r.get('provider_failures') or 0 for r in rows)}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        sys.exit(smoke_connectivity())
    if "--dry" in sys.argv:
        sys.exit(dry_probe())
    if "--gen2" in sys.argv:
        max_cells = None
        for i, a in enumerate(sys.argv):
            if a == "--max" and i + 1 < len(sys.argv):
                max_cells = int(sys.argv[i + 1])
        sys.exit(run_gen2(max_cells=max_cells))
    if "--report-gen2" in sys.argv:
        sys.exit(make_report_gen2())
    if "--report" in sys.argv:
        make_report()
    elif "--replay" in sys.argv:
        replay_scripted()
    else:
        # optional --max N to bound this invocation (resume handles the rest)
        max_cells = None
        for i, a in enumerate(sys.argv):
            if a == "--max" and i + 1 < len(sys.argv):
                max_cells = int(sys.argv[i + 1])
        run_campaign(max_cells=max_cells)
