"""D1-B: byte-compare current LLMOnly adapter vs bd6ddbac original; PROMPTED_AGENT history."""
import subprocess

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return r.stdout + r.stderr

# 1) diff class LLMOnlyConclusionAdapter between bd6ddbac version and working tree
out = run(["git", "show", "bd6ddbac:arena/conclusion_adapters.py"])
with open("/tmp/orig_adapters.py", "w") as f:
    f.write(out)

import re
cur = open("src/arena/conclusion_adapters.py").read()

def extract(src_text, cls):
    m = re.search(r"class " + cls + r":(.*?)(?=\nclass |\Z)", src_text, re.S)
    return m.group(1) if m else None

orig_text = out
for cls in ("LLMOnlyConclusionAdapter", "FullConclusionAdapter", "NoWorldModelConclusionAdapter"):
    a = extract(orig_text, cls)
    b = extract(cur, cls)
    same = a == b
    print(f"{cls}: bd6ddbac == current ? {same}  (orig_len={len(a) if a else -1}, cur_len={len(b) if b else -1})")

# 2) does the ORIGINAL version already lack the semantic path in LLMOnly?
o_llm = extract(orig_text, "LLMOnlyConclusionAdapter")
print("\nORIGINAL LLMOnly adapter calls:")
for fn in ("_semantic_inference_to_claims", "_hypothesis_to_claims", "_evidence_to_claims",
           "_evidence_to_llm_claims", "_world_model_to_claims", "_plan_decision_to_claims"):
    print(f"  {fn}: {'YES' if fn in o_llm else 'no'}")

# 3) NoWorldModel adapter (original): keep or drop semantic path?
o_nwm = extract(orig_text, "NoWorldModelConclusionAdapter")
print("\nORIGINAL NoWorldModel adapter calls:")
for fn in ("_semantic_inference_to_claims", "_hypothesis_to_claims", "_evidence_to_claims",
           "_evidence_to_llm_claims", "_world_model_to_claims"):
    print(f"  {fn}: {'YES' if fn in o_nwm else 'no'}")

# 4) ablation.py PROMPTED_AGENT git history
out4 = run(["git", "log", "--all", "--oneline", "--", "src/arena/ablation.py", "arena/ablation.py"])
print("\n=== ablation.py history ===")
print(out4)
out5 = run(["git", "blame", "-L", "215,240", "src/arena/ablation.py"])
print("\n=== blame lines 215-240 ablation.py ===")
print(out5)