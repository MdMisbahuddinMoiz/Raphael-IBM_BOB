import json, os, glob

# Find NWM run with has_service claim
dirs = glob.glob("arena/results/raw/abl_NO_WORLD_MODEL_*holdout")
for d in dirs:
    p = os.path.join(d, "run_conclusion.json")
    if not os.path.exists(p):
        continue
    rc = json.load(open(p))
    for c in rc.get("claims", []):
        if c.get("predicate") == "has_service":
            print(f"Found in: {d}")
            print(json.dumps(c, indent=1))
            exit(0)
print("No has_service found in any NWM run")