"""D2: Sensitivity table — proportion of paired FULL-vs-OTHER score differences
exceeding Δ thresholds (0.05, 0.10, 0.20, 0.30, 0.40, 0.50).
Replaces the post-hoc Δ≥0.10 adjudication bar with a sensitivity table.
"""
import json
import collections

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

# Build dict: arm -> (template, seed) -> score
by_arm = collections.defaultdict(dict)
for r in rows:
    key = (r["template"], r["seed"])
    by_arm[r["arm"]][key] = r["score"]

# For each comparison, get paired scores for common (template, seed)
comparisons = [
    ("FULL_RAPHAEL", "PROMPTED_AGENT", "FULL_vs_PROMPTED", "primary (central thesis)"),
    ("FULL_RAPHAEL", "NO_WORLD_MODEL", "FULL_vs_NO_WORLD_MODEL", "secondary (world-model component)"),
    ("FULL_RAPHAEL", "SCRIPTED_BASELINE", "FULL_vs_SCRIPTED", "secondary (operator utility)"),
]

thresholds = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]

print("=" * 110)
print("D2 SENSITIVITY TABLE: Proportion of paired (template, seed) cells where FULL score - OTHER score ≥ Δ")
print("=" * 110)
print()
print(f"{'Comparison':30s} {'n_pairs':>8s} " + " ".join(f"Δ≥{t:.2f}" for t in thresholds))

# Exclude infra-invalid seeds per TERMINAL_ANALYSIS
INFRA_EXCLUDE = {15, 57}
for A, B, label, desc in comparisons:
    scores_A = by_arm.get(A, {})
    scores_B = by_arm.get(B, {})
    common_keys = set(scores_A.keys()) & set(scores_B.keys())
    # exclude infra-invalid seeds
    common_keys = {k for k in common_keys if k[1] not in INFRA_EXCLUDE}
    n = len(common_keys)
    diffs = [scores_A[k] - scores_B[k] for k in common_keys]
    diffs.sort()
    # compute proportion ≥ Δ for each threshold
    props = []
    for t in thresholds:
        # proportion of diffs >= t
        # diffs sorted ascending; find first index >= t
        import bisect
        idx = bisect.bisect_left(diffs, t)
        prop = (n - idx) / n if n > 0 else 0
        props.append(f"{prop*100:5.1f}%")
    mean_diff = sum(diffs)/len(diffs) if diffs else 0
    print(f"{label:30s} {n:>8d} " + " ".join(props) + f"  | mean_diff={mean_diff:.4f}")

print()
print("Notes:")
print("- Pairs are matched by (template, seed) across the two arms.")
print("- Seeds 15 (EVENT-001) and 57 (EVENT-002) excluded per infra-validity policy.")
print("- Score range [0,1]; Δ is FULL minus OTHER (positive = FULL higher).")
print("- This table REPLACES the post-hoc Δ≥0.10 adjudication bar with a full sensitivity curve.")
print("- The former 'Δ≥0.10 bar' would correspond to the column Δ≥0.10 here.")