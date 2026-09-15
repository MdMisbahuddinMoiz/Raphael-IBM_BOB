"""Pre-launch inspection: preregistration contract, seed scheme, prompt freeze sha, run log state."""
import json, hashlib, os
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
CAM = ROOT / "evaluations/campaign"

print("=== 1. PREREGISTRATION CONTRACT ===")
d = json.load(open(CAM / "TERMINAL_FALSIFICATION_PREREGISTRATION.json"))
def walk(o, prefix=""):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{prefix}.{k}")
    elif isinstance(o, list):
        if o and isinstance(o[0], (str, int, float)):
            print(f"{prefix}: {o}")
        else:
            print(f"{prefix}: [list len {len(o)}]")
    else:
        s = str(o)
        if len(s) > 120: s = s[:120] + "..."
        print(f"{prefix}: {s}")
walk(d)

print("\n=== 2. HOLD OUT JSONL STATE ===")
p = CAM / "rbs_v4_holdout.jsonl"
if p.exists():
    lines = [l for l in p.read_text().splitlines() if l.strip()]
    print(f"rows: {len(lines)}")
    cells = set()
    for l in lines:
        try:
            r = json.loads(l)
            if r.get("campaign") == "rbs-v4-holdout" and "error" not in r:
                cells.add((r.get("config"), r.get("template"), r.get("seed")))
        except Exception:
            pass
    print(f"completed cells: {len(cells)}")
    for c in sorted(cells)[:10]:
        print("  ", c)
else:
    print("rbs_v4_holdout.jsonl does not exist (fresh)")

q = CAM / "rbs_v4_holdout_STALE_T1T12_GPTOSS_QUARANTINE.jsonl"
if q.exists():
    n = len([l for l in q.read_text().splitlines() if l.strip()])
    print(f"QUARANTINE file rows: {n} (NOT consumed by runner)")

print("\n=== 3. PROMPT FREEZE SHA ===")
pf = CAM / "PROMPTED_PROMPT_FREEZE.json"
if pf.exists():
    raw = pf.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    print(f"PROMPTED_PROMPT_FREEZE.json sha256: {sha}")
    print(f"runner hardcoded sha: 4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a")
    print(f"match: {sha == '4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a'}")
    pfj = json.loads(raw)
    print("keys:", list(pfj.keys()))
    print("mtime:", os.path.getmtime(pf))
else:
    print("PROMPTED_PROMPT_FREEZE.json missing")

print("\n=== 4. D13 PATCH STATE (ablation_runner model sites) ===")
src = (ROOT / "src/arena/ablation_runner.py").read_text()
import re
sites = [l.strip() for l in src.splitlines() if "model_id" in l and "def " not in l]
for s in sites:
    print("  ", s[:110])
print("hardcoded nvapi occurrences:", src.count("nvapi-REDACTED"))

print("\n=== 5. SEED SCHEME (resolve_seed) ===")
import sys
sys.path.insert(0, str(ROOT / "src"))
from arena.templates.base import resolve_seed
from arena.templates import ScenarioSplit
print("relative 0 ->", resolve_seed(0, ScenarioSplit.HOLDOUT))
print("relative 59 ->", resolve_seed(59, ScenarioSplit.HOLDOUT))

print("\n=== 6. INFRA EVENTS ON FILE ===")
for f in ["HOLDOUT_INFRA_EVENT_001.json", "HOLDOUT_INFRA_EVENT_002.json"]:
    fp = CAM / f
    if fp.exists():
        e = json.load(open(fp))
        print(f, "->", json.dumps({k: e.get(k) for k in ("event", "kind", "window", "status", "resolution")}, default=str)[:200])

print("\n=== 7. SEMANTIC INFERENCE DEFAULT MODEL ===")
si = (ROOT / "src/arena/semantic_inference.py").read_text()
m = re.search(r"model_id.*?=.*?[\"']([^\"']+)[\"']", si)
print("first model_id literal:", m.group(1) if m else "?")
