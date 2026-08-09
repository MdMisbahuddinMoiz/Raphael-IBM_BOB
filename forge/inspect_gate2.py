import json
d = json.load(open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_VERIFICATION.json"))
for s in d["samples"]:
    print(f"{s['template']:20s} s={s['seed']} | fb={s['fallback_fired']} "
          f"l028={len(s['l028_predicates'])} mi={s['model_inference_evidence']} "
          f"lsfail={s['llm_service_provider_failures']} pass={s['sample_pass']}")
