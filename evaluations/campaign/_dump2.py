import json, os
out=[]
for f in ["rbs_v4_claim_ledger.json","TERMINAL_FALSIFICATION_PREREGISTRATION.json"]:
    p="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/"+f
    out.append("="*70); out.append(f); out.append("="*70)
    if not os.path.exists(p): out.append("MISSING"); continue
    d=json.load(open(p))
    out.append(json.dumps(d, indent=1)[:5000])
open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/_specs_dump.txt","w").write("\n".join(out))
print("written")