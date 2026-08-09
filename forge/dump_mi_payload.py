"""Dump FULL model_inference evidence payloads from one PROMPTED_AGENT run."""
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

env_text = open("/home/yaser/raphael-2.0-rbsv2r/.env").read()
keys = {m.group(1): m.group(2) for m in re.finditer(r"^(NVIDIA_API_KEY[A-Z_]*)=(\S+)", env_text, re.M)}

LLM_CONFIG = LLMProviderConfig(
    model_id="deepseek-ai/deepseek-v4-flash-0731",
    provider="nvidia",
    api_base="https://integrate.api.nvidia.com/v1",
    api_key=keys.get("NVIDIA_API_KEY_A", ""),
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

ar = runner.arena_runner
eg = ar.evidence_graph
evs = eg.get_all_evidence()
mis = [e for e in evs if getattr(e, "evidence_type", "") == "model_inference"]
print(f"model_inference evidence: {len(mis)}")
for e in mis:
    print("\n" + "-" * 70)
    print("evidence_id:", e.evidence_id)
    print("FULL raw_content:")
    print(getattr(e, "raw_content", "") or "''")

# Also inspect claim derivation details
concl = getattr(runner, "_conclusion", None)
print("\n" + "=" * 70)
print(f"adapter: {type(concl).__name__ if concl else None}, claims: {len(concl.claims) if concl else 0}")
if concl:
    for c in concl.claims:
        print("\nclaim:", c.predicate.value if hasattr(c.predicate, 'value') else c.predicate)
        print("  derivation_type:", getattr(c, "derivation_type", None))
        print("  model_inference_ids:", getattr(c, "model_inference_ids", None))
        print("  supporting_evidence_ids:", getattr(c, "supporting_evidence_ids", None))
        print("  object_value:", getattr(c, "object_value", None))
