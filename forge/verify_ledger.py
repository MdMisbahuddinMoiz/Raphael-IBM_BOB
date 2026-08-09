import json
d = json.load(open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/AMENDMENT_LEDGER.json"))
ids = [e["amendment_id"] for e in d["entries"]]
print("entries:", len(ids))
print("APPEND-ONLY check (holdout preserved):", "AMENDMENT-HOLDOUT-LAUNCH-2026-08-07" in ids)
print("new entry present:", "AMENDMENT-MODEL-EOL-2026-08-09" in ids)
for e in d["entries"]:
    assert set(e.keys()) >= {"amendment_id", "title", "authorizer", "applied_at_utc", "reason"}
print("all entries structurally intact")
