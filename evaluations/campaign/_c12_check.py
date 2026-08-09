import json

d = json.load(open("evaluations/campaign/rbs_v4_claim_ledger.json"))
c12 = [c for c in d["claims"] if c["id"] == 12][0]
e = c12["evidence"]
q = c12["qualification"]
print("claim12 mechanism-shared phrasing present:", "NOT the same defect status" in e)
print("claim12 evidence says MECHANISM:", "MECHANISM" in e)
print("claim12 no 'identical structural defect':", "identical structural defect" not in e)
print("claim12 no 'same instrument defect':", "same instrument defect" not in e)
print("claim12 qualification by-design mention:", "by design" in q)
c11 = [c for c in d["claims"] if c["id"] == 11][0]
print("claim11 DISTINCTION clause still present:", "DISTINCTION FROM CLAIM 12" in c11["qualification"])
print("JSON valid: True")