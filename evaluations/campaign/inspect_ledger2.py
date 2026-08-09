import json
d=json.load(open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/AMENDMENT_LEDGER.json"))
print("top keys:", list(d.keys()))
for k in d.keys():
    if k != "entries":
        print(k, ":", str(d[k])[:200])
e=d["entries"][0]
print("\nsample entry keys:", list(e.keys()))
print(json.dumps(e, indent=1)[:800])
