"""Determine the actual ablation.py state at holdout collection time."""
import subprocess, json, re

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return r.stdout + r.stderr

# 1) HEAD ablation.py has PROMPTED_AGENT?
out = run(["git", "show", "HEAD:src/arena/ablation.py"])
print("HEAD ablation.py has PROMPTED_AGENT:", "PROMPTED_AGENT" in out)
if "PROMPTED_AGENT" in out:
    m = re.search(r"# PROMPTED_AGENT.*?\nPROMPTED_AGENT = AblationConfig\(.*?\n\)", out, re.S)
    print("--- HEAD block ---")
    print(m.group(0)[:800] if m else out[out.index("PROMPTED_AGENT"):][:800])

# 2) HEAD runner: ARMS + PRESETS use
out2 = run(["git", "show", "HEAD:scripts/run_rbs_v4_holdout_frozen.py"])
print("\nHEAD runner has PROMPTED_AGENT:", "PROMPTED_AGENT" in out2)
for l in out2.splitlines():
    if "ARMS" in l and "=" in l:
        print("  ARMS line:", l.strip())
    if "ABLATION_PRESETS[" in l:
        print("  PRESETS ref:", l.strip())

# 3) worktree diff on the runner script
out3 = run(["git", "diff", "--stat", "HEAD", "--", "scripts/"])
print("\ndiff stat scripts/:", out3[:800])
out4 = run(["git", "status", "--porcelain"])
print("\nporcelain:")
print(out4[:1500])

# 4) real collection timestamps + run dir dates
rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
ts = sorted({r["timestamp"] for r in rows if r.get("timestamp")})
print("\nJSONL timestamps (unique, sorted):")
for t in ts[:8]:
    print("  ", t)
print("  ... total unique:", len(ts))

# 5) run dir mtime of a PROMPTED run dir
import os, glob
p = "arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout"
if os.path.isdir(p):
    import datetime
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(p, "episodes.jsonl")), datetime.timezone.utc)
    print("PROMPTED s0000 episodes mtime:", mt)