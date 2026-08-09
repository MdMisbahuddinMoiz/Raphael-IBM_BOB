"""Verify: compile, import, adapter mapping, and fallback heuristic body."""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")

import arena.conclusion_adapters as ca

# 1. Factory mapping check
adapter = ca.get_adapter("PROMPTED_AGENT")
print("PROMPTED_AGENT adapter class:", type(adapter).__name__)

# 2. Fallback heuristic effective signature
import inspect
sig = inspect.signature(ca._parse_fallback_heuristic)
print("fallback signature:", sig)

# 3. Fallback body — what evidence does it read?
src = inspect.getsource(ca._parse_fallback_heuristic)
print("fallback lines:", len(src.splitlines()))
for kw in ["model_inference", "raw_content", "structured_conclusion", "claim", "CVE", "version", "patched", "vulnerable", "port", "has_service"]:
    print(f"  contains {kw!r}:", kw in src)

# 4. Structured parser presence
sig2 = inspect.signature(ca._parse_structured_conclusion)
print("structured parser signature:", sig2)

# 5. Quick unit test: fallback extraction from a synthetic evidence-like dict
import json
import types

class FakeEv:
    def __init__(self, raw, ev_id="ev1"):
        self.raw_content = raw
        self.evidence_id = ev_id
        self.evidence_type = "model_inference"
        self.trust_level = None

class FakeGraph:
    def __init__(self, evs):
        self._evs = evs
    def get_all_evidence(self):
        return self._evs

raw = json.dumps({
    "claim": "Host 10.0.0.5 runs Apache 2.4.49, vulnerable to CVE-2021-41773, patched in 2.4.50, port 80 open",
    "category": "vulnerability_indication",
    "confidence": 0.9,
    "structured_conclusion": {},
})
g = FakeGraph([FakeEv(raw)])
claims = ca._parse_fallback_heuristic(g, ("ev1",))
print("\nfallback claims from synthetic evidence:", len(claims))
from arena.conclusion import ConclusionPredicate
for c in claims:
    print("  predicate:", c.predicate, "| subject:", c.subject_id, "| obj:", str(c.object_value)[:80])

# 6. D13 real-phrasing unit test: model output observed in re-audit
raw_real = json.dumps({
    "claim": "Host 10.0.248.10 runs an Apache service on port 80.",
    "category": "service_identification",
    "confidence": 0.95,
    "structured_conclusion": {},
})
g_real = FakeGraph([FakeEv(raw_real, ev_id="ev_real")])
claims_real = ca._parse_fallback_heuristic(g_real, ("ev_real",))
print("\nD13 real-phrasing claims:", len(claims_real))
for c in claims_real:
    print("  predicate:", c.predicate, "| subject:", c.subject_id, "| obj:", str(c.object_value)[:80])

assert len(claims_real) >= 1, "FAIL: real phrasing must yield has_service"
has_svc = [c for c in claims_real
           if getattr(c, "predicate", None) == ConclusionPredicate.HAS_SERVICE]
assert has_svc, "FAIL: no HAS_SERVICE claim"
obj = has_svc[0].object_value
assert obj.get("port") == 80 and obj.get("type") == "http", f"FAIL: got {obj}"
print("\nD13 UNIT TEST PASS: has_service {port: 80, type: http} from real phrasing")

# 7. D13 extension: port-less phrasings -> SERVICE_TYPE
raw_pl = json.dumps({
    "claim": "Target 10.0.238.25 is a Linux host with MySQL service; target 10.0.238.10 runs DNS and SSH services.",
    "category": "service_identification",
    "confidence": 0.9,
    "structured_conclusion": {},
})
g_pl = FakeGraph([FakeEv(raw_pl, ev_id="ev_pl")])
claims_pl = ca._parse_fallback_heuristic(g_pl, ("ev_pl",))
print("\nD13 port-less phrasing claims:", len(claims_pl))
svc_types = [c.object_value for c in claims_pl
             if getattr(c, "predicate", None) == ConclusionPredicate.SERVICE_TYPE]
print("  service_type values:", svc_types)
assert 'mysql' in svc_types, "FAIL: expected service_type mysql"
assert 'dns' in svc_types, "FAIL: expected service_type dns"
assert 'ssh' in svc_types, "FAIL: expected service_type ssh"
print("\nD13 EXTENSION UNIT TEST PASS: port-less phrasings -> service_type claims")


