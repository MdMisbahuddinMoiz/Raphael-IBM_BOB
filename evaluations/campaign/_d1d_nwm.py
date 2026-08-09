import json, os, collections

# Check all NWM runs for claim types and derivation types
base = "arena/results/raw"
nwm_dirs = [d for d in os.listdir(base) if d.startswith("abl_NO_WORLD_MODEL_") and "holdout" in d]

all_claims = collections.Counter()
deriv_types = collections.Counter()
hs_count = 0
hs_deriv = collections.Counter()

for d in nwm_dirs:
    p = os.path.join(base, d, "run_conclusion.json")
    try:
        rc = json.load(open(p))
    except:
        continue
    for c in rc.get("claims", []):
        pred = c.get("predicate")
        deriv = c.get("derivation_type", "unknown")
        all_claims[pred] += 1
        deriv_types[deriv] += 1
        if pred == "has_service":
            hs_count += 1
            hs_deriv[deriv] += 1

print("NWM claim predicates (all 300 runs):")
for p, c in all_claims.most_common():
    print(f"  {p}: {c}")

print(f"\nTotal has_service claims: {hs_count}")
print("has_service derivation types:")
for d, c in hs_deriv.most_common():
    print(f"  {d}: {c}")

print("\nAll derivation types:")
for d, c in deriv_types.most_common():
    print(f"  {d}: {c}")