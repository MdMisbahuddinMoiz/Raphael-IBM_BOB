#!/usr/bin/env python3
"""Characterize duplicate snapshots: same-session vs cross-session append."""
import json

D = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/dev_runs/raw/abl_PROMPTED_AGENT_arena-d6-013_s1357447574_dev/episodes.jsonl"
rows = [json.loads(l) for l in open(D)]
print(f"total lines: {len(rows)}")
# group by ep id and show sequence/timestamp pattern
by_ep = {}
for r in rows:
    by_ep.setdefault(r["episode_id"], []).append(r["sequence_number"])
for ep, seqs in sorted(by_ep.items()):
    print(f"  {ep}: seqs={sorted(seqs)}")

# timestamps sorted
ts = sorted(r["timestamp"] for r in rows)
print(f"\ntimestamp min={ts[0]:.0f} max={ts[-1]:.0f} span={ts[-1]-ts[0]:.0f}s")
# cluster by gap > 600s
clusters = []
cur = [ts[0]]
for t in ts[1:]:
    if t - cur[-1] > 600:
        clusters.append(cur)
        cur = [t]
    else:
        cur.append(t)
clusters.append(cur)
print(f"session clusters (gap>600s): {[len(c) for c in clusters]}")

# are duplicate rows adjacent (append at end) or interleaved?
for i in range(len(rows) - 1):
    a, b = rows[i], rows[i + 1]
    if (a["episode_id"], a["sequence_number"]) == (b["episode_id"], b["sequence_number"]):
        print(f"ADJACENT dup at line {i}: same composite key")
        break
else:
    print("no adjacent dups — duplicates are interleaved/non-adjacent")