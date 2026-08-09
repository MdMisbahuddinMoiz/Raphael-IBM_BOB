"""D2: Family-level sensitivity for FULL_vs_PROMPTED (central thesis)"""
import json, bisect, collections

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
INFRA_EXCLUDE = {15, 57}

by_arm = collections.defaultdict(dict)
for r in rows:
    if r["seed"] in INFRA_EXCLUDE:
        continue
    key = (r["template"], r["seed"])
    by_arm[r["arm"]][key] = r["score"]

scores_A = by_arm.get("FULL_RAPHAEL", {})
scores_B = by_arm.get("PROMPTED_AGENT", {})
common_keys = set(scores_A.keys()) & set(scores_B.keys())

# Group by family
families = collections.defaultdict(list)
for k in common_keys:
    fam = k[0]
    d = scores_A[k] - scores_B[k]
    families[fam].append(d)

print("Family-level sensitivity: FULL_vs_PROMPTED (n_pairs per family)")
thresholds = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
for fam in sorted(families.keys()):
    diffs = sorted(families[fam])
    n = len(diffs)
    props = []
    for t in thresholds:
        idx = bisect.bisect_left(diffs, t)
        prop = (n - idx) / n if n > 0 else 0
        props.append(f"{prop*100:5.1f}%")
    mean_d = sum(diffs)/n
    print(f"{fam:22s} n={n:3d} " + " ".join(props) + f"  | mean={mean_d:.4f}")