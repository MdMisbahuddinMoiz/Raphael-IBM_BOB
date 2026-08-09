"""FORGE fix script step 2: apply surgical repairs to conclusion_adapters.py.

Fixes:
  A. Remove stray col-0 'try:' + duplicated for-loop header in _falsification_to_claims
     (single occurrence; leaves the original 4-space 'try:' and the real loop body).
  B. (dry-run first) compare the two _parse_fallback_heuristic definitions; if identical,
     remove the FIRST (dead, shadowed) copy per Minimal Repair Principle.

Run: .venv/bin/python forge/fix_conclusion_adapters.py --apply
     (without --apply: dry-run, prints what WOULD change)
"""
import sys
import re

PATH = "src/arena/conclusion_adapters.py"

with open(PATH, "r", encoding="utf-8", newline="") as f:
    src = f.read()

original = src
report = []

# ── FIX A: stray try ─────────────────────────────────────────────
stray = "\ntry:\n        for fr in falsification_results:\n            if not fr:\n                continue\n            \n"
idx = src.find(stray)
if idx != -1:
    # ensure the char before is a blank line (4-space indent line = '    '), not something else
    prefix = src[max(0, idx - 6):idx]
    line_no = src[:idx].count("\n") + 1
    report.append(f"[A] stray 'try:' at line {line_no}; prefix={prefix!r}")
    src = src[:idx] + "\n" + src[idx + len(stray):]
    report.append(f"[A] removed {len(stray)} chars (stray try + dup loop header)")
else:
    report.append("[A] stray pattern NOT found — already fixed?")

# ── FIX B: duplicate fallback heuristic ──────────────────────────
defs = [m.start() for m in re.finditer(r"def _parse_fallback_heuristic", src)]
if len(defs) == 2:
    s1, s2 = defs[0], defs[1]
    # find end of first def: next top-level def after s1
    nxt = src.find("\ndef ", s1 + 10)
    end1 = nxt if nxt != -1 else s2
    first_def = src[s1:end1]
    # find end of second def: next top-level def/class after s2
    nxt2 = src.find("\ndef ", s2 + 10)
    nxt3 = src.find("\nclass ", s2 + 10)
    ends = [x for x in (nxt2, nxt3) if x != -1]
    end2 = min(ends) if ends else len(src)
    second_def = src[s2:end2]
    same = first_def.strip() == second_def.strip()
    report.append(f"[B] two defs: first {len(first_def)} chars, second {len(second_def)} chars, identical={same}")
    if same:
        report.append(f"[B] would remove first copy (lines {s1 + 1}..{end1 + 1} approx)")
        if "--apply" in sys.argv:
            src = src[:s1] + src[end1:]
            report.append("[B] REMOVED dead first copy")
else:
    report.append(f"[B] fallback def count = {len(defs)} (expected 2 for dedup step)")

# ── Verify ───────────────────────────────────────────────────────
changed = src != original
report.append(f"changed: {changed} (size {len(original)} -> {len(src)})")

if "--apply" in sys.argv:
    with open(PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    report.append("written to disk (LF endings)")
else:
    report.append("DRY RUN — nothing written (pass --apply to commit)")

print("\n".join(report))
