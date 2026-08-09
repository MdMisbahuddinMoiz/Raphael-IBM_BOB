import os, sys

base = "/home/yaser/raphael-2.0-rbsv2r"
run = sys.argv[1]
log = os.path.join(base, "evaluations/campaign/rbs_v4_holdout_run3.log")
print("searching", log, "for", run)
hits = 0
with open(log, "r", errors="replace") as fh:
    for line in fh:
        if run in line:
            hits += 1
            if hits <= 10:
                s = line.strip()[:2000]
                print("HIT", hits, s)
print("total hits:", hits)