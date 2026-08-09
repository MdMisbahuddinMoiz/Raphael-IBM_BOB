import json

d = json.load(open("evaluations/campaign/rbs_v4_claim_ledger.json"))
c11 = [c for c in d["claims"] if c["id"] == 11][0]
print("CLAIM 11 classification:", c11["classification"])
print("has DISTINCTION clause:", "DISTINCTION FROM CLAIM 12" in c11["qualification"])
print("has STRUCTURAL DISCLOSURE:", "STRUCTURAL DEFECT DISCLOSURE" in c11["qualification"])
c12 = [c for c in d["claims"] if c["id"] == 12][0]
print("CLAIM 12 classification:", c12["classification"])
print("claim 12 mentions SCRIPTED defect:", "SCRIPTED" in c12["qualification"])