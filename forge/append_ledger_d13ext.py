"""Append companion ledger entry: D13 FALLBACK 6 extension + gate result."""
import json

path = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/AMENDMENT_LEDGER.json"
d = json.load(open(path))

entry = {
    "amendment_id": "D13-EXT-2026-08-09",
    "title": "D13 Fix 1 extension (FALLBACK 6 service_type extraction) + final gate result",
    "authorizer": "SENTINEL (Fix 1 authorization covers parser phrasing alignment; extension documented for audit)",
    "applied_at_utc": "2026-08-09T12:10:00Z",
    "reason": "Re-audit v4 showed model phrasing variance: 'runs an HTTP service on Linux', 'host with MySQL service', 'runs HTTP and SSH services on Windows' — service identified without a port, so FALLBACK 5 (has_service, port-required) extracted nothing. FALLBACK 6 emits SERVICE_TYPE (L-028 predicate) from port-less phrasings; accumulates across all three patterns (dedupe), never invents a port. Bug fixed during validation: p3 pattern returns tuples -> flattened before dedupe (was swallowed by parser's except-pass).",
    "files_changed": [
        "src/arena/conclusion_adapters.py: _parse_fallback_heuristic FALLBACK 6 added after FALLBACK 5 (service_type from 'runs? an? <svc> service', 'with <svc> service', 'runs <svc> and <svc> services'; svc map http/https/apache/nginx/tomcat/web->http, ssh, mysql, dns, ftp, smtp, netlogon, samba, postgresql)"
    ],
    "superseded_state": "FALLBACK 5 only (port-required has_service); port-less phrasings yielded 0 fallback claims",
    "amended_state": "FALLBACK 5 + FALLBACK 6 (service_type); port-less phrasings yield typed L-028 predicates with LLM_INTERPRETATION provenance",
    "verification": [
        "forge/verify_l028_fix.py: D13 unit test PASS (has_service {80, http}) + extension test PASS (mysql, dns, ssh from 'with MySQL service; runs DNS and SSH services')",
        "tracked suite: 127/127 PASS",
        "FINAL GATE (10 samples, live -0731, key rotation): fallback-sourced typed predicates 9/10 (>= 8/10), MECHANICAL 0/10 (< 2/10) -> GATE PASSED",
        "known-observable s=1: score 1.0 CORRECT (first CORRECT outcome in PROMPTED_AGENT campaign)",
        "2/10 samples had 1 transient provider 503 (INFRA per FREEZE-02) but still produced fallback predicates",
        "evaluations/campaign/L028_VERIFICATION.json (v4) with gate_verdict recorded"
    ],
    "out_of_scope_untouched": [
        "Fix 3 (syn_scan method='all' version-bearing evidence) — DEFERRED by SENTINEL",
        "cognitive loop, broker, environment, evaluators",
        "AMENDMENT-MODEL-EOL-2026-08-09 entry (unchanged, append-only)"
    ],
}

ids = [e["amendment_id"] for e in d["entries"]]
assert "D13-EXT-2026-08-09" not in ids, "entry already exists"
d["entries"].append(entry)
with open(path, "w") as f:
    json.dump(d, f, indent=2)
print("ledger entries:", len(d["entries"]))
