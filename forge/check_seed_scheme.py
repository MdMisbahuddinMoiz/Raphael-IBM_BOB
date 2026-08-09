"""Check resolve_seed mapping for all splits + compare runtime prompt vs freeze verbatim."""
import json, hashlib, re, sys
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, str(ROOT / "src"))

print("=== 1. resolve_seed implementation ===")
tb = (ROOT / "src/arena/templates/base.py").read_text()
m = re.search(r"def resolve_seed.*?(?=\ndef |\nclass )", tb, re.S)
print(m.group(0)[:1500] if m else "not found in base.py")
if not m:
    for fn in ["templates/base.py", "templates/__init__.py"]:
        p = ROOT / "src/arena" / fn
        if p.exists():
            t = p.read_text()
            i = t.find("resolve_seed")
            print(f"--- {fn} around resolve_seed ---")
            print(t[max(0,i-200):i+800])

print("\n=== 2. split ranges: what abs seeds do splits give? ===")
from arena.templates import ScenarioSplit
for s in ["dev", "validation", "holdout", "warmup", "train"]:
    try:
        split = getattr(ScenarioSplit, s.upper())
        lo = resolve_seed(0, split)
        hi = resolve_seed(59, split)
        print(f"relative 0..59 -> {s}: {lo}..{hi}")
    except Exception as e:
        print(f"{s}: {e}")
