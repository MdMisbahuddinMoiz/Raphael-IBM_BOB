import json, os

# Check SCRIPTED_BASELINE run_conclusion
p = "arena/results/raw/abl_SCRIPTED_BASELINE_known-observable_s0000_holdout/run_conclusion.json"
rc = json.load(open(p))
print("SCRIPTED_BASELINE s0000:")
print(f"  decision: {rc.get('decision')}")
print(f"  architecture_id: {rc.get('architecture_id')}")
print(f"  claims: {len(rc.get('claims', []))}")
for c in rc.get('claims', [])[:5]:
    print(f"  {c.get('predicate')}: {c.get('object_value')}")

# Check NWM run_conclusion for has_service
p2 = "arena/results/raw/abl_NO_WORLD_MODEL_known-observable_s0000_holdout/run_conclusion.json"
rc2 = json.load(open(p2))
print(f"\nNO_WORLD_MODEL s0000:")
print(f"  decision: {rc2.get('decision')}")
print(f"  architecture_id: {rc2.get('architecture_id')}")
print(f"  claims: {len(rc2.get('claims', []))}")
hs = [c for c in rc2.get('claims', []) if c.get('predicate') == 'has_service']
print(f"  has_service claims: {len(hs)}")
for c in hs[:3]:
    print(f"  {c.get('predicate')}: {c.get('object_value')}")

# Also check hypothesis claims in NWM - what predicates do they produce?
hyp = [c for c in rc2.get('claims', []) if c.get('derivation_type') == 'hypothesis_inference']
print(f"\n  hypothesis_inference claims: {len(hyp)}")
for c in hyp[:5]:
    print(f"  {c.get('predicate')}: {c.get('object_value')}")