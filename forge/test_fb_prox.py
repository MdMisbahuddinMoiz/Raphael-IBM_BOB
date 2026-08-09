"""Direct test: forbidden-proximity s=0 fallback firing + exception check."""
import sys, json, re, traceback
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r")

from arena.ablation_runner import AblationRunner
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS
from arena.semantic_inference import LLMProviderConfig
from arena import conclusion_adapters as ca

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

template = TEMPLATE_REGISTRY["forbidden-proximity"]
runner = AblationRunner(
    template=template,
    config=ABLATION_PRESETS["PROMPTED_AGENT"],
    seed=0,
    split="holdout",
    llm_config_override=LLM_CONFIG,
)
runner.run()

evs = runner.arena_runner.evidence_graph.get_all_evidence()
mis = [e for e in evs if getattr(e, "evidence_type", "") == "model_inference"]
print("mi:", len(mis))
for e in mis:
    print("  payload:", (getattr(e, "raw_content", "") or "")[:200])

# Direct parser call on the actual graph (bypasses adapter)
all_ids = tuple(e.evidence_id for e in evs)
claims = ca._parse_fallback_heuristic(runner.arena_runner.evidence_graph, all_ids)
print("\ndirect fallback claims:", len(claims))
for c in claims:
    prov = getattr(c, "provenance", None)
    print("  ", c.predicate.value, getattr(c, "object_value", None),
          "| dt=", getattr(prov, "derivation_type", None))

# Replicate parser body with exception surfaced
try:
    import re as _re
    all_ev = runner.arena_runner.evidence_graph.get_all_evidence()
    inf = [ev for ev in all_ev if getattr(ev, 'evidence_type', '') == 'model_inference']
    for ev in inf:
        content = getattr(ev, 'raw_content', '') or ''
        try:
            jd = json.loads(content)
        except Exception:
            jd = None
        if not jd:
            continue
        claim_lower = (jd.get("claim", "") or "").lower()
        print("  claim_lower:", claim_lower[:120])
        m = _re.findall(r'(?:runs?\s+an?\s+[\w-]+\s+service\s+)?on\s+port\s+(\d+)', claim_lower)
        print("    on-port match:", m)
except Exception:
    traceback.print_exc()
