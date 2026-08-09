import json, collections
rows=[json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl")]
print("total rows:", len(rows))
r0=rows[0]
print("keys:", sorted(r0.keys()))
def pick(d,*ks):
    for k in ks:
        if isinstance(d,dict) and k in d: return d[k]
    return None
scen=collections.Counter()
arm=collections.Counter()
model=collections.Counter()
seeds=collections.Counter()
for r in rows:
    scen[str(pick(r,"scenario","scenario_id","template","template_id","family","family_id"))]+=1
    arm[str(pick(r,"arm","config","configuration","variant"))]+=1
    model[str(pick(r,"model","model_id","provider","llm_model"))]+=1
    seeds[str(pick(r,"seed","run_seed"))]+=1
print("\nscenario/template counts (top 25):")
for k,v in scen.most_common(25): print(f"  {k}: {v}")
print("\narm/config counts:")
for k,v in arm.most_common(25): print(f"  {k}: {v}")
print("\nmodel counts:")
for k,v in model.most_common(10): print(f"  {k}: {v}")
print("\nseed unique:", len(seeds))
for k,v in list(seeds.most_common(10)): print(f"  {k}: {v}")
