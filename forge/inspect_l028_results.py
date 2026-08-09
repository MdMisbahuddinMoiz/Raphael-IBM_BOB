"""Inspect claim predicates + provenance in L028_VERIFICATION.json v2."""
import json

d = json.load(open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_VERIFICATION.json"))
print("verification:", d.get("verification"))
print("note:", d.get("note", ""))
print()
for r in d["samples"]:
    print(f"{r['template']:20s} s={r['seed']}: mi={r['model_inference_evidence']} "
          f"claims={r['claim_count']} preds={r['claim_predicates']}")
