"""Locate run row in campaign JSONL; inspect metrics/verification; check evidence persistence."""
import json

# 1) campaign JSONL row
p = "evaluations/campaign/rbs_v4_holdout.jsonl"
target = "abl_PROMPTED_AGENT_known-observable_s0000_holdout"
row = None
n = 0
for ln in open(p):
    try:
        r = json.loads(ln)
    except Exception:
        continue
    if r.get("run_id") == target:
        row = r
        break
    n += 1
print(f"scanned {n} rows; found: {row is not None}")
if row:
    print("row keys:", list(row.keys()))
    for k, v in row.items():
        s = json.dumps(v)[:200] if not isinstance(v, str) else v[:200]
        print(f"  {k}: {s}")

# 2) metrics + verification for run dir
for f in ("metrics.json", "verification.json"):
    p2 = f"arena/results/raw/{target}/{f}"
    try:
        print(f"\n--- {f}: {open(p2).read()[:1500]}")
    except Exception as e:
        print(f, "ERR", e)

# 3) check if any evidence.json / evidence store persisted
import os
d = f"arena/results/raw/{target}"
for fn in sorted(os.listdir(d)):
    print("dir file:", fn, os.path.getsize(os.path.join(d, fn)))