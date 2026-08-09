"""Confirm: does LLMOnly adapter convert semantic inferences? Does evidence persist on disk?"""
import json, os, glob, re

# 1) _semantic_inference_to_claims — where FULL's si_* claims come from
src = open("src/arena/conclusion_adapters.py").read()
lines = src.splitlines()
print("=== _semantic_inference_to_claims (lines 250-307) ===")
for i in range(249, 307):
    print(f"{i+1:4d}: {lines[i]}")

# 2) which adapters call it?
for i, ln in enumerate(lines, 1):
    if "_semantic_inference_to_claims" in ln:
        print(f"called at line {i}: {ln.strip()}")

# 3) semantic inference outputs for PROMPTED run: does evidence raw_content show?
# check if the run dir has any evidence store
d = "arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout"
for root, dirs, files in os.walk(d):
    for f in files:
        p = os.path.join(root, f)
        sz = os.path.getsize(p)
        if sz < 500000:
            txt = open(p, errors="replace").read()
            if "semantic" in txt.lower() or "8080" in txt:
                print(f"{p} ({sz}) contains 'semantic' or '8080'")

# 4) evidence graph store type used by runner — does it persist to disk at run dir?
import subprocess
r = subprocess.run(["grep", "-rn", "evidence_store\\|EvidenceStore\\|json.dump", "scripts/run_rbs_v4_holdout_frozen.py"], capture_output=True, text=True)
print("\nfrozen runner persistence refs:", r.stdout[:1000])