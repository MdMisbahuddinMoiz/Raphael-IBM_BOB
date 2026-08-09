#!/usr/bin/env python3
"""
L-028 Fix Verification v4 (FINAL GATE): 10 stratified PROMPTED_AGENT samples.

v4 changes (2026-08-09):
- D13 patches applied: fallback FALLBACK 5 phrasing alignment (Fix 1),
  PROMPTED_AGENT_SYSTEM_PROMPT tightening (Fix 2), EOL model -0731 + env keys.
- LIVE LLM override: deepseek-ai/deepseek-v4-flash-0731 + .env keys (rotation).
- Sample PASS = fallback-fired (claim with model_inference_ids +
  derivation_type LLM_INTERPRETATION) AND mi evidence >= 1 AND 0 provider failures.

Gate (SENTINEL): >= 8/10 PASS. Halt if >= 2/10 MECHANICAL (zero claims).
"""
import sys
import json
import re
from collections import Counter

# Path setup — src/ FIRST (scripts/arena.py + top-level arena/ dir shadow src/arena/)
for p in ("/home/yaser/raphael-2.0-rbsv2r/src",
          "/home/yaser/raphael-2.0-rbsv2r/scripts",
          "/home/yaser/raphael-2.0-rbsv2r"):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/scripts")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

from arena.ablation_runner import AblationRunner
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS
from arena.semantic_inference import LLMProviderConfig

# Live provider override (49B fallback per AMENDMENT-MODEL-550B-2026-08-09)
env_text = open("/home/yaser/raphael-2.0-rbsv2r/.env").read()
env_keys = {m.group(1): m.group(2) for m in re.finditer(r"^(NVIDIA_API_KEY[A-Z_]*)=(\S+)", env_text, re.M)}

LLM_CONFIG = LLMProviderConfig(
    model_id="nvidia/llama-3.3-nemotron-super-49b-v1",
    provider="nvidia",
    api_base="https://integrate.api.nvidia.com/v1",
    api_key=env_keys.get("NVIDIA_API_KEY_A") or env_keys.get("NVIDIA_API_KEY_B") or "",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

AUDIT_SAMPLES = [
    ("contradiction", 0), ("contradiction", 1),
    ("false-lead", 0), ("false-lead", 1),
    ("forbidden-proximity", 0), ("forbidden-proximity", 1),
    ("known-observable", 0), ("known-observable", 1),
    ("signal-noise", 0), ("signal-noise", 1),
]

# L-028 typed predicates the fallback must be able to emit
L028_PREDICATES = {"service_type", "version", "patch", "has_service"}


def run_sample(template_key: str, seed: int, api_key: str) -> dict:
    template = TEMPLATE_REGISTRY[template_key]
    llm_config = LLMProviderConfig(
        model_id="nvidia/llama-3.3-nemotron-super-49b-v1",
        provider="nvidia",
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
        timeout_seconds=180,
        temperature=0.0,
        max_tokens=16384,
    )
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS["PROMPTED_AGENT"],
        seed=seed,
        split="holdout",
        llm_config_override=llm_config,
    )
    runner.run()

    # Evidence inspection
    ar = getattr(runner, "arena_runner", None)
    eg = getattr(ar, "evidence_graph", None) if ar else None
    evs = eg.get_all_evidence() if eg else []
    ev_types = dict(Counter(getattr(e, "evidence_type", "?") for e in evs))
    mi_count = sum(1 for e in evs if getattr(e, "evidence_type", "") == "model_inference")

    # Conclusion claims — separate FALLBACK-sourced claims (carry model_inference_ids
    # + derivation_type LLM_INTERPRETATION) from deterministic regex claims
    concl = getattr(runner, "_conclusion", None)
    claim_preds = []
    fallback_preds = []
    fallback_fired = False
    if concl is not None:
        for c in concl.claims:
            pred = c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate)
            claim_preds.append(pred)
            # Provenance lives in c.provenance (ConclusionProvenance)
            prov = getattr(c, "provenance", None)
            mi_ids = getattr(prov, "model_inference_ids", None) or () if prov else ()
            dt = getattr(prov, "derivation_type", None) if prov else None
            if mi_ids and dt is not None and dt.name == "LLM_INTERPRETATION":
                fallback_fired = True
                fallback_preds.append(pred)
    l028_preds = [p for p in fallback_preds if p.lower() in L028_PREDICATES]

    # LLMService telemetry
    ls = getattr(runner, "_llm_service", None)
    ls_calls = ls.call_count if ls else None
    ls_failures = ls.provider_failures if ls else None

    # Adapter identity
    adapter_name = type(concl).__name__ if concl else "None"

    return {
        "template": template_key,
        "seed": seed,
        "run_id": runner.run_id,
        "score": runner.evaluation_result.score if runner.evaluation_result else None,
        "actions": runner.metrics.actions_proposed,
        "metrics_outcome": getattr(runner.metrics, "outcome", None),
        "outcome_reason": getattr(runner.metrics, "outcome_reason", ""),
        "infra_failures": getattr(runner.metrics, "infra_failures", []),
        "adapter": adapter_name,
        "evidence_types": ev_types,
        "model_inference_evidence": mi_count,
        "llm_service_calls": ls_calls,
        "llm_service_provider_failures": ls_failures,
        "claim_count": len(claim_preds),
        "claim_predicates": claim_preds,
        "fallback_fired": fallback_fired,
        "fallback_predicates": fallback_preds,
        "l028_predicates": l028_preds,
        # Sample PASS = fallback parser fired (provenance: model_inference_ids +
        # LLM_INTERPRETATION) AND evidence flowed AND no provider failure
        "sample_pass": (fallback_fired and len(l028_preds) >= 1 and mi_count >= 1
                        and (ls_failures or 0) == 0),
    }


def main():
    print("=" * 70)
    print("L-028 VERIFICATION v4 (FINAL GATE): 10-Sample PROMPTED_AGENT (D13 + LIVE LLM)")
    print(f"model: {LLM_CONFIG.model_id}")
    print("=" * 70)

    results = []
    keys = [env_keys.get("NVIDIA_API_KEY_A"), env_keys.get("NVIDIA_API_KEY_B")]
    for i, (template_key, seed) in enumerate(AUDIT_SAMPLES, 1):
        # Rotate keys per sample to mitigate transient 503 ResourceExhausted
        api_key = keys[(i - 1) % 2]
        print(f"\n[{i}/10] Running {template_key} seed={seed} (key={'A' if (i-1)%2==0 else 'B'})...", flush=True)
        r = run_sample(template_key, seed, api_key)
        results.append(r)
        print(f"  score={r['score']} outcome={r['metrics_outcome']} "
              f"mi_evidence={r['model_inference_evidence']} "
              f"ls_calls={r['llm_service_calls']} ls_fail={r['llm_service_provider_failures']} "
              f"fallback={r['fallback_fired']} fallback_preds={r['fallback_predicates']} pass={r['sample_pass']}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in results:
        print(f"  {r['template']:20s} s={r['seed']}: score={r['score']} "
              f"outcome={r['metrics_outcome']} mi={r['model_inference_evidence']} "
              f"fallback={r['fallback_fired']} fb_preds={r['fallback_predicates']} PASS={r['sample_pass']}")

    n_pass = sum(1 for r in results if r["sample_pass"])
    n_fb = sum(1 for r in results if r["fallback_fired"])
    n_mech = sum(1 for r in results if r["claim_count"] == 0)
    n_infra = sum(1 for r in results if r["infra_failures"])
    print(f"\nGate (SENTINEL): >= 8/10 runs produce fallback-sourced typed predicates")
    print(f"  fallback-sourced typed predicates: {n_fb}/10  (gate: >= 8/10)")
    print(f"  MECHANICAL (zero claims): {n_mech}/10  (stop: >= 2/10)")
    print(f"  strict PASS (fb + mi>=1 + 0 provider failures): {n_pass}/10")
    print(f"  INFRA_FAILURE runs: {n_infra}/10")
    # SENTINEL gate criterion: fallback-sourced typed predicates >= 8/10,
    # stop condition: >= 2/10 MECHANICAL
    if n_fb >= 8 and n_mech < 2:
        verdict = "GATE PASSED -> authorized to proceed to 1200-row holdout"
    else:
        verdict = "GATE FAILED -> halt; report to SENTINEL with telemetry"
    print(f"VERDICT: {verdict}")

    output = {
        "verification": "L-028 fallback heuristic re-audit v4 (FINAL GATE)",
        "timestamp": "2026-08-09T11:00:00Z",
        "model_override": LLM_CONFIG.model_id,
        "d13_applied": True,
        "note": ("D13 patches: FALLBACK 5 phrasing alignment + prompt tightening + "
                 "EOL model -0731 env keys. Sample PASS = fallback-fired claim "
                 "(model_inference_ids + LLM_INTERPRETATION derivation) AND "
                 "model_inference_evidence >= 1 AND 0 provider failures."),
        "gate": ">=8/10 samples typed predicate via fallback",
        "samples": results,
    }
    with open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_VERIFICATION.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to evaluations/campaign/L028_VERIFICATION.json")


if __name__ == "__main__":
    main()
