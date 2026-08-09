"""Compare evidence/LLM claim channels: FULL vs PROMPTED_AGENT, same cell."""
import json, glob, os

base = "arena/results/raw"
cell = "known-observable"
seed = "s0000"

def load(p):
    try:
        return json.load(open(p))
    except Exception as e:
        return {"ERROR": str(e)}

def scan(arm):
    pat = f"{base}/abl_{arm}_{cell}_{seed}_holdout"
    dirs = sorted(glob.glob(pat))
    print(f"== {arm} (known-observable {seed}) dirs: {len(dirs)}")
    for d in dirs[:3]:
        ec = os.path.join(d, "evaluation.json")
        rc = os.path.join(d, "run_conclusion.json")
        ct = os.path.join(d, "component_traces.json")
        mf = os.path.join(d, "manifest.json")
        ev = load(ec); r = load(rc); ct = load(ct); m = load(mf)
        claims = r.get("claims", []) if isinstance(r, dict) else []
        print(f"  {os.path.basename(d)}")
        print(f"    manifest arch: {m.get('architecture_id') if isinstance(m, dict) else '?'} | adapter: {r.get('conclusion_adapter') if isinstance(r, dict) else r.get('adapter')}")
        print(f"    claims(n={len(claims)}): {[ (c.get('predicate'), str(c.get('object_value'))[:80]) for c in claims ][:6]}")
        # trace ops summary
        ops = {}
        if isinstance(ct, dict):
            tr = ct.get("traces") if isinstance(ct.get("traces"), list) else ct.get("components") or ct
            trl = tr if isinstance(tr, list) else []
            for t in trl:
                k = (t.get("component"), t.get("operation"))
                ops[k] = ops.get(k, 0) + 1
            print(f"    trace ops: {ops}")
        else:
            print(f"    trace type: {type(ct)}")

import re
scan("FULL_RAPHAEL")
scan("PROMPTED_AGENT")