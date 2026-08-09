"""Deep diagnostic: why does semantic inference produce no evidence?

Checks: llm_service counters, run_inference result type, provider reachability,
select_diverse_evidence output, envelope build.
"""
import sys, json

for p in ("/home/yaser/raphael-2.0-rbsv2r/src",
          "/home/yaser/raphael-2.0-rbsv2r/scripts",
          "/home/yaser/raphael-2.0-rbsv2r"):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/scripts")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

from arena.ablation_runner import AblationRunner, select_diverse_evidence
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS

template = TEMPLATE_REGISTRY["contradiction"]
runner = AblationRunner(
    template=template,
    config=ABLATION_PRESETS["PROMPTED_AGENT"],
    seed=0,
    split="holdout",
)
runner.run()

print("=" * 70)
print("DEEP DIAGNOSTIC")
print("=" * 70)
print("metrics.llm_calls:", runner.metrics.llm_calls)
print("metrics.provider_failures:", runner.metrics.provider_failures)
print("metrics.input_tokens:", runner.metrics.input_tokens)
print("metrics.output_tokens:", runner.metrics.output_tokens)

ls = getattr(runner, "_llm_service", None)
print("\n_llm_service exists:", ls is not None)
if ls is not None:
    print("  call_count:", ls.call_count)
    print("  logical_llm_calls:", ls.logical_llm_calls)
    print("  provider_failures:", ls.provider_failures)
    print("  system_prompt set:", ls.system_prompt is not None)

# Manually exercise the pipeline to see where it stops
ar = runner.arena_runner
eg = ar.evidence_graph
all_ev = eg.get_all_evidence()
print("\nevidence count:", len(all_ev))

diverse = select_diverse_evidence(all_ev)
print("select_diverse_evidence ->", len(diverse), "items")
if diverse:
    print("first item keys:", sorted(diverse[0].keys()))
    eids = tuple(eid for item in diverse for eid in item.get('evidence_ids', []))
    print("evidence_ids extracted:", len(eids))

if ls is not None:
    from arena.semantic_inference import build_evidence_context, build_envelope
    text = build_evidence_context(diverse) if diverse else ""
    print("\nenvelope chars:", len(text))
    try:
        msgs = build_envelope(text, system_prompt=ls.system_prompt)
        print("envelope messages:", len(msgs))
        print("system prompt head:", (msgs[0]["content"][:120] if msgs else "NONE"))
    except Exception as e:
        print("envelope build ERROR:", repr(e))

    # Direct provider call test
    from arena.llm_service import call_llm_provider
    try:
        resp, err = call_llm_provider([{"role": "user", "content": "ping"}], ls.config)
        print("\nprovider call:", "OK" if err is None else f"ERROR={err}")
        print("response text head:", (resp.response_text[:150] if resp else "NONE"))
    except Exception as e:
        print("\nprovider call EXCEPTION:", repr(e))
