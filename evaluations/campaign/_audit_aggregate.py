"""D1 aggregate analyses over the 1200-row campaign JSONL (no run-dir reads).

Analysis 1: decision_outcome distribution per arm (budget exhaustion dominance?)
Analysis 2: failed-check mechanism classification per arm:
  - 'no_matching_claim'   => observed/detected in evidence but never formalized as claim
                              (claim-formalization gap signal)
  - other markers         => check failed for a different reason
Analysis 3: check-pair consistency: for each (arm, template, seed), does the SAME
            truth-check fail across arms, or is the failing predicate arm-specific?
"""
import json, collections, re

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
print(f"total rows: {len(rows)}")

arms = collections.Counter(r["arm"] for r in rows)
print("\narm counts:", dict(arms))

# ── Analysis 1: decision_outcome per arm ────────────────────────────
print("\n" + "=" * 72)
print("ANALYSIS 1: decision_outcome distribution per arm")
print("=" * 72)
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    c = collections.Counter(r["decision_outcome"] for r in sub)
    n = len(sub)
    line = ", ".join(f"{k}: {v} ({100*v/n:.1f}%)" for k, v in c.most_common())
    print(f"{arm:16s} (n={n:3d}): {line}")

# ── Analysis 2: failed-check mechanism per arm ──────────────────────
print("\n" + "=" * 72)
print("ANALYSIS 2: failed-check mechanism (claim-formalization gap?)")
print("=" * 72)

def classify_fail(fail_str):
    if "no_matching_claim" in fail_str:
        return "no_matching_claim"
    if "claim_text_matched" in fail_str:
        return "claim_text_matched_but_fail_elsewhere"
    if "restraint" in fail_str:
        return "restraint_violation"
    return "other"

for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    mech = collections.Counter()
    fail_examples = {}
    n_fail = 0
    for r in sub:
        fails = r.get("failed_checks") or []
        if not fails:
            continue
        n_fail += 1
        for f in fails:
            c = classify_fail(f)
            mech[c] += 1
            fail_examples.setdefault(c, f)
    print(f"\n{arm} (n_fail={n_fail}/{len(sub)}):")
    for k, v in mech.most_common():
        print(f"  {k:45s}: {v}")
        print(f"      ex: {fail_examples.get(k, '')[:110]}")

# ── Analysis 3: check identity overlap ──────────────────────────────
print("\n" + "=" * 72)
print("ANALYSIS 3: failing check identities (arm-agnostic vs arm-specific)")
print("=" * 72)
def check_name(fail_str):
    # strip the bracketed mechanism, keep the check identity
    return re.sub(r"\[.*?\]", "", fail_str).strip()

by_arm_fail_checks = {}
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    c = collections.Counter()
    for r in sub:
        for f in (r.get("failed_checks") or []):
            c[check_name(f)] += 1
    by_arm_fail_checks[arm] = c
    n_runs_fail = sum(1 for r in sub if r.get("failed_checks"))
    print(f"\n{arm} (runs with >=1 fail: {n_runs_fail}/{len(sub)})")
    for k, v in c.most_common(8):
        print(f"  {v:4d}x  {k}")

# intersection of check identities that fail in BOTH FULL and PROMPTED
set_full = set(by_arm_fail_checks["FULL_RAPHAEL"].keys())
set_prompted = set(by_arm_fail_checks["PROMPTED_AGENT"].keys())
print("\ncheck identities failing in BOTH FULL_RAPHAEL and PROMPTED_AGENT:")
for k in sorted(set_full & set_prompted):
    print(f"  {k}")

# ── bonus: outcome / outcome_reason distribution for PROMPTED ──────
print("\n" + "=" * 72)
print("BONUS: outcome + outcome_reason for PROMPTED_AGENT")
print("=" * 72)
sub = [r for r in rows if r["arm"] == "PROMPTED_AGENT"]
oc = collections.Counter(r["outcome"] for r in sub)
print("outcome:", dict(oc))
orc = collections.Counter(r["outcome_reason"] for r in sub)
print("outcome_reason:", dict(orc))
dc = collections.Counter((r["decision_outcome"], r["outcome"]) for r in sub)
print("\n(decision_outcome, outcome) pairs:")
for k, v in dc.most_common(10):
    print(f"  {k}: {v}")