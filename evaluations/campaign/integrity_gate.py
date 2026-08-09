import os, json, hashlib
from collections import Counter, defaultdict

REPO = "/home/yaser/raphael-2.0-rbsv2r"
J = REPO + "/evaluations/campaign/rbs_v4_holdout.jsonl"
FREEZE = REPO + "/evaluations/campaign/TERMINAL_VALIDATION_FREEZE.json"
REPORT = REPO + "/evaluations/campaign/rbs_v4_holdout_INTEGRITY_GATE.json"

FAMILIES = ["known-observable","signal-noise","false-lead","contradiction","forbidden-proximity"]
ARMS = ["FULL_RAPHAEL","NO_WORLD_MODEL","PROMPTED_AGENT","SCRIPTED_BASELINE"]
NETWORK_ARMS = ["FULL_RAPHAEL","PROMPTED_AGENT","NO_WORLD_MODEL"]
SEEDS = list(range(60))
MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"

def sha(path):
    if not os.path.exists(path): return "MISSING"
    return hashlib.sha256(open(path,"rb").read()).hexdigest()

rows=[]
if os.path.exists(J):
    for line in open(J):
        line=line.strip()
        if not line: continue
        try: rows.append(json.loads(line))
        except Exception: pass
ok=[r for r in rows if "error" not in r]
err=[r for r in rows if "error" in r]

gate={"checked_at_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
      "campaign": "rbs-v4-holdout", "phase": "integrity-gate-pre-analysis"}

# ── 1. Completeness: exact cell set = all (family, arm, seed) combos ──
expected = set()
for f in FAMILIES:
    for a in ARMS:
        for s in SEEDS:
            expected.add((f,a,s))
present = set((r["template"], r["config"], r["seed"]) for r in ok)
missing = expected - present
extra   = present - expected
gate["1_completeness"] = {
    "expected_cells": len(expected),
    "present_cells": len(present),
    "missing": sorted(missing, key=str)[:20],
    "extra": sorted(extra, key=str)[:20],
    "pass": len(missing)==0 and len(extra)==0 and len(present)==1200,
}

# ── 2. run_id uniqueness ──
ids=[r.get("run_id") for r in ok]
dup = [i for i,c in Counter(ids).items() if c>1]
gate["2_runid_uniqueness"]={"n_rows":len(ok),"unique_run_ids":len(set(ids)),
    "duplicates":dup[:10],"pass":len(dup)==0}

# ── 3. seed/family/arm parity ──
arm_c = Counter(r["config"] for r in ok)
fam_c = Counter(r["template"] for r in ok)
seed_ok = all(2000 <= (r.get("abs_seed") or 0) < 10000 for r in ok)
model_ok = set(r.get("model_id") for r in ok) == {MODEL}
gate["3_parity"]={
    "per_arm": dict(arm_c),
    "per_family": dict(fam_c),
    "seeds_exclusively_in_holdout_range": seed_ok,
    "model_identity": sorted(set(r.get("model_id") for r in ok)),
    "pass": all(v==300 for v in arm_c.values()) and all(v==240 for v in fam_c.values()) and seed_ok and model_ok,
}

# ── 4. freeze-hash verification ──
fh=json.load(open(FREEZE)).get("files_sha256",{})
changed=[]
for rel,fr in fh.items():
    cur=sha(os.path.join(REPO,rel))
    if cur!=fr: changed.append((rel,fr,cur))
gate["4_freeze_hash"]={"n_files":len(fh),"changed":changed,"pass":len(changed)==0}

# ── 5. world determinism: for each (family,seed), all arms same world_hash ──
cells_by_cell=defaultdict(dict)
for r in ok:
    cells_by_cell[(r["template"], r["seed"])][r["config"]] = r["world_hash"]
det={}
mismatched=[]
for k,arms in sorted(cells_by_cell.items()):
    h=set(arms.values())
    if len(h)>1: mismatched.append((k, arms))
det_tested=len(cells_by_cell)
gate["5_world_determinism"]={
    "checked_cells": det_tested,  # (family,seed) pairs; expect 300 (5x60)
    "expected_pairs": len(FAMILIES)*len(SEEDS),
    "mismatched_pairs": mismatched[:10],
    "pass": len(mismatched)==0 and det_tested==300,
}

# ── 6. Matched INFRA validity (authoritative at closure) ──
def qualifying(r):
    return ((r.get("provider_failures") or 0)>0) or bool(r.get("infra_failures"))
invalid_comparisons=[]; valid_comparisons=[]
for (f,s) in sorted(set((r["template"], r["seed"]) for r in ok)):
    cells=[r for r in ok if r["template"]==f and r["seed"]==s]
    if len(cells)<4: continue
    infra_arms=sorted(r["config"] for r in cells if r["config"] in NETWORK_ARMS and qualifying(r))
    item={"family":f,"seed":s,"infra_arms":infra_arms,
          "cells_present":[r["config"] for r in cells]}
    if infra_arms: invalid_comparisons.append(item)
    else: valid_comparisons.append(item)
gate["6_matched_infra_validity"]={
    "policy": ("any network arm with >=1 qualifying INFRA event invalidates the WHOLE matched "
               "comparison for PRIMARY FULL-vs-PROMPTED inference; no selective rerun; no fallback"),
    "n_matched_comparisons": len(valid_comparisons)+len(invalid_comparisons),
    "n_valid": len(valid_comparisons),
    "n_invalid": len(invalid_comparisons),
    "invalid_comparisons": invalid_comparisons,
    "pass": len(invalid_comparisons) <= 10,  # tolerant design; authoritative
}

# ── overall ──
gate["rows_metadata"]={"total_rows":len(rows),"valid_rows":len(ok),"error_rows":len(err)}
skip=("checked_at_utc","campaign","phase","rows_metadata")
gate["overall_pass"] = all(gate[k]["pass"] for k in gate if k not in skip)

json.dump(gate, open(REPORT,"w"), indent=2)
print(json.dumps(gate, indent=2))