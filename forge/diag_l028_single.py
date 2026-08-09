"""Diagnostic v4: PROMPTED_AGENT with LIVE LLM override (deepseek-v4-flash-0731).

Frozen default model deepseek-ai/deepseek-v4-flash is EOL (HTTP 410 since
2026-08-07T09:00:00Z). Override supplies the live -0731 snapshot + .env key.
"""
import sys, json, re

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

# Live provider override: read key from .env, model from live catalog
env_text = open("/home/yaser/raphael-2.0-rbsv2r/.env").read()
env_keys = {m.group(1): m.group(2) for m in re.finditer(r"^(NVIDIA_API_KEY[A-Z_]*)=(\S+)", env_text, re.M)}
live_key = env_keys.get("NVIDIA_API_KEY_A") or env_keys.get("NVIDIA_API_KEY_B")

LLM_CONFIG = LLMProviderConfig(
    model_id="deepseek-ai/deepseek-v4-flash-0731",
    provider="nvidia",
    api_base="https://integrate.api.nvidia.com/v1",
    api_key=live_key or "",
    timeout_seconds=30,
    temperature=0.0,
    max_tokens=512,
)

template = TEMPLATE_REGISTRY["contradiction"]
runner = AblationRunner(
    template=template,
    config=ABLATION_PRESETS["PROMPTED_AGENT"],
    seed=0,
    split="holdout",
    llm_config_override=LLM_CONFIG,
)
runner.run()

print("=" * 70)
print("RUN COMPLETE")
print("=" * 70)
print("run_id:", runner.run_id)
print("score:", runner.evaluation_result.score if runner.evaluation_result else None)
print("actions_proposed:", runner.metrics.actions_proposed)
print("metrics.outcome:", getattr(runner.metrics, "outcome", None))
print("outcome_reason:", getattr(runner.metrics, "outcome_reason", None))
print("metrics.llm_calls:", runner.metrics.llm_calls)
print("metrics.provider_failures:", runner.metrics.provider_failures)
ls = getattr(runner, "_llm_service", None)
print("llm_service.call_count:", ls.call_count if ls else None)
print("llm_service.provider_failures:", ls.provider_failures if ls else None)

# Correct object: arena_runner holds the evidence graph
ar = runner.arena_runner
print("\narena_runner exists:", ar is not None)
if ar is not None:
    eg = getattr(ar, "evidence_graph", None)
    print("arena_runner.evidence_graph:", type(eg).__name__ if eg else None)
    if eg is not None:
        evs = eg.get_all_evidence()
        print("evidence count:", len(evs))
        from collections import Counter
        types = Counter(getattr(e, "evidence_type", "?") for e in evs)
        print("evidence types:", dict(types))
        for e in evs[:12]:
            print("  -", getattr(e, "evidence_type", "?"), "|", 
                  getattr(e, "evidence_id", "?")[:24], "|",
                  (getattr(e, "raw_content", "") or "")[:120].replace("\n", " "))

# Conclusion claims from the adapter
concl = getattr(runner, "_conclusion", None)
print("\nconclusion adapter used:", type(concl).__name__ if concl else None)
if concl is not None:
    print("conclusion claims:", len(concl.claims))
    for c in concl.claims[:25]:
        pred = c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate)
        print("  ", pred, "|", getattr(c, "subject_id", "?"), "|", str(c.object_value)[:80])

# Check evaluation result details
ev = runner.evaluation_result
if ev is not None:
    print("\nevaluation passed_checks:", ev.passed_checks)
    print("evaluation failed_checks:", ev.failed_checks)

out = {
    "run_id": runner.run_id,
    "score": ev.score if ev else None,
    "actions": runner.metrics.actions_proposed,
    "evidence_count": len(evs) if (ar and eg) else 0,
    "evidence_types": dict(types) if (ar and eg) else {},
    "llm_calls": runner.metrics.llm_calls,
    "provider_failures": runner.metrics.provider_failures,
    "conclusion_claims": len(concl.claims) if concl else 0,
    "claim_predicates": [
        c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate)
        for c in concl.claims
    ] if concl else [],
}
with open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_SINGLE_DIAG.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nSaved evaluations/campaign/L028_SINGLE_DIAG.json")
