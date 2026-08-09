"""Claim predicate inventory + max claims per arm (PROMPTED vs FULL vs others)."""
import json, collections, os

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

def claim_stats(arm):
    dirs = [r["run_dir"] for r in rows if r["arm"] == arm]
    preds = collections.Counter()
    n_claims = []
    object_types = collections.Counter()
    for d in dirs:
        rc = json.load(open(os.path.join(d, "run_conclusion.json")))
        cl = rc.get("claims") or []
        n_claims.append(len(cl))
        for c in cl:
            preds[c.get("predicate")] += 1
            ov = c.get("object_value")
            object_types[type(ov).__name__] += 1
    n = len(n_claims)
    import statistics
    print(f"\n---- {arm} (n={n}) ----")
    print(f"  mean_claims={statistics.mean(n_claims):.2f} median={statistics.median(n_claims)} "
          f"max={max(n_claims)} zero={sum(1 for x in n_claims if x==0)}")
    print(f"  predicates: {dict(preds.most_common(15))}")
    print(f"  object_types: {dict(object_types)}")

for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"):
    claim_stats(arm)

# for PROMPTED: which predicate is the single claim? and how are claims derived?
print("\n---- PROMPTED single-claim runs: predicate + derivation ----")
dirs = [r["run_dir"] for r in rows if r["arm"] == "PROMPTED_AGENT"]
deriv = collections.Counter()
pred1 = collections.Counter()
for d in dirs[:60]:
    rc = json.load(open(os.path.join(d, "run_conclusion.json")))
    cl = rc.get("claims") or []
    if len(cl) >= 1:
        pred1[cl[0].get("predicate")] += 1
    prods = [c.get("producer") for c in cl] or [None]
    deriv[tuple(prods)] += 1
print("  predicate[0] over first 60:", dict(pred1))
print("  producer sets:", dict(deriv))