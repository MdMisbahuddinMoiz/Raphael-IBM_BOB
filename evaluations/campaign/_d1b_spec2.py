"""Read RBS-v4 research spec: Q7 wording + any PROMPTED/prompted/prompt-only arms."""
import json, re

spec = json.load(open("benchmarks/RBS-v4/RBS-v4_RESEARCH_SPECIFICATION.json"))
s = json.dumps(spec, indent=1)

for kw in ("PROMPTED", "prompted", "prompt-only", "no scaffold", "raw tool", "Q7", "prompted-agent"):
    hits = [m.start() for m in re.finditer(kw, s)]
    print(f"== [{kw}] {len(hits)} hits ==")
    for i in hits[:3]:
        print("   ..." + s[max(0, i - 180):i + 280].replace("\n", " ") + "...")
        print()
    if not hits:
        print("   (none)")
    print()