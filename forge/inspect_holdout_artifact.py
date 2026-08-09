"""Inspect existing holdout artifact + instrument details for the fresh launch decision."""
import json, sys
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
CAM = ROOT / "evaluations/campaign"

print("=== A. EXISTING rbs_v4_holdout.jsonl (1200 rows) — WHICH INSTRUMENT? ===")
rows = [json.loads(l) for l in (CAM / "rbs_v4_holdout.jsonl").read_text().splitlines() if l.strip()]
models = {}
tags = {}
seeds = set()
sids = set()
adapters = {}
for r in rows:
    models[r.get("model_id")] = models.get(r.get("model_id"), 0) + 1
    tags[r.get("instrument_tag")] = tags.get(r.get("instrument_tag"), 0) + 1
    seeds.add(r.get("abs_seed"))
    sids.add(r.get("scenario_id"))
    adapters[r.get("adapter_name")] = adapters.get(r.get("adapter_name"), 0) + 1
print("model_id distribution:", models)
print("instrument_tag distribution:", tags)
print("abs seeds:", sorted(seeds)[:3], "...", sorted(seeds)[-3:], "count:", len(seeds))
print("scenario ids:", list(sids)[:3], "...", list(sids)[-1] if sids else None)
print("adapter names:", adapters)
ts = [r.get("timestamp") for r in rows if r.get("timestamp")]
print("timestamps:", min(ts) if ts else None, "->", max(ts) if ts else None)
# any envelope/failover fields populated?
svc_rows = [r for r in rows if r.get("failover_count") is not None]
print("rows with failover telemetry:", len(svc_rows))

print("\n=== B. QUARANTINE FILE (3240 rows) ===")
qrows = [json.loads(l) for l in (CAM / "rbs_v4_holdout_STALE_T1T12_GPTOSS_QUARANTINE.jsonl").read_text().splitlines() if l.strip()]
qmodels = {}
for r in qrows:
    qmodels[r.get("model_id")] = qmodels.get(r.get("model_id"), 0) + 1
print("model_id distribution:", qmodels)
qseeds = set(r.get("abs_seed") for r in qrows)
print("abs seeds count:", len(qseeds), "range:", min(qseeds) if qseeds else None, "-", max(qseeds) if qseeds else None)
print("first row keys:", list(qrows[0].keys())[:20] if qrows else None)

print("\n=== C. PROMPTED_PROMPT_FREEZE.json details ===")
pf = json.load(open(CAM / "PROMPTED_PROMPT_FREEZE.json"))
print("artifact_id:", pf.get("artifact_id"))
print("version:", pf.get("version"), "status:", pf.get("status"))
print("frozen_at_utc:", pf.get("frozen_at_utc"))
print("model:", pf.get("model"), "provider:", pf.get("provider"))
print("implementation_source:", pf.get("implementation_source"))
print("freeze_scope:", json.dumps(pf.get("freeze_scope"), indent=1)[:600])
print("frozen_instruction_block_sha256:", pf.get("frozen_instruction_block_sha256"))
print("prompt_sha (whole file): 935b6caa06de7c3b366c71979e0c753674ab31891750ba4bbae369a171e21eea")

print("\n=== D. does semantic_inference.py load prompt from freeze file? ===")
si = (ROOT / "src/arena/semantic_inference.py").read_text()
import re
for m in re.finditer(r"(PROMPTED_PROMPT_FREEZE|prompt_freeze|freeze)", si):
    line = si[:m.start()].count("\n") + 1
    print(f"line {line}: {si.splitlines()[line-1].strip()[:130]}")
print("--- system prompt location ---")
for m in re.finditer(r"(PROMPTED_AGENT_SYSTEM_PROMPT|ENVELOPE_SYSTEM_PROMPT)\s*=\s*(\"\"\"|\"|f\"\"\")", si):
    line = si[:m.start()].count("\n") + 1
    print(f"line {line}: {m.group(1)}")

print("\n=== E. LLMService failover support? ===")
llm = (ROOT / "src/arena/llm_service.py").read_text()
for pat in ["failover", "KEY_A", "KEY_B", "alternate_key", "api_key_alt", "fallback_key"]:
    hits = [i for i, l in enumerate(llm.splitlines(), 1) if pat.lower() in l.lower()]
    if hits:
        print(f"{pat}: lines {hits[:6]}")
print("llm_transport.py exists:", (ROOT / "src/arena/llm_transport.py").exists())
