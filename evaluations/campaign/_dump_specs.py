import json, os
for f in ["rbs_v4_claim_ledger.json","TERMINAL_FALSIFICATION_PREREGISTRATION.json",
          "rbs_v4_reproducibility_manifest.json"]:
    p="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/"+f
    print("="*70); print(f); print("="*70)
    if not os.path.exists(p): print("MISSING"); continue
    d=json.load(open(p))
    s=json.dumps(d, indent=1)
    print(s[:4500])