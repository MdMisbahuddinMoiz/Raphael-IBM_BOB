import json, os
p="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_statistics.json"
if os.path.exists(p):
    d=json.load(open(p))
    print(json.dumps(d, indent=1)[:6000])
else:
    print("MISSING statistics file")