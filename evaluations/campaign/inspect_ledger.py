import json
d=json.load(open("evaluations/campaign/AMENDMENT_LEDGER.json"))
e=d["entries"]
print("entries:",len(e))
for x in e:
    print(" -", x.get("amendment_id"), "| model:", x.get("model", x.get("model_id","?")), "| status:", x.get("status","?"))
