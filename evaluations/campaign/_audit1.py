"""D1 audit step: map adapter for PROMPTED_AGENT and claim extraction paths."""
import re

path = "src/arena/conclusion_adapters.py"
src = open(path).read()

lines = src.splitlines()
for i, ln in enumerate(lines, 1):
    if re.match(r"^(class |def |    def |    class )", ln):
        print(f"{i:5d}: {ln}")