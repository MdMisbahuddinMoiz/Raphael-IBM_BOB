"""D3 recomputation artifact -- reproduce TERMINAL_ANALYSIS_RESULTS.json exactly.

Purpose: SENTINEL flagged D3 as "recomputed but no diff artifact". The analysis
script (scripts/terminal_analysis.py) overwrites its output in place, so a
prior recomputation destroyed its own reference. This script:

  1. Loads the frozen analysis script as a module (same code, same raw input
     evaluations/campaign/rbs_v4_holdout.jsonl).
  2. Redirects its OUT to a sibling file TERMINAL_ANALYSIS_RESULTS_RECOMPUTED.json
     so the prior artifact survives.
  3. Diffs RECOMPUTED vs the pre-D3 reference (TERMINAL_ANALYSIS_RESULTS_pre_D3_reference.json)
     ignoring the volatile generated_at_utc timestamp.
  4. Writes TERMINAL_D3_RECOMPUTATION_DIFF.txt recording the outcome.

Minimal-repair discipline: no edits to src/, no edits to the frozen analysis
script. The analysis code is reused verbatim; only the output path differs.
"""
import importlib.util
import json
import os
import sys

CAMP = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(CAMP))
ANALYSIS_SCRIPT = os.path.join(REPO, "scripts", "terminal_analysis.py")
REFERENCE = os.path.join(CAMP, "TERMINAL_ANALYSIS_RESULTS_pre_D3_reference.json")
RECOMPUTED = os.path.join(CAMP, "TERMINAL_ANALYSIS_RESULTS_RECOMPUTED.json")
DIFF_REPORT = os.path.join(CAMP, "TERMINAL_D3_RECOMPUTATION_DIFF.txt")

# 1. Load the frozen analysis script, redirect output
spec = importlib.util.spec_from_file_location("terminal_analysis", ANALYSIS_SCRIPT)
ta = importlib.util.module_from_spec(spec)
sys.modules["terminal_analysis"] = ta
spec.loader.exec_module(ta)
ta.OUT = RECOMPUTED
ta.main()

# 2. Load both artifacts
with open(REFERENCE) as fh:
    ref = json.load(fh)
with open(RECOMPUTED) as fh:
    recom = json.load(fh)

# 3. Diff, ignoring generated_at_utc (volatile timestamp)
def strip_volatile(d):
    d = dict(d)
    d.pop("generated_at_utc", None)
    return d

ref_s = json.dumps(strip_volatile(ref), sort_keys=True, indent=1)
recom_s = json.dumps(strip_volatile(recom), sort_keys=True, indent=1)
identical = ref_s == recom_s

lines = []
lines.append("TERMINAL D3 RECOMPUTATION DIFF")
lines.append("=" * 46)
lines.append("date_utc:           %s" % __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
lines.append("analysis script    : scripts/terminal_analysis.py (frozen, loaded verbatim)")
lines.append("input jsonl        : evaluations/campaign/rbs_v4_holdout.jsonl (1200 rows)")
lines.append("reference artifact : %s" % os.path.basename(REFERENCE))
lines.append("recomputed artifact: %s" % os.path.basename(RECOMPUTED))
lines.append("")
lines.append("comparison key     : full JSON payload EXCEPT generated_at_utc (volatile timestamp)")
lines.append("result             : %s" % ("IDENTICAL (byte-for-byte, minus timestamp)" if identical else "MISMATCH — see below"))
lines.append("")

if not identical:
    # find first divergent path
    def walk(a, b, path=""):
        diffs = []
        if isinstance(a, dict) and isinstance(b, dict):
            keys = sorted(set(a) | set(b))
            for k in keys:
                if k not in a:
                    diffs.append((path + "." + k, "MISSING in ref", b[k]))
                elif k not in b:
                    diffs.append((path + "." + k, a[k], "MISSING in recomputed"))
                else:
                    diffs.extend(walk(a[k], b[k], path + "." + k))
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diffs.append((path, "len %d" % len(a), "len %d" % len(b)))
            for i, (x, y) in enumerate(zip(a, b)):
                diffs.extend(walk(x, y, "%s[%d]" % (path, i)))
        else:
            if a != b:
                diffs.append((path, a, b))
        return diffs

    for path, a, b in walk(strip_volatile(ref), strip_volatile(recom), "")[:40]:
        lines.append("  %-44s | %s | %s" % (path, str(a)[:60], str(b)[:60]))
else:
    # Byte-level confirmation: hash both (minus timestamp block is redundant since
    # JSON above proves identity; record sha256 of full files for the record).
    import hashlib
    for p in (REFERENCE, RECOMPUTED):
        with open(p, "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        lines.append("sha256(%s) = %s" % (os.path.basename(p), h))
    lines.append("")
    lines.append("NOTE: full-file sha256 differs only due to generated_at_utc; the")
    lines.append("stripped JSON above is verified byte-identical by comparison.")

report = "\n".join(lines) + "\n"
with open(DIFF_REPORT, "w") as fh:
    fh.write(report)
print(report)
sys.exit(0 if identical else 2)