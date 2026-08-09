"""Inspect effective _parse_fallback_heuristic (second copy) after Fix A."""
import re

src = open("src/arena/conclusion_adapters.py", encoding="utf-8").read()
defs = [m.start() for m in re.finditer(r"def _parse_fallback_heuristic", src)]
print("fallback def count after A:", len(defs))
if len(defs) >= 2:
    s2 = defs[1]
    nxt2 = src.find("\ndef ", s2 + 10)
    nxt3 = src.find("\nclass ", s2 + 10)
    ends = [x for x in (nxt2, nxt3) if x != -1]
    end2 = min(ends) if ends else len(src)
    eff = src[s2:end2]
    print("effective def chars:", len(eff))
    print("--- head ---")
    print("\n".join(eff.split("\n")[:12]))
    print("--- tail ---")
    print("\n".join(eff.split("\n")[-6:]))
    # also show the first copy tail to compare endings
    s1 = defs[0]
    first = src[s1:s2]
    print("--- first copy tail ---")
    print("\n".join(first.split("\n")[-4:]))
