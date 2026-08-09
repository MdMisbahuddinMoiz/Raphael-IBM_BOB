import os, sys, json

base = "/home/yaser/raphael-2.0-rbsv2r"
run = sys.argv[1]
d = os.path.join(base, "arena/results/raw", run)
print("FILES in", d)
for root, dirs, files in os.walk(d):
    for f in files:
        p = os.path.join(root, f)
        print(f"  {os.path.getsize(p):>9}  {p[len(d):]}")

# also grep the run log JSONL for the run_id
log = os.path.join(base, "evaluations/campaign/rbs_v4_holdout.log")
print("\nsearch log for run_id:", run)
hits = 0
with open(log, "r", errors="replace") as fh:
    for line in fh:
        if run in line:
            hits += 1
            if hits <= 5:
                print("  HIT:", line[:500])
print("  total log hits:", hits)