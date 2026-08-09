"""Post-D13 payload dump: model_inference content + claim provenance detail."""
import sys, json, re
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r")

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

for tkey, seed in [("contradiction", 0), ("known-observable", 1)]:
    print("\n" + "#" * 70)
    print(f"# {tkey} seed={seed}")
    print("#" * 70)
    template = TEMPLATE_REGISTRY[tkey]
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS["PROMPTED_AGENT"],
        seed=seed,
        split="holdout",
        llm_config_override=LLM_CONFIG,
    )
    runner.run()
    ar = runner.arena_runner
    evs = ar.evidence_graph.get_all_evidence()
    mis = [e for e in evs if getattr(e, "evidence_type", "") == "model_inference"]
    print(f"score={runner.evaluation_result.score if runner.evaluation_result else None} "
          f"outcome={getattr(runner.metrics, 'outcome', None)}")
    print(f"model_inference evidence: {len(mis)}")
    for e in mis:
        print("  payload:", (getattr(e, "raw_content", "") or "")[:400])

    concl = getattr(runner, "_conclusion", None)
    print(f"claims: {len(concl.claims) if concl else 0}")
    if concl:
        for c in concl.claims:
            pred = c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate)
            prov = getattr(c, "provenance", None)
            dt = getattr(prov, "derivation_type", None) if prov else None
            mi = getattr(prov, "model_inference_ids", None) if prov else None
            print(f"  {pred} | dt={dt} "
                  f"| mi_ids={mi} "
                  f"| obj={getattr(c, 'object_value', None)}")
