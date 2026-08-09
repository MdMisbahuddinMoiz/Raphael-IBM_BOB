#!/usr/bin/env python3
"""
Test the _parse_structured_conclusion function directly with mock data.
"""
import sys
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

from arena.conclusion_adapters import _parse_structured_conclusion
from types import SimpleNamespace

# Mock evidence with structured_conclusion
class MockEvidence:
    def __init__(self, evidence_id, raw_content, evidence_type="model_inference"):
        self.evidence_id = evidence_id
        self.raw_content = raw_content
        self.evidence_type = evidence_type

class MockEvidenceGraph:
    def __init__(self, evidences):
        self._evidences = evidences
    
    def get_all_evidence(self):
        return self._evidences

# Test 1: Valid structured_conclusion with all fields
    print("Test 1: Valid structured_conclusion with all fields")
    raw_content = '{"claim": "Found CVE-2021-41773 in Apache", "category": "vulnerability_indication", "confidence": 0.9, "structured_conclusion": {"cve": "CVE-2021-41773", "version": "Apache/2.4.50", "patched_fix": "patched in 2.4.51", "vulnerable_host": "10.0.52.10", "has_service": {"port": 80, "type": "http"}}}'
    ev = type('MockEv', (), {
        'evidence_id': 'ev_test_001',
        'raw_content': raw_content,
        'evidence_type': 'model_inference'
    })()
    
    graph = type('MockGraph', (), {
        'get_all_evidence': lambda self: [ev]
    })()
    
    claims = _parse_structured_conclusion(graph, ())
    print(f"Claims extracted: {len(claims)}")
    for c in claims:
        print(f"  {c.predicate}: {c.object_value}")

    # Test 2: Empty structured_conclusion
    print("\nTest 2: Empty structured_conclusion")
    ev2 = type('MockEv', (), {
        'evidence_id': 'ev_test_002',
        'raw_content': '{"claim": "Port 80 open", "category": "service_identification", "confidence": 0.8, "structured_conclusion": {}}',
        'evidence_type': 'model_inference'
    })()
    
    graph2 = type('MockGraph', (), {'get_all_evidence': lambda self: [ev2]})()
    claims2 = _parse_structured_conclusion(graph2, ())
    print(f"Claims extracted: {len(claims2)}")

    # Test 3: No structured_conclusion field
    print("\nTest 3: No structured_conclusion field")
    ev3 = type('MockEv', (), {
        'evidence_id': 'ev_test_003',
        'raw_content': '{"claim": "Port 22 open", "category": "service_identification", "confidence": 0.9}',
        'evidence_type': 'model_inference'
    })()
    
    graph3 = type('MockGraph', (), {'get_all_evidence': lambda self: [ev3]})()
    claims3 = _parse_structured_conclusion(graph3, ())
    print(f"Claims extracted: {len(claims3)}")

    print("\nAll tests completed!")