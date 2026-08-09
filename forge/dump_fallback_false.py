"""Inspect model phrasing in the 4 fallback=False samples."""
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

for tkey, seed in [("false-lead", 0), ("forbidden-proximity", 0),
                   ("known-observable", 0), ("signal-noise", 0)]:
    print("\n" + "#" * 70)
    print(f"# {tkey} seed={seed}")
    template = TEMPLATE_REGISTRY[tkey]
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS["PROMPTED_AGENT"],
        seed=seed,
        split="holdout",
        llm_config_override=LLM_CONFIG,
    )
    runner.run()
    evs = runner.arena_runner.evidence_graph.get_all_evidence()
    mis = [e for e in evs if getattr(e, "evidence_type", "") == "model_inference"]
    seen = set()
    for e in mis:
        rc = getattr(e, "raw_content", "") or ""
        if rc not in seen:
            seen.add(rc)
            print("  payload:", rc[:250])
