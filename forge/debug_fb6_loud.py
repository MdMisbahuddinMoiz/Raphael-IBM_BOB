"""Bisect: run parser body with exception surfaced."""
import sys, json, re, traceback
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

import arena.conclusion_adapters as ca
import inspect

# Get the parser source, swap the silent except for a loud one, exec it
src = inspect.getsource(ca._parse_fallback_heuristic)
src = src.replace("except Exception:\n        pass", "except Exception:\n        traceback.print_exc()")
ns = {"traceback": traceback, "json": json, "re": re}
# make_claim and ConclusionPredicate come from module globals; exec in a namespace with them
ns["make_claim"] = ca.make_claim
ns["ConclusionPredicate"] = ca.ConclusionPredicate
ns["DerivationType"] = ca.DerivationType
ns["ConclusionClaim"] = ca.ConclusionClaim
exec(src, ns)
fn = ns["_parse_fallback_heuristic"]

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
claims = fn(g, ("ev1",))
print("claims:", len(claims))
