import json
d=json.load(open("evaluations/campaign/AMENDMENT_LEDGER.json"))
e=d["entries"]
for x in e:
    if x.get("amendment_id") in ("AMENDMENT-A-2026-08-06","AMENDMENT-B-2026-08-06"):
        print("=== ", x.get("amendment_id"), "===")
        print(json.dumps(x, indent=2))
        print()