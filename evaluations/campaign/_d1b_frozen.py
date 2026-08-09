"""D1-B decisive: did the FROZEN instrument (git 74e52edd) define PROMPTED_AGENT?
Also: what prompt does the frozen runner use for the PROMPTED_AGENT arm, and does the
research spec define it as (a) failed raw tool-loop w/ scaffold or (b) intent-pure.
"""
import subprocess

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return r.stdout + r.stderr

# 1) frozen commit 74e52edd: does ablation.py contain PROMPTED_AGENT?
out = run(["git", "show", "74e52edd:src/arena/ablation.py"])
print("frozen(74e52edd) ablation.py has PROMPTED_AGENT:", "PROMPTED_AGENT" in out)
# print the block
import re
m = re.search(r"# PROMPTED_AGENT.*?\nPROMPTED_AGENT = AblationConfig\(.*?\n\)", out, re.S)
print("--- block in frozen commit ---")
print(m.group(0) if m else "NOT FOUND in 74e52edd")
m2 = re.search(r"PROMPTED_AGENT = AblationConfig\(.*?\n\)", out, re.S)
print("--- config in frozen commit ---")
print(m2.group(0)[:600] if m2 else "CONFIG NOT FOUND")

# 2) frozen runner: ARMS + how PROMPTED_AGENT config obtained + prompt text
out2 = run(["git", "show", "74e52edd:scripts/run_rbs_v4_holdout_frozen.py"])
print("\nfrozen runner has PROMPTED_AGENT:", "PROMPTED_AGENT" in out2)
print("ARMS line:", [l for l in out2.splitlines() if "ARMS" in l and "=" in l][:3])
# what prompt builder / config source
for l in out2.splitlines():
    if "ABLATION_PRESETS" in l or "ablation." in l and "import" in l or "PROMPTED_AGENT" in l:
        print("RUNNER:", l.strip()[:130])

# 3) research spec location & wording
import glob
for f in glob.glob("**/RBS-v4_RESEARCH_SPECIFICATION*.json", recursive=True):
    txt = open(f).read()
    print("\nSPEC FILE:", f)
    for kw in ("PROMPTED", "prompted", "raw tool", "no scaffold", "LLM_ONLY", "prompt-only"):
        idxs = [m.start() for m in re.finditer(kw, txt)]
        if idxs:
            i = idxs[0]
            print(f"  [{kw}] ...{txt[max(0,i-160):i+220].replace(chr(10),' ')}...")
            break

# 4) current vs committed ablation.py diff for PROMPTED region
outdiff = run(["git", "diff", "--", "src/arena/ablation.py"])
print("\ndiff ablation.py (worktree vs HEAD) len:", len(outdiff))
print(outdiff[:1200])