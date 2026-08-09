#!/usr/bin/env python3
"""
Debug the _parse_structured_conclusion function.
"""
import sys
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

from arena.conclusion_adapters import _parse_structured_conclusion
import json
import re

# Test the parsing logic directly
raw_content = '{"claim": "Found CVE-2021-41773 in Apache", "category": "vulnerability_indication", "confidence": 0.9, "structured_conclusion": {"cve": "CVE-2021-41773", "version": "Apache/2.4.50", "patched_fix": "patched in 2.4.51", "vulnerable_host": "10.0.52.10", "has_service": {"port": 80, "type": "http"}}}'

print("Testing JSON parsing...")
try:
    json_data = json.loads(raw_content)
    print(f"JSON parsed successfully: {json_data}")
    structured = json_data.get("structured_conclusion")
    print(f"Structured: {structured}")
    if structured:
        print(f"  cve: {structured.get('cve')}")
        print(f"  version: {structured.get('version')}")
        print(f"  patched_fix: {structured.get('patched_fix')}")
        print(f"  vulnerable_host: {structured.get('vulnerable_host')}")
        print(f"  has_service: {structured.get('has_service')}")
except Exception as e:
    print(f"JSON parsing failed: {e}")

# Test the mock evidence
class MockEv:
    def __init__(self, evidence_id, raw_content, evidence_type="model_inference"):
        self.evidence_id = evidence_id
        self.raw_content = raw_content
        self.evidence_type = evidence_type

class MockGraph:
    def __init__(self, evidences):
        self._evidences = evidences
    def get_all_evidence(self):
        return self._evidences

from arena.conclusion_adapters import _parse_structured_conclusion

raw_content = '{"claim": "Found CVE-2021-41773 in Apache", "category": "vulnerability_indication", "confidence": 0.9, "structured_conclusion": {"cve": "CVE-2021-41773", "version": "Apache/2.4.50", "patched_fix": "patched in 2.4.51", "vulnerable_host": "10.0.52.10", "has_service": {"port": 80, "type": "http"}}}'
ev = type('MockEv', (), {
    'evidence_id': 'ev_test_001',
    'raw_content': '{"claim": "Found CVE-2021-41773 in Apache", "category": "vulnerability_indication", "confidence": 0.9, "structured_conclusion": {"cve": "CVE-2021-41773", "version": "Apache/2.4.50", "patched_fix": "patched in 2.4.51", "vulnerable_host": "10.0.52.10", "has_service": {"port": 80, "type": "http"}}',
    'evidence_type': 'model_inference'
})()

graph = type('MockGraph', (), {'get_all_evidence': lambda self: [ev]})()

print("Calling _parse_structured_conclusion...")
try:
    from arena.conclusion_adapters import _parse_structured_conclusion
    claims = _parse_structured_conclusion(type('MockGraph', (), {'get_all_evidence': lambda self: [type('MockEv', (), {'evidence_id': 'ev_test_001', 'raw_content': '{"claim": "Found CVE-2021-41773 in Apache", "category": "vulnerability_indication", "confidence": 0.9, "structured_conclusion": {"cve": "CVE-2021-41773", "version": "Apache/2.4.50", "patched_fix": "patched in 2.4.51", "vulnerable_host": "10.0.52.10", "has_service": {"port": 80, "type": "http"}}}', 'evidence_type': 'model_inference'})()}, evidence_ids=())
    print(f"Claims extracted: {len(claims)}")
    for c in claims:
        print(f"  {c.predicate}: {c.object_value}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()