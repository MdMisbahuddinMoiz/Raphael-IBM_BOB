"""Dump first episode row structure for PROMPTED run."""
import json

p = "arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout/episodes.jsonl"
rows = [json.loads(l) for l in open(p)]
print(f"episode rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"\n--- row {i} keys: {list(r.keys())}")
    print(json.dumps(r, indent=1)[:1800])