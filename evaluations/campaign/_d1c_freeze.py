"""D1-C2: compare current worktree hashes vs TERMINAL_VALIDATION_FREEZE.json 9-file set."""
import json, hashlib

freeze = json.load(open("evaluations/campaign/TERMINAL_VALIDATION_FREEZE.json"))
files = freeze["files_sha256"]

print(f"{'file':55s} {'frozen==current?':>16s}")
for f, h in files.items():
    try:
        cur = hashlib.sha256(open(f, "rb").read()).hexdigest()
    except Exception as e:
        print(f"{f:55s} MISSING/ERR {e}")
        continue
    match = "MATCH" if cur == h else "DIFF"
    print(f"{f:55s} {match:>10s}")
    if cur != h:
        print(f"    frozen: {h}")
        print(f"    current: {cur}")

# does frozen ablation.py hash correspond to a committed version with PROMPTED_AGENT?
import subprocess
# the frozen hash should match a blob in git history
out = subprocess.run(["git", "rev-list", "--all", "--objects"], capture_output=True, text=True, cwd=".")
# find blobs for src/arena/ablation.py in history
for l in out.stdout.splitlines():
    if "src/arena/ablation.py" in l:
        blob_sha = l.split()[0]
        r = subprocess.run(["git", "cat-file", "-p", blob_sha], capture_output=True, text=True, cwd=".")
        h = hashlib.sha256(r.stdout.encode()).hexdigest()
        has_pa = "PROMPTED_AGENT" in r.stdout
        print(f"blob {blob_sha[:12]}: sha256={h[:12]} has_PROMPTED={has_pa} {'<-- FROZEN?' if h == list(freeze['files_sha256'].values())[8] else ''}")