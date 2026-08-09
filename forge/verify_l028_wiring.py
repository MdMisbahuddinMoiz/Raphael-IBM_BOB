"""Verify L-028 wiring integrity after Fix A: fallback + structured parser + adapter."""
import re

src = open("src/arena/conclusion_adapters.py", encoding="utf-8").read()

# 1. Call sites of the fallback heuristic
calls = [m.start() for m in re.finditer(r"_parse_fallback_heuristic\(", src)]
print("fallback calls:", len(calls))
for c in calls:
    line = src[:c].count("\n") + 1
    snippet = src[c:c + 120].split("\n")[0]
    print(f"  line {line}: {snippet}")

# 2. Call sites of structured parser
pcalls = [m.start() for m in re.finditer(r"_parse_structured_conclusion\(", src)]
print("structured parser calls:", len(pcalls))
for c in pcalls:
    line = src[:c].count("\n") + 1
    snippet = src[c:c + 120].split("\n")[0]
    print(f"  line {line}: {snippet}")

# 3. Effective fallback def signature
m = re.search(r"def _parse_fallback_heuristic\(([^)]*)\)", src)
print("\neffective fallback signature:", m.group(1) if m else "NOT FOUND")

# 4. LLMOnlyConclusionAdapter.build body (lines after class)
m2 = re.search(r"class LLMOnlyConclusionAdapter:.*?def build\(.*?\):", src, re.S)
print("\nLLMOnlyConclusionAdapter found:", bool(m2))

# 5. make_claim predicate usage inside effective fallback
eff_start = [x for x in [mm.start() for mm in re.finditer(r"def _parse_fallback_heuristic", src)]][-1]
eff = src[eff_start:]
preds = re.findall(r"ConclusionPredicate\.(\w+)", eff)
from collections import Counter
print("\npredicates used in effective fallback:", dict(Counter(preds)))
