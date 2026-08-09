"""D1 follow-up: harness health + claim-volume per arm + claim-bucket split.

Probes:
  A. envelope_failures / model_failures / provider_failures / infra_failures per arm
  B. claims count per run per arm (from run_conclusion.json, sampled or all)
  C. failed-check buckets: [no_claims] vs [no_matching_claim] vs restraint vs other
  D. INCORRECT vs ABSTAIN_INCORRECT: which check failed in each class
"""
import json, collections, re, os

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

# ── A: harness health ────────────────────────────────────────────────
print("=" * 72)
print("PROBE A: harness health per arm (envelope/model/provider/infra failures)")
print("=" * 72)
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    keys = ["envelope_failures", "logical_llm_calls", "provider_attempts", "failover_count",
            "model_failures", "provider_failures", "infra_failures", "adapter_error_events",
            "llm_calls", "llm_invocations"]
    parts = []
    for k in keys:
        vals = [r.get(k) for r in sub]
        nonnull = [v for v in vals if v is not None]
        try:
            tot = sum(nonnull) if nonnull else 0
        except TypeError:
            tot = len(nonnull)
        parts.append(f"{k}={tot}")
    print(f"{arm:16s}: " + " | ".join(parts))

# distinct failure_class / final_provider_status
print("\nfailure_class per arm:")
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    fc = collections.Counter(str(r.get("failure_class")) for r in sub)
    print(f"  {arm:16s}: {dict(fc)}")

# ── B: claim counts per run ──────────────────────────────────────────
print("\n" + "=" * 72)
print("PROBE B: run_conclusion claim counts per arm (full 300/arm read)")
print("=" * 72)
nmax = 6000
for arm in ["code_FULL_RAPHAEL", "code_PROMPTED_AGENT", "code_NO_WORLD_MODEL", "code_SCRIPTED_BASELINE"][::-1]:
    pass
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    dirs = [r["run_dir"] for r in rows if r["arm"] == arm]
    cnts = []
    zero_claim_runs = 0
    missing = 0
    for d in dirs:
        p = os.path.join(d, "run_conclusion.json")
        if not os.path.exists(p):
            missing += 1
            continue
        try:
            rc = json.load(open(p))
        except Exception:
            missing += 1
            continue
        cl = rc.get("claims") or []
        cnts.append(len(cl))
        if len(cl) == 0:
            zero_claim_runs += 1
    import statistics
    if cnts:
        print(f"{arm:16s}: n={len(cnts)} missing={missing} mean_claims={statistics.mean(cnts):.1f} "
              f"median={statistics.median(cnts)} zero_claim_runs={zero_claim_runs} "
              f"p90={sorted(cnts)[int(0.9*len(cnts))] if cnts else 0}")

# ── C: check buckets ─────────────────────────────────────────────────
print("\n" + "=" * 72)
print("PROBE C: failed-check buckets per arm")
print("=" * 72)
def bucket(f):
    if "no_claims" in f:
        return "no_claims_AT_ALL"
    if "no_matching_claim" in f:
        return "no_matching_claim"
    if "prohibited_actions_attempted" in f:
        return "prohibited_action_violation"
    if "claim" in f:
        return "claim_related_other"
    return "other"
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    b = collections.Counter()
    for r in sub:
        for f in (r.get("failed_checks") or []):
            b[bucket(f)] += 1
    print(f"{arm:16s}: {dict(b)}")