#!/usr/bin/env python3
"""
RBS-v4 TERMINAL FALSIFICATION HOLDOUT — 49B (Gate-Passing Model)
=================================================================
Authorized: SENTINEL terminal authorization (AMENDMENT-MODEL-550B-2026-08-09).
550B failed gate (6/10); 49B fallback passed (8/10). Holdout launches on 49B.

Design (frozen; TERMINAL_FALSIFICATION_PREREGISTRATION + TERMINAL_VALIDATION_FREEZE):
  - Families : 5 FRESH architecture-agnostic families
                    known-observable | signal-noise | false-lead | contradiction | forbidden-proximity
  - Arms     : 4 preregistered arms — FULL_RAPHAEL, PROMPTED_AGENT, NO_WORLD_MODEL
                    (network), SCRIPTED_BASELINE (hermetic control)
  - Seeds    : 60 seeds/family = relative 0..59 -> HOLDOUT split absolute 2000..2059
                    (resolve_seed(seed, ScenarioSplit.HOLDOUT); guard abs in [2000, 10000))
  - Runs     : 5 families x 4 arms x 60 seeds = 1,200 cells
  - Budget   : ACTION_CAP = 5, ITERATION_BUDGET = 5 (frozen; d6_manifest.py)
  - Model    : nvidia/llama-3.3-nemotron-super-49b-v1 (49B, gate-passing model)
                    identical provider path for ALL arms (model parity, verified).
  - Evaluator: architecture-blind evaluate_runconclusion for all arms (fresh ids).
  - Prompt   : FROZEN (PROMPTED_PROMPT_FREEZE.json v1.0 record; runtime prompt SHA recorded).
  - Tag      : ALL frozen `instrument_tag = terminal-holdout-49b`.

COLLECTION DISCIPLINE:
  - COLLECT-ONLY. The campaign loop prints experiment HEALTH only: completed count,
    elapsed, provider/model failures, run_id, adapter errors, actions dispatched ceiling.
    It NEVER prints score / verdict / pass-fail / arm-level success rate / cognitive deltas
    during collection. Performance is sealed until collection closes and integrity verifies.

  - A single terminal analysis (verdict A/B/C1/C2/D) runs ONCE, after collection closes
    and integrity verification passes (see separate analysis step --report in scripts/
    run_rbs_v4_holdout_analysis.py, invoked explicitly; NOT reachable during collection).

Paired INFRA VALIDITY policy (frozen):
  - INFRA event (qualifying) = provider_failures > 0 OR non-empty metrics.infra_failures.
  - If ANY network arm in a matched (family, seed) comparison has >=1 qualifying INFRA
    event -> the WHOLE matched comparison is INFRA_INVALID and EXCLUDED from the primary
    FULL-vs-PROMPTED comparison. No selective rerun. No key/model fallback.
  - Handle allowed infra-failure handling per preregistration; NEVER a post-hoc rerun to
    salvage performance. Post-hoc reruns are FORBIDDEN except preregistered infra-handling.

Outputs:
  - evaluations/campaign/rbs_v4_holdout_49b.jsonl      (append-only row log, resumable)
  - evaluations/campaign/holdout_49b_runs/             (per-run dirs via runner.save())
  - NO report during collection.
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
    if not os.path.exists(path):
        logging.warning("missing %s; provider calls will have no credentials and fail as INFRA.", path)
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v.strip()


_here = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_here, ".env")):
    _load_dotenv(os.path.join(_here, ".env"))
_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.templates import TEMPLATE_REGISTRY, ScenarioSplit
from arena.runner import SCENARIO_EVALUATORS as _GLOBAL_EVALUATORS
from arena.d6_manifest import ITERATION_BUDGET

# ── Frozen campaign identity ─────────────────────────────────────────────
MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
CAMPAIGN = "rbs-v4-holdout-49b"
INSTRUMENT_TAG = "terminal-holdout-49b"
PROMPT_FREEZE_SHA = "e9d6a0fdb4a9a5462dd5a8e7d95f82affea082c8bb1aaec887e5b1b89412bb67"  # runtime PROMPTED_AGENT_SYSTEM_PROMPT SHA256

FAMILIES = [
    "known-observable",
    "signal-noise",
    "false-lead",
    "contradiction",
    "forbidden-proximity",
]

ARMS = ["FULL_RAPHAEL", "NO_WORLD_MODEL", "PROMPTED_AGENT", "SCRIPTED_BASELINE"]
NETWORK_ARMS = ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL"]

SEED_COUNT = 60       # relative 0..59 -> HOLDOUT absolute 2000..2059
ACTION_CAP = 5
SPLIT_NAME = "holdout"  # -> ScenarioSplit.HOLDOUT

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v4_holdout_49b.jsonl"
RUN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign" / "holdout_49b_runs"


def _abs_seed(relative: int) -> int:
    from arena.templates.base import resolve_seed
    abs_seed = resolve_seed(relative, ScenarioSplit.HOLDOUT)
    assert 2000 <= abs_seed < 10000, f"HOLD GUARD: abs seed {abs_seed} outside HOLDOUT range"
    return abs_seed


def _world_hash(template, relative_seed: int) -> str:
    from arena.templates.base import resolve_seed
    abs_seed = resolve_seed(relative_seed, ScenarioSplit.HOLDOUT)
    scenario = template.generate(seed=relative_seed, split=ScenarioSplit.HOLDOUT)
    policy = scenario.policy
    canon = {
        "scenario_id": scenario.scenario_id,
        "name": scenario.name,
        "description": scenario.description,
        "allowed_targets": sorted(policy.allowed_targets or []),
        "prohibited_targets": sorted(policy.prohibited_targets or []),
        "allowed_action_types": sorted(policy.allowed_action_types or []),
        "prohibited_action_types": sorted(policy.prohibited_action_types or []),
        "allowed_capabilities": sorted(policy.allowed_capabilities or []),
        "prohibited_capabilities": sorted(policy.prohibited_capabilities or []),
        "starting_assets": scenario.evaluator_truth.get("starting_assets", []),
        "objective": scenario.evaluator_truth.get("objective", ""),
    }
    blob = json.dumps(canon, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _trace_counts(run_dir):
    out = {"llm_invocations": 0, "hypothesis_traces": 0, "falsification_traces": 0,
           "student_traces": 0, "planner_traces": 0, "world_model_traces": 0}
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
    except Exception:
        pass
    return out


def run_one(config_id, family_id, relative_seed):
    template = TEMPLATE_REGISTRY[family_id]
    abs_seed = _abs_seed(relative_seed)
    expected_sid = f"{template.family_id}-s{abs_seed:04d}"

    world_hash = _world_hash(template, relative_seed)
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=relative_seed,
        split=SPLIT_NAME,
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

    evaluator_name = "evaluate_runconclusion"
    if _GLOBAL_EVALUATORS.get(expected_sid) is not None:
        evaluator_name = f"scenario_specific:{expected_sid}"
    from arena.conclusion_adapters import get_adapter
    adapter = get_adapter(config_id)
    adapter_name = type(adapter).__name__
    adapter_error_events = [
        e for e in getattr(runner, "events", []).events
        if e.get("type") == "conclusion_adapter_error"
    ] if getattr(runner, "events", None) else []

    row = {
        "campaign": CAMPAIGN,
        "phase": "holdout",
        "config": config_id,
        "arm": config_id,
        "template": family_id,
        "scenario_id": expected_sid,
        "seed": relative_seed,
        "abs_seed": abs_seed,
        "run_id": runner.run_id,
        "world_hash": world_hash,
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
        "world_model_traces": tc["world_model_traces"],
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
        "infra_failures": m.get("infra_failures") or [],
        "model_failures": m.get("model_failures"),
        "llm_calls": m.get("llm_calls"),
        "decision_outcome": m.get("decision_outcome"),
        "outcome": m.get("outcome"),
        "outcome_reason": m.get("outcome_reason"),
        "safety_pass": safety_pass,
        "safety_failures": safety_failures,
        "isolation_pass": isolation_pass,
        "isolation_failures": isolation_failures,
        "evaluator_name": evaluator_name,
        "adapter_name": adapter_name,
        "adapter_error_events": len(adapter_error_events),
        "model_id": MODEL_ID,
        "provider": "nvidia",
        "prompt_freeze_sha": PROMPT_FREEZE_SHA,
        "instrument_tag": INSTRUMENT_TAG,
        "run_dir": str(run_dir) if run_dir else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _svc = getattr(runner, "_llm_service", None)
    row["envelope_failures"] = getattr(_svc, "envelope_failures", None) if _svc else None
    row["logical_llm_calls"] = getattr(_svc, "logical_llm_calls", None) if _svc else None
    row["provider_attempts"] = getattr(_svc, "provider_attempts", None) if _svc else None
    row["failover_count"] = getattr(_svc, "failover_count", None) if _svc else None
    row["retries_by_key_alias"] = dict(getattr(_svc, "retries_by_key_alias", {}) or {}) if _svc else None
    row["final_key_alias"] = getattr(_svc, "final_key_alias", None) if _svc else None
    row["failure_class"] = getattr(_svc, "failure_class", None) if _svc else None
    row["final_provider_status"] = getattr(_svc, "final_provider_status", None) if _svc else None
    return row


def run_campaign(max_cells=None):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    cells = []
    for family_id in FAMILIES:
        for config_id in ARMS:
            for seed in range(SEED_COUNT):
                cells.append((config_id, family_id, seed))
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

    print("=" * 80)
    print("RBS-v4 TERMINAL HOLDOUT (49B) — COLLECTION-ONLY")
    print("=" * 80)
    print(f"Families : {FAMILIES}")
    print(f"Arms     : {ARMS}")
    print(f"Seeds    : {SEED_COUNT}/family (HOLDOUT split, relative 0-{SEED_COUNT-1} -> abs 2000-{2000+SEED_COUNT-1})")
    print(f"Budget   : ACTION_CAP={ACTION_CAP} ITERATION_BUDGET={ITERATION_BUDGET}")
    print(f"Model    : {MODEL_ID} (gate-passing fallback, per AMENDMENT-MODEL-550B-2026-08-09)")
    print(f"Total planned cells: {total} | already completed: {len(completed)}")
    print(f"Output   : {OUT}")
    print(f"Tag      : {INSTRUMENT_TAG}")
    print(f"Prompt SHA: {PROMPT_FREEZE_SHA}")
    print("DISCIPLINE: health-only telemetry during collection; perf sealed until closure.")
    print()

    t_start = time.time()
    count = 0
    for (config_id, family_id, seed) in cells:
        if max_cells and count >= max_cells:
            print(f"[RESUME-CHECK] stopping after {count} cells this invocation")
            break
        if (config_id, family_id, seed) in completed:
            continue
        count += 1
        label = f"{config_id:18s} {family_id:20s} s{seed}"
        t0 = time.time()
        try:
            row = run_one(config_id, family_id, seed)
            dt = time.time() - t0
            # HEALTH-ONLY progress: completed, provider/model failures, adapter,
            # budget ceiling. Deliberately NO score/verdict print.
            print(f"  [{count:5d}/{total:5d}] {label} "
                  f"pfail={row['provider_failures']} mfail={row['model_failures']} "
                  f"adapter_err={row['adapter_error_events']} "
                  f"disp={row['actions_dispatched']} iter={row['iterations_used']} "
                  f"rid={row['run_id']} t={dt:.1f}s")
            with open(OUT, "a") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as e:
            import traceback
            print(f"  [{count:4d}/{total:4d}] FAILED {label}: {e}")
            traceback.print_exc()
            with open(OUT, "a") as f:
                f.write(json.dumps({
                    "campaign": CAMPAIGN, "config": config_id,
                    "template": family_id, "seed": seed, "error": str(e),
                    "phase": "holdout", "instrument_tag": INSTRUMENT_TAG,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== HOLDOUT COLLECTION: {count}/{total} cells this invocation | {elapsed/60:.1f}min ===")
    print("Collection still running? Sealed until integrity verification passes. Do NOT inspect perf.")


def dry_probe():
    print("=== DRY PROBE (construction-only; no network) ===")
    ok = True
    for config_id in ARMS:
        template = TEMPLATE_REGISTRY[FAMILIES[0]]
        runner = AblationRunner(
            template=template,
            config=ABLATION_PRESETS[config_id],
            seed=0,
            split=SPLIT_NAME,
            output_dir=str(RUN_DIR),
            llm_config_override=None,
        )
        cfg = runner.llm_service.config
        same = (cfg.model_id == MODEL_ID and cfg.provider == "nvidia")
        print(f"  {config_id:18s} model={cfg.model_id} provider={cfg.provider} "
              f"vs {MODEL_ID} -> {same}")
        ok = ok and same
    print(f"  DRY PROBE: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--dry" in sys.argv:
        sys.exit(dry_probe())
    max_cells = None
    for i, a in enumerate(sys.argv):
        if a == "--max" and i + 1 < len(sys.argv):
            max_cells = int(sys.argv[i + 1])
    run_campaign(max_cells=max_cells)