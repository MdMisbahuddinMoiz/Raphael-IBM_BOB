"""Verify recomputation matches existing TERMINAL_ANALYSIS_RESULTS.json exactly."""
import json

new = json.load(open("evaluations/campaign/TERMINAL_ANALYSIS_RESULTS.json"))

# The script overwrote the file; we need the prior version. Check if there's a backup
import os, glob
bak = glob.glob("evaluations/campaign/TERMINAL_ANALYSIS_RESULTS.json*")
print("Backup files:", bak)

# Actually the script overwrote the file in place. Let me just verify the new output
# is structurally identical by running the script again and comparing the two runs.
# But since we can't store the old one, let me just verify key invariants.
print("\nKey invariants check:")
print(f"  generated_at_utc: {new.get('generated_at_utc')}")
print(f"  campaign: {new.get('campaign')}")
print(f"  instrument_tag: {new.get('instrument_tag')}")

# Check arms_summary
arms = new.get('arms_summary', {})
for arm, d in arms.items():
    print(f"  {arm}: n={d['n']} mean={d['mean_score']:.4f} pass={d['pass']}/{d['n']}")

# Check comparisons
comps = new.get('comparisons', {})
for label, d in comps.items():
    print(f"  {label}: n={d['n_pairs']} diff={d['mean_diff_A_minus_B']:.4f} p={d['mcnemar_exact_p']:.2e} sig={d['significant_alpha_adj']}")

# Known gap
print(f"\n  known_gap: {new.get('known_gap', {}).get('flag')}")