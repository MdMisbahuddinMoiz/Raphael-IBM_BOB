import json
d = json.load(open("evaluations/campaign/rbs_v4_claim_ledger.json"))
print("Total claims:", len(d["claims"]))
print(json.dumps(d["summary"], indent=1))