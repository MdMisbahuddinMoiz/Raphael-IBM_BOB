import os, re, collections

log = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout_run3.log"
head = 200000  # bytes of head and tail to sample
sz = os.path.getsize(log)
print("size:", sz)
with open(log, "r", errors="replace") as fh:
    head = fh.read(200000)
with open(log, "r", errors="replace") as fh:
    fh.seek(max(0, sz-200000))
    tail = fh.read()
print("=== typical head line ===")
for l in head.splitlines()[:20]:
    print(l[:300])
print("=== typical tail line ===")
for l in tail.splitlines()[-10:]:
    print(l[:300])