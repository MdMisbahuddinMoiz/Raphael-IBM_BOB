import json
d = json.load(open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_VERIFICATION.json"))
for s in d["samples"]:
    if s["template"] in ("known-observable", "forbidden-proximity", "contradiction"):
        print(s["template"], s["seed"],
              "| fb=", s["fallback_fired"],
              "| l028=", s["l028_predicates"],
              "| mi=", s["model_inference_evidence"],
              "| lsfail=", s["llm_service_provider_failures"],
              "| pass=", s["sample_pass"],
              "| allpreds=", s["fallback_predicates"])
