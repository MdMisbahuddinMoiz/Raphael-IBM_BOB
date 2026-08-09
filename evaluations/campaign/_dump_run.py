import json, os, sys

BASE = "/home/yaser/raphael-2.0-rbsv2r"
RAWDIR = BASE + "/arena/results/raw"
run = sys.argv[1]
d = os.path.join(RAWDIR, run)
print("RUN DIR:", d, "exists:", os.path.isdir(d))
for f in ["manifest.json", "run_conclusion.json", "evaluation.json", "metrics.json", "verification.json"]:
    p = os.path.join(d, f)
    if os.path.exists(p):
        print("\n" + "=" * 30, f, "=" * 30)
        txt = open(p, "r", errors="replace").read()
        print(txt[:4000])
        if len(txt) > 4000:
            print("...[truncated", len(txt), "bytes]")