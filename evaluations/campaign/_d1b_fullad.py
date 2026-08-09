"""Confirm FullConclusionAdapter behavior when brain components are disabled (PROMPTED_AGENT run)."""
import json

rc = json.load(open("arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout/run_conclusion.json"))
print("PROMPTED run_conclusion keys:", list(rc.keys()))
print("decision:", rc.get("decision"))
print("architecture_id:", rc.get("architecture_id"))
cl = rc.get("claims") or []
print("claims:", len(cl))
for c in cl:
    print("  ", json.dumps(c)[:300])

# hypothesis_manager in FULL vs PROMPTED traces
import json as j
for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT"):
    ct = j.load(open(f"arena/results/raw/abl_{arm}_known-observable_s0000_holdout/component_traces.json"))
    ops = {}
    tr = ct.get("traces", []) if isinstance(ct, dict) else []
    for t in tr:
        k = (t.get("component"), t.get("operation"))
        ops[k] = ops.get(k, 0) + 1
    hypo = {k: v for k, v in ops.items() if k[0] == "hypothesis"}
    print(f"\n{arm} hypothesis ops: {hypo}")