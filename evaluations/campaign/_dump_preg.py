import json, os
p="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/TERMINAL_FALSIFICATION_PREREGISTRATION.json"
if os.path.exists(p):
    d=json.load(open(p))
    def walk(o, pre=""):
        if isinstance(o, dict):
            for k,v in o.items():
                print(f"{pre}{k}:")
                walk(v, pre+"  ")
        elif isinstance(o, list):
            print(f"{pre}[list len={len(o)}]")
            for i,v in enumerate(o[:20]):
                walk(v, pre+"  ")
        else:
            print(f"{pre}{repr(o)}")
    walk(d)
else:
    print("MISSING")