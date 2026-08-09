"""Record GATE PASSED verdict in L028_VERIFICATION.json (single-shot run, no re-run)."""
import json

path = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/L028_VERIFICATION.json"
d = json.load(open(path))

fb = sum(1 for s in d["samples"] if s["fallback_fired"])
mech = sum(1 for s in d["samples"] if s["claim_count"] == 0)
strict = sum(1 for s in d["samples"] if s["sample_pass"])

d["gate_verdict"] = {
    "criterion": "SENTINEL gate: >= 8/10 runs produce fallback-sourced typed predicates; stop if >= 2/10 MECHANICAL",
    "fallback_sourced_typed_predicates": f"{fb}/10",
    "mechanical_runs": f"{mech}/10",
    "strict_pass_with_zero_provider_failures": f"{strict}/10",
    "result": "GATE PASSED" if (fb >= 8 and mech < 2) else "GATE FAILED",
    "note": ("2 samples carried a single transient provider failure (HTTP 503 ResourceExhausted) "
             "but STILL produced fallback-sourced typed predicates. forbidden-proximity s=1 had "
             "no extractable service phrasing in model output (no-invention contract). "
             "Provider failures are INFRA class per FREEZE-02, not architecture defects."),
}

with open(path, "w") as f:
    json.dump(d, f, indent=2)
print("verdict recorded:", d["gate_verdict"]["result"])
