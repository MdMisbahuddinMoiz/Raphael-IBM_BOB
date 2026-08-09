"""Check: git state of llm_service.py, wire_llm_service.py contents, old holdout failover values."""
import json, subprocess
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")

print("=== 1. git status of llm_service.py / llm_transport.py ===")
r = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True)
print(r.stdout)
r = subprocess.run(["git", "log", "--oneline", "-5", "--", "src/arena/llm_service.py"], cwd=ROOT, capture_output=True, text=True)
print("llm_service.py recent commits:")
print(r.stdout)

print("\n=== 2. wire_llm_service.py contents ===")
w = (ROOT / "forge/wire_llm_service.py").read_text()
print(w[:3000])

print("\n=== 3. old holdout failover values (were they real?) ===")
rows = [json.loads(l) for l in (ROOT / "evaluations/campaign/rbs_v4_holdout.jsonl").read_text().splitlines() if l.strip()]
fvals = {}
for r in rows:
    v = r.get("failover_count")
    if v is not None:
        fvals[str(v)] = fvals.get(str(v), 0) + 1
print("failover_count distribution:", fvals)
kvals = {}
for r in rows:
    v = r.get("final_key_alias")
    kvals[str(v)] = kvals.get(str(v), 0) + 1
print("final_key_alias distribution:", kvals)
svals = {}
for r in rows:
    v = r.get("provider_failures")
    svals[str(v)] = svals.get(str(v), 0) + 1
print("provider_failures distribution:", svals)
