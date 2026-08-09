"""Prove the parser-alignment gap: real fallback vs real model phrasing.

Calls the REAL _parse_fallback_heuristic (read-only) on a model_inference
evidence whose content is the ACTUAL model output observed in the re-audit
("Host 10.0.248.10 runs an Apache service on port 80."), then demonstrates
the candidate extended pattern would extract has_service.
"""
import sys, json
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

from arena.conclusion_adapters import _parse_fallback_heuristic
from orchestrator.brain.evidence import Evidence, TrustLevel

# Rebuild an EvidenceGraph with a model_inference evidence exactly as produced
from orchestrator.brain.evidence import EvidenceGraph
eg = EvidenceGraph()
ev = Evidence.create(
    raw_content=json.dumps({
        "claim": "Host 10.0.248.10 runs an Apache service on port 80.",
        "category": "service_identification",
        "confidence": 0.95,
        "structured_conclusion": {},
    }),
    trust_level=TrustLevel.MODEL_INFERENCE,
    source_detail="LLM semantic inference (category: service_identification)",
    target="service_identification",
    evidence_type="model_inference",
    description="LLM semantic inference",
    structured_content={"claim": "Host 10.0.248.10 runs an Apache service on port 80."},
    collected_by="llm_service",
)
eg.add_evidence(ev)

claims = _parse_fallback_heuristic(eg, (ev.evidence_id,))
print(f"REAL fallback on real model phrasing -> {len(claims)} claims")
for c in claims:
    print("  ", c.predicate.value if hasattr(c.predicate, 'value') else c.predicate,
          "|", getattr(c, "object_value", None))

# Proposed minimal extension: pattern for 'runs an <svc> service on port <n>'
import re as _re
claim_text = "Host 10.0.248.10 runs an Apache service on port 80."
m = _re.search(r'runs?\s+an?\s+([\w-]+)\s+service\s+on\s+port\s+(\d+)', claim_text, _re.IGNORECASE)
print(f"\nproposed extended pattern match: {m.groups() if m else None}")
