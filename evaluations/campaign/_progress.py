import re, os
P="/tmp/holdout_full.log"
rows=[]
prog=[]
with open(P) as f:
    for line in f:
        m=re.search(r"\[\s*(\d+)/(\d+)\]", line)
        if m and "RESUME" not in line:
            prog.append((int(m.group(1)), int(m.group(2))))
print("progress lines found:", len(prog))
if prog:
    print("last:", prog[-1])
# also count from jsonl
J="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl"
n=0
if os.path.exists(J):
    for line in open(J):
        if line.strip(): n+=1
print("jsonl rows:", n)
