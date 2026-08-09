"""Remove the DEAD first copy of _parse_fallback_heuristic (line ~721, signature (ev)).

The effective definition (evidence_graph, evidence_ids) is the SECOND one — the
first is shadowed dead code with an incompatible signature. Removing it is pure
hygiene within the authorized L-028 clean patch. Does NOT touch
_defeater_to_claims / _falsification_to_claims.
"""
import re
import sys

PATH = "src/arena/conclusion_adapters.py"

src = open(PATH, encoding="utf-8").read()

# Locate both defs
defs = [m.start() for m in re.finditer(r"^def _parse_fallback_heuristic", src, re.M)]
assert len(defs) == 2, f"expected 2 defs, found {len(defs)}"

first_start = defs[0]
second_start = defs[1]

# End of first def = start of second def (they're adjacent blocks; strip trailing blank lines)
block = src[first_start:second_start]
# Find the boundary: last "return claims" + following blank lines within the block
m = re.search(r"return claims[ \t]*\n(?:[ \t]*\n)*", block)
if not m:
    print("ERROR: could not locate end of first def")
    sys.exit(1)

cut_end = first_start + m.end()

new_src = src[:first_start] + src[cut_end:]

# Verify: exactly one def remains
rem = len(re.findall(r"^def _parse_fallback_heuristic", new_src, re.M))
assert rem == 1, f"after cut, defs = {rem}"

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_src)

print(f"removed {cut_end - first_start} chars (dead first copy)")
print(f"new size: {len(new_src)} (was {len(src)})")
print("remaining defs:", rem)
