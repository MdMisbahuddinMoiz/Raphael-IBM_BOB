"""Dump evidence + model_inference evidence content for PROMPTED & FULL runs."""
import json, os, glob

base = "arena/results/raw"
cell, seed = "known-observable", "s0000"

def dump_arm(arm):
    d = f"{base}/abl_{arm}_{cell}_{seed}_holdout"
    print(f"\n######## {arm} {d}")
    # find evidence store files
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        print(f"  file: {fn}  ({os.path.getsize(p)} bytes)")
    # check episodes for observation content
    ep_path = os.path.join(d, "episodes.jsonl")
    if os.path.exists(ep_path):
        obs_texts = []
        inf_texts = []
        for ln in open(ep_path):
            try:
                ev = json.loads(ln)
            except Exception:
                continue
            # look for evidence / observation payload
            if "observation" in ev and isinstance(ev["observation"], dict):
                obs_texts.append(ev["observation"])
            for k in ("evidence_snapshot", "evidence", "context"):
                if k in ev:
                    obs_texts.append(ev[k])
        print(f"  episodes: {len(obs_texts)} payload entries")
        # print first observation payload keys
        if obs_texts:
            o0 = obs_texts[0]
            print(f"  first payload type={type(o0)} keys={list(o0.keys())[:12] if isinstance(o0, dict) else 'n/a'}")
            s = json.dumps(o0)[:600]
            print(f"  sample: {s}")

dump_arm("PROMPTED_AGENT")
dump_arm("FULL_RAPHAEL")