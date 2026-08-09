import json, collections
CAMP="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign"
path=CAMP+"/rbs_v4_holdout.jsonl"
rows=[json.loads(l) for l in open(path) if l.strip()]
print("total", len(rows))

# distinct template values per arm
tpl=collections.defaultdict(collections.Counter)
arm_seed_range=collections.defaultdict(list)
for r in rows:
    tpl[r["arm"]][r.get("template")]+=1
    arm_seed_range[r["arm"]].append(r.get("seed"))
for a,c in tpl.items():
    print(a, dict(c))
print()
for a, seeds in arm_seed_range.items():
    print(a, "min/max seed:", min(seeds), max(seeds), "n unique:", len(set(seeds)), "any dup:", len(seeds)!=len(set(seeds)))
# cross-arm seed intersection
arms=list(arm_seed_range)
sets={a:set(arm_seed_range[a]) for a in arms}
for i in range(len(arms)):
    for j in range(i+1,len(arms)):
        a,b=arms[i],arms[j]
        print("intersection", a, b, len(sets[a]&sets[b]))