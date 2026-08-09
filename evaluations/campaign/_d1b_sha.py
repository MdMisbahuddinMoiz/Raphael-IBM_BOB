"""Decode prompt_freeze_sha semantics + how the worktree runner defines PROMPTED_AGENT."""
import subprocess

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return r.stdout + r.stderr

# 1) is 4c2f8464 a git commit?
out = run(["git", "cat-file", "-t", "4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a"])
print("cat-file type:", out.strip())
out2 = run(["git", "show", "--no-patch", "--oneline", "4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a"])
print("show:", out2.strip()[:200])

# 2) if it's a blob, what file is it?
out3 = run(["git", "rev-list", "--all", "--objects"])
hits = [l for l in out3.splitlines() if l.startswith("4c2f8464")]
print("object refs:", hits[:3])

# 3) where is prompt_freeze_sha computed in frozen runner (worktree)?
out4 = run(["grep", "-n", "prompt_freeze_sha\\|prompt_freeze\\|sha256", "scripts/run_rbs_v4_holdout_frozen.py"])
print("\nrunner sha refs:\n", out4[:1200])

# 4) worktree runner PROMPTED_AGENT definition
out5 = run(["grep", "-n", "PROMPTED_AGENT", "scripts/run_rbs_v4_holdout_frozen.py"])
print("\nrunner PROMPTED_AGENT lines:\n", out5[:1500])