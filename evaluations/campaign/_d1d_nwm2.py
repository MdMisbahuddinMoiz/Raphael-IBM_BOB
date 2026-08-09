import json, os

# Find an NWM run with has_service claim
base = "arena/results/raw"
for d in os.listdir(base):
    if d.startswith("abl_NO_WORLD_MODEL_") and "holdout" in d:
        p = os.path.join(base, d, "run_conclusion.json")
        try:
            rc = json.load(open(p))
        except:
            continue
        for c in rc.get("claims", []):
            if c.get("predicate") == "has_service":
                print(json.dumps(c, indent=1))
                break
        break