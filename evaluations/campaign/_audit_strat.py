"""Pull stratified 10-run PROMPTED sample (2/family) with claims+episodes metrics."""
import json, collections, os

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
by_arm = collections.defaultdict(list)
for r in rows:
    by_arm[r["arm"]].append(r)

# check template / scenario_id naming for families
templ = collections.Counter(r["template"] for r in rows)
print("template values:", dict(templ))
scen = collections.Counter(r["scenario_id"] for r in rows)
print("scenario_id values:", list(scen.keys())[:10])

# stratified sample: pick 2 seeds per family (first two distinct seeds)
fam_of = {}
for r in by_arm["PROMPTED_AGENT"]:
    fam = r["template"] or r["scenario_id"]
    fam_of.setdefault(fam, []).append(r)

sample = []
for fam, runs in sorted(fam_of.items()):
    seen = {}
    for r in sorted(runs, key=lambda x: x["seed"]):
        seen.setdefault(r["seed"], r)
    sel = sorted(seen.keys())[:2]
    for s in sel:
        sample.append((fam, seen[s]))
print(f"\nstratified sample: {len(sample)} runs")

def claim_count(run_id, run_dir):
    p = os.path.join(run_dir, "run_conclusion.json") if run_dir else None
    if not p or not os.path.exists(p):
        return "?"
    rc = json.load(open(p))
    return len(rc.get("claims") or [])

def ep_info(run_dir):
    p = os.path.join(run_dir, "episodes.jsonl") if run_dir else None
    if not p or not os.path.exists(p):
        return (0, 0)
    rows_ep = [json.loads(l) for l in open(p) if l.strip()]
    ev_created = sum(len(x.get("evidence_created") or []) for x in rows_ep)
    return (len(rows_ep), ev_created)

print("\n" + "=" * 100)
print("STRATIFIED PROMPTED_AGENT SAMPLE (2/family)")
print("=" * 100)
for fam, r in sample:
    rd = r["run_dir"]
    n_ep, n_ev = ep_info(rd)
    n_cl = claim_count(r["run_id"], rd)
    print(f"{fam:22s} seed={r['seed']:3d} outcome={r['outcome']:16s} score={r['score']:.3f} "
          f"ep={n_ep} ev_created={n_ev} claims={n_cl} "
          f"| pass=[{'; '.join((r.get('passed_checks') or [])[:2])}] "
          f"fail=[{'; '.join((r.get('failed_checks') or [])[:3])}]")

# infra_failures semantic check: is it constant & identical across SCRIPTED?
print("\ninfra_failures distribution per arm:")
for arm, runs in by_arm.items():
    c = collections.Counter(r.get("infra_failures") for r in runs)
    print(f"  {arm:16s}: {dict(c)}")

# what does infra_failures map to? grep the runner for the field quickly
print("\nprovider_failures nonzero rows:")
for arm, runs in by_arm.items():
    bad = [r for r in runs if (r.get("provider_failures") or 0) > 0]
    for r in bad:
        print(f"  {arm} {r['run_id']} provider_failures={r['provider_failures']}")