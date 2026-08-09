"""Which instrument actually produced the PROMPTED_AGENT rows? Check per-row sha/tag + git status."""
import json, collections, subprocess

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

print("per-row instrument columns per arm:")
for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"):
    sub = [r for r in rows if r["arm"] == arm]
    shas = collections.Counter(r.get("prompt_freeze_sha") for r in sub)
    tags = collections.Counter(r.get("instrument_tag") for r in sub)
    ts = collections.Counter(r.get("timestamp") for r in sub)
    print(f"  {arm:16s}: sha={dict(shas)}")
    print(f"             tag={dict(tags)}")

# timestamp range for PROMPTED rows
prows = [r for r in rows if r["arm"] == "PROMPTED_AGENT"]
import datetime
ts_vals = [r["timestamp"] for r in prows if r.get("timestamp")]
if ts_vals:
    lo, hi = min(ts_vals), max(ts_vals)
    print("\nPROMPTED timestamp range:", datetime.datetime.utcfromtimestamp(lo), "->", datetime.datetime.utcfromtimestamp(hi))

# git status: which files differ from HEAD
out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=".")
print("\ngit status (worktree vs HEAD):")
print(out.stdout[:2500])

# what does HEAD's frozen runner ARMS look like?
out2 = subprocess.run(["git", "show", "HEAD:scripts/run_rbs_v4_holdout_frozen.py"], capture_output=True, text=True, cwd=".")
lines = [l for l in out2.stdout.splitlines() if "ARMS" in l or "PROMPTED" in l]
print("\nHEAD frozen runner ARMS/PROMPTED lines:", lines[:5])