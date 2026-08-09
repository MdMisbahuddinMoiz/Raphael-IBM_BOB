import os
P="/home/yaser/raphael-2.0-rbsv2r/.env"
keys=[]
if os.path.exists(P):
    for line in open(P):
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k=line.split("=",1)[0].strip()
        if k: keys.append(k)
print("ENV KEYS:")
for k in keys: print("  -", k)
