"""Final check: FULL has_service claim shape vs evaluator check text for s0 pair."""
import json, os

# FULL known-observable s0000 run_conclusion: find has_service / observed claims
rc = json.load(open("arena/results/raw/abl_FULL_RAPHAEL_known-observable_s0000_holdout/run_conclusion.json"))
cl = rc.get("claims") or []
print("FULL s0 run_conclusion keys:", list(rc.keys())[:20])
print("FULL claims:", len(cl))
hs = [c for c in cl if c.get("predicate") == "has_service"]
print(f"has_service claims: {len(hs)}")
for c in hs[:3]:
    print("  ", json.dumps(c)[:260])
# observed_property that may carry port text
obs = [c for c in cl if c.get("predicate") == "observed_property"]
for c in obs[:5]:
    s = json.dumps(c)
    if "8080" in s or "80 " in s:
        print("  OBS>", s[:260])

# PROMPTED s0
rc2 = json.load(open("arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout/run_conclusion.json"))
cl2 = rc2.get("claims") or []
print("\nPROMPTED s0 claims:", len(cl2))
for c in cl2:
    print("  ", json.dumps(c)[:260])

# Does the PROMPTED evidence actually contain port-8080 observation? episodes evidence_available
# shows evidence ids; component_traces may carry semantic inference output ids only. Check
# evaluation details for the port check string exactly as the evaluator wrote it.
ev = json.load(open("arena/results/raw/abl_PROMPTED_AGENT_known-observable_s0000_holdout/evaluation.json"))
print("\nPROMPTED failed_checks:", ev["failed_checks"])
print("PROMPTED passed_checks:", ev["passed_checks"])

# what nmap observation content looks like in this scenario (read scenario def)
import glob
for f in glob.glob("src/**/scenario*", recursive=True)[:10]:
    pass
# check where "detected as open" evaluator check strings live
import subprocess
print("\nevaluator check-string source:")
r = subprocess.run(["grep", "-rn", "detected as open", "src/"], capture_output=True, text=True)
print(r.stdout[:2000] or r.stderr[:500])