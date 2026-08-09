"""D1-B final: legacy LLM_ONLY claim profile + preregistration/final-report PROMPTED_AGENT spec."""
import json, glob, collections, subprocess

# 1) legacy abl_LLM_ONLY dirs before holdout: evaluation verdicts + claim counts
legacy = glob.glob("arena/results/raw/abl_LLM_ONLY_*")
print(f"legacy LLM_ONLY runs on disk: {len(legacy)}")
prof = collections.Counter()
port_pass = 0
port_fail = 0
n_eval = 0
for d in legacy:
    evp = d + "/evaluation.json"
    import os
    if not os.path.exists(evp):
        continue
    n_eval += 1
    try:
        ev = json.load(open(evp))
    except Exception:
        continue
    prof[(ev.get("verdict"))] += 1
    for c in ev.get("passed_checks") or []:
        if "Port " in c:
            port_pass += 1
    for c in ev.get("failed_checks") or []:
        if "Port " in c:
            port_fail += 1
print(f"evaluations read: {n_eval}; verdict dist: {dict(prof)}")
print(f"port-related passed: {port_pass}; port-related failed: {port_fail}")

# show one pass example with port text
for d in legacy:
    evp = d + "/evaluation.json"
    try:
        ev = json.load(open(evp))
    except Exception:
        continue
    for c in ev.get("passed_checks") or []:
        if "Port " in c:
            print(f"\nPASS example: {d}\n  {c}")
            try:
                rc = json.load(open(d + "/run_conclusion.json"))
                cl = rc.get("claims") or []
                print(f"  claims: {len(cl)}", [ (x.get('predicate'), str(x.get('object_value'))[:90]) for x in cl[:5] ])
            except Exception as e:
                print("  no run_conclusion:", e)
            break
    else:
        continue
    break

# 2) prereg/final report: what does PROMPTED_AGENT / prompted control arm say?
def cat(fname):
    try:
        return open(fname).read()
    except Exception as e:
        return f"ERR {e}"

for f in ("evaluations/campaign/TERMINAL_FALSIFICATION_PREREGISTRATION.json",
          "evaluations/rbs_v4_final_report.md",
          "RBS-v4_RESEARCH_SPECIFICATION.json"):
    print("\n" + "=" * 70)
    print("FILE:", f)
    txt = cat(f)
    print(txt[:400] if txt.startswith("ERR") else "[content available, len=%d]" % len(txt))

# grep for PROMPTED / prompted / llm-only across docs
out = subprocess.run(["grep", "-rln", "PROMPTED_AGENT", "evaluations/", "configs/", "docs/", "benchmarks/"], capture_output=True, text=True)
print("\nfiles mentioning PROMPTED_AGENT:")
print(out.stdout[:1500])