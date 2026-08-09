import os
d="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign"
for f in sorted(os.listdir(d)):
    if any(k in f.lower() for k in ["terminal","holdout","amendment","verdict","decision","claim","integ","threshold","criteria","spec","analysis","prereg","report"]):
        p=os.path.join(d,f)
        print(f"{os.path.getsize(p):>12}  {f}")