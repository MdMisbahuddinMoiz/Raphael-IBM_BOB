"""Inspect: campaign JSONL row fields + evaluation.json structure for both arms."""
import json

p = "evaluations/campaign/rbs_v4_holdout.jsonl"
rows = [json.loads(l) for l in open(p) if l.strip()]
print(f"total rows: {len(rows)}")

# row field names + a sample
r0 = rows[0]
print("\nrow keys:", list(r0.keys()))
print("\nsample row (arm):", r0.get("architecture_id"), r0.get("run_id"))
for k in ("decision_outcome", "outcome", "outcome_reason", "safety_pass", "score", "family", "seed"):
    print(f"  {k}: {r0.get(k)}")

# distribution of keys presence
import collections
key_presence = collections.Counter()
for r in rows:
    for k in r.keys():
        key_presence[k] += 1
print("\nkey presence across rows:", dict(key_presence))

# evaluation.json structure for the two arms
for arm in ("PROMPTED_AGENT", "FULL_RAPHAEL"):
    p2 = f"arena/results/raw/abl_{arm}_known-observable_s0000_holdout/evaluation.json"
    try:
        ev = json.load(open(p2))
        print(f"\n--- {arm} evaluation.json keys: {list(ev.keys())}")
        print(json.dumps(ev, indent=1)[:1400])
    except Exception as e:
        print(arm, "ERR", e)