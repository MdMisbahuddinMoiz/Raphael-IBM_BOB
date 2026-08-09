import json, os, sys

BASE = "/home/yaser/raphael-2.0-rbsv2r"
RAWDIR = BASE + "/arena/results/raw"
run = sys.argv[1]
d = os.path.join(RAWDIR, run)
p = os.path.join(d, "component_traces.json")
print("COMPONENT_TRACES:", p, "exists:", os.path.exists(p))
if not os.path.exists(p):
    sys.exit(0)
data = json.load(open(p, "r", errors="replace"))
def walk(o, pre="", depth=0):
    if depth > 6:
        print(pre + "...[deep]")
        return
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                print(f"{pre}{k}: {type(v).__name__} len={len(v)}")
                walk(v, pre + "  ", depth + 1)
            else:
                s = str(v)
                print(f"{pre}{k}: {s[:200]}")
    elif isinstance(o, list):
        for i, v in enumerate(o[:8]):
            print(f"{pre}[{i}]: {type(v).__name__}")
            walk(v, pre + "  ", depth + 1)
walk(data)