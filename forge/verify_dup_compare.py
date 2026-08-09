#!/usr/bin/env python3
"""Compare duplicate (episode_id, sequence_number) snapshots for divergence."""
import json, os

D = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/dev_runs/raw/abl_PROMPTED_AGENT_arena-d6-013_s1357447574_dev/episodes.jsonl"
seen = {}
with open(D) as f:
    for line in f:
        o = json.loads(line)
        key = (o["episode_id"], o["sequence_number"])
        if key in seen:
            a, b = seen[key], o
            print(f"DUP {key}: identical={a == b} seq={a.get('sequence_number')}")
            if a != b:
                for k in set(a) | set(b):
                    if a.get(k) != b.get(k):
                        print(f"   DIFF key '{k}': A={str(a.get(k))[:120]} B={str(b.get(k))[:120]}")
        else:
            seen[key] = o
print(f"total composite keys: {len(seen)}")