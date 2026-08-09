"""Analyze validation-100 results."""
import json
from pathlib import Path

rows = [json.loads(l) for l in (Path("evaluations/campaign/rbs_v4_validation_100.jsonl")).read_text().splitlines() if l.strip()]
print(f"Total rows: {len(rows)}")

for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    arm_rows = [r for r in rows if r.get("config") == arm]
    scores = [r["score"] for r in arm_rows if r.get("score") is not None]
    verdicts = [r["verdict"] for r in arm_rows if r.get("verdict")]
    disp = [r.get("actions_dispatched", 0) for r in arm_rows]
    pfail = [r.get("provider_failures", 0) for r in arm_rows]
    print(f"\n{arm} ({len(arm_rows)} runs):")
    print(f"  Scores: {len(scores)} runs, mean={sum(scores)/len(scores):.3f} min={min(scores):.3f} max={max(scores):.3f}")
    print(f"  Verdicts: {dict((v, verdicts.count(v)) for v in set(verdicts))}")
    print(f"  Actions dispatched: avg={sum(disp)/len(disp):.1f}")
    print(f"  Provider failures: {sum(pfail)}")

print("\n--- By family ---")
for fam in ["known-observable", "signal-noise", "false-lead", "contradiction", "forbidden-proximity"]:
    fam_rows = [r for r in rows if r.get("template") == fam]
    scores = [r["score"] for r in fam_rows if r.get("score") is not None]
    print(f"{fam:20s}: {len(scores)} runs, mean={sum(scores)/len(scores):.3f}")

print("\n--- PROMPTED_AGENT detailed ---")
pa = [r for r in rows if r.get("config") == "PROMPTED_AGENT"]
for r in pa:
    print(f"  {r['template']:20s} s{r['seed']}: score={r['score']:.3f} verdict={r['verdict']} disp={r.get('actions_dispatched')}")