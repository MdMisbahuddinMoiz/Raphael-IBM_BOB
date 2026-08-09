"""Verify: (1) ledger has AMENDMENT-MODEL-550B entry + holdout entry intact,
(2) .env keys match the two keys SENTINEL provided (by hash only),
(3) which absolute seeds were touched by every existing collection (quarantine + validation + dev)."""
import json, hashlib, glob
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
CAM = ROOT / "evaluations/campaign"

print("=== 1. LEDGER ===")
d = json.load(open(CAM / "AMENDMENT_LEDGER.json"))
for e in d["entries"]:
    print(f'  {e["amendment_id"]:40s} | {e.get("title","")[:60]}')
ids = [e["amendment_id"] for e in d["entries"]]
print("  AMENDMENT-MODEL-550B-2026-08-09 present:", "AMENDMENT-MODEL-550B-2026-08-09" in ids)
print("  AMENDMENT-HOLDOUT-LAUNCH-2026-08-07 preserved:", "AMENDMENT-HOLDOUT-LAUNCH-2026-08-07" in ids)

print("\n=== 2. .env KEYS vs SENTINEL-PROVIDED (hashes only) ===")
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
sentinel_keys = [
    "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",
    "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",
]
print("  env NVIDIA_API_KEY_A present:", bool(env.get("NVIDIA_API_KEY_A")),
      "len:", len(env.get("NVIDIA_API_KEY_A", "")))
print("  env NVIDIA_API_KEY_B present:", bool(env.get("NVIDIA_API_KEY_B")),
      "len:", len(env.get("NVIDIA_API_KEY_B", "")))
for i, k in enumerate(sentinel_keys):
    h = hashlib.sha256(k.encode()).hexdigest()[:16]
    match_a = env.get("NVIDIA_API_KEY_A") == k
    match_b = env.get("NVIDIA_API_KEY_B") == k
    print(f"  sentinel key #{i+1} sha256[:16]={h} -> matches env A: {match_a}, env B: {match_b}")

print("\n=== 3. SEEDS TOUCHED BY EVERY COLLECTION ===")
def seedset(f, seedkey="seed", abskey="abs_seed"):
    s = set()
    for line in open(f):
        try:
            r = json.loads(line)
            for k in (seedkey, abskey):
                v = r.get(k)
                if isinstance(v, int):
                    s.add(v)
        except Exception:
            pass
    return s

for pat in ["rbs_v4_holdout*.jsonl", "rbs_v4_validation*.jsonl", "rbs_v4_repair_verify*.jsonl",
            "rbs_v4_dev*.jsonl", "rbs_v4_pilot*.jsonl", "rbs_v4_benchmark*.json"]:
    for f in sorted(glob.glob(str(CAM / pat))):
        s = seedset(f)
        if s:
            print(f"  {Path(f).name:55s} seeds: {min(s)}..{max(s)} (n={len(s)})")

print("\n=== 4. HOLDOUT SPLIT UNTOUCHED WINDOW (abs 2000..9999) ===")
holdout_touched = seedset(str(CAM / "rbs_v4_holdout.jsonl"))
quar_touched = seedset(str(CAM / "rbs_v4_holdout_STALE_T1T12_GPTOSS_QUARANTINE.jsonl"))
print("  holdout.jsonl abs seeds:", sorted(holdout_touched)[:5], "...", sorted(holdout_touched)[-5:] if holdout_touched else None)
print("  quarantine abs seeds:", sorted(quar_touched)[:10] if quar_touched else "(none/other key)")
