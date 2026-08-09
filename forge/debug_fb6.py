"""Debug: surface exceptions in _parse_fallback_heuristic on port-less claim."""
import sys, json, re, traceback
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
import ast
src = open("/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py").read()
try:
    ast.parse(src)
    print("compile OK")
except SyntaxError as e:
    print("SYNTAX ERROR:", e)
    sys.exit(1)

from arena import conclusion_adapters as ca

class FakeEv:
    def __init__(self, raw, ev_id="ev1"):
        self.raw_content = raw
        self.evidence_id = ev_id
        self.evidence_type = "model_inference"

class FakeGraph:
    def __init__(self, evs):
        self._evs = evs
    def get_all_evidence(self):
        return self._evs

raw = json.dumps({
    "claim": "Target 10.0.238.25 is a Linux host with MySQL service; target 10.0.238.10 runs DNS and SSH services.",
    "category": "service_identification",
    "confidence": 0.9,
    "structured_conclusion": {},
})
g = FakeGraph([FakeEv(raw)])

# Replicate parser body WITHOUT the except-swallow
claim_lower = "target 10.0.238.25 is a linux host with mysql service; target 10.0.238.10 runs dns and ssh services."
p1 = re.findall(r'runs?\s+(?:an?\s+)?([\w-]+)\s+service', claim_lower)
p2 = re.findall(r'with\s+([\w-]+)\s+service', claim_lower)
p3 = re.findall(r'runs\s+([\w-]+)\s+and\s+([\w-]+)\s+services', claim_lower)
print("p1:", p1)
print("p2:", p2)
print("p3:", p3)

claims = ca._parse_fallback_heuristic(g, ("ev1",))
print("parser claims:", len(claims))
for c in claims:
    print("  ", c.predicate.value, getattr(c, "object_value", None))

# Inspect the actual source of FALLBACK 6 to confirm edit integrity
src_lines = src.splitlines()
for i, line in enumerate(src_lines):
    if "FALLBACK 6" in line:
        print("\nFALLBACK 6 source region:")
        for j in range(i, min(i + 30, len(src_lines))):
            print(f"{j+1}: {src_lines[j]}")
        break
