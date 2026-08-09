"""Final Pre-Flight E2E Trace: FULL_RAPHAEL vs PROMPTED_AGENT on known-observable seed 0."""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path("/home/yaser/raphael-2.0-rbsv2r/src")))

from arena.ablation_runner import AblationRunner
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS

template = TEMPLATE_REGISTRY["known-observable"]

def trace_run(config_id, label):
    print(f"\n{'='*60}")
    print(f"E2E TRACE: {label} (config={config_id})")
    print(f"{'='*60}")
    
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=0,
        split="holdout",
        output_dir="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/preflight_traces",
        llm_config_override=None,
    )
    
    # Monkey-patch to capture broker invocations
    # The broker is invoked via runner.arena_runner.propose_action
    # We need to wrap it after the arena_runner is created
    # The arena_runner is created in _run_* methods
    broker_calls = []
    llm_calls = []
    
    # We'll trace by patching the CapabilityBroker.propose_action
    from orchestrator.brain.capability_broker import CapabilityBroker
    orig_broker_propose = CapabilityBroker.propose_action
    
    def traced_broker_propose(self, target, action_type, capability, method="auto", **kwargs):
        result = orig_broker_propose(self, target, action_type, capability, method, **kwargs)
        broker_calls.append({
            "target": target,
            "action_type": action_type,
            "capability": capability,
            "method": method,
            "decision": getattr(result, 'decision', 'unknown'),
            "reason": getattr(result, 'reason', ''),
        })
        return result
    
    CapabilityBroker.propose_action = traced_broker_propose
    
    # Capture LLM calls for PROMPTED_AGENT
    if hasattr(runner, '_llm_service') and runner._llm_service:
        orig_infer = runner._llm_service.run_inference
        def traced_infer(obs_text, ev_ids, run_id):
            result = orig_infer(obs_text, ev_ids, run_id)
            llm_calls.append({
                "obs_preview": obs_text[:200],
                "result_type": type(result).__name__,
                "has_inference": hasattr(result, 'inference_id'),
            })
            return result
        runner._llm_service.run_inference = traced_infer
    
    t0 = time.time()
    metrics = runner.run()
    elapsed = time.time() - t0
    
    # Results
    m = metrics.to_dict()
    print(f"Run time: {elapsed:.1f}s")
    print(f"Score: {runner.evaluation_result.score if runner.evaluation_result else None}")
    print(f"Verdict: {runner.evaluation_result.verdict.value if runner.evaluation_result and hasattr(runner.evaluation_result, 'verdict') else None}")
    print(f"Actions dispatched: {m.get('actions_dispatched')}")
    print(f"Actions authorized: {m.get('actions_authorized')}")
    print(f"Actions denied: {m.get('actions_denied')}")
    print(f"Broker calls: {len(broker_calls)}")
    for i, bc in enumerate(broker_calls):
        print(f"  [{i}] {bc['action_type']} {bc['capability']} {bc['target']} -> {bc['decision']} ({bc['reason']})")
    if llm_calls:
        print(f"LLM calls: {len(llm_calls)}")
        for i, lc in enumerate(llm_calls):
            print(f"  [{i}] type={lc['result_type']} has_inference={lc['has_inference']}")
    
    return {
        "config": config_id,
        "metrics": m,
        "broker_calls": broker_calls,
        "llm_calls": llm_calls,
    }

# Run both
full_trace = trace_run("FULL_RAPHAEL", "FULL_RAPHAEL")
prompted_trace = trace_run("PROMPTED_AGENT", "PROMPTED_AGENT")

# Summary
print(f"\n{'='*60}")
print("SUMMARY COMPARISON")
print(f"{'='*60}")
for t in [full_trace, prompted_trace]:
    m = t["metrics"]
    print(f"\n{t['config']}:")
    print(f"  actions_dispatched: {m.get('actions_dispatched')}")
    print(f"  actions_authorized: {m.get('actions_authorized')}")
    print(f"  actions_denied: {m.get('actions_denied')}")
    print(f"  broker_calls: {len(t['broker_calls'])}")
    if t.get('llm_calls'):
        print(f"  llm_calls: {len(t['llm_calls'])}")
    # Check candidate generation
    cand_count = sum(1 for bc in t['broker_calls'])
    print(f"  candidates_proposed: {cand_count}")

# Save traces
with open("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/preflight_e2e_trace.json", "w") as f:
    json.dump({
        "FULL_RAPHAEL": full_trace,
        "PROMPTED_AGENT": prompted_trace,
    }, f, indent=2, default=str)

print(f"\nTraces saved to evaluations/campaign/preflight_e2e_trace.json")