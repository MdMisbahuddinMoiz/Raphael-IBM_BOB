#!/usr/bin/env python3
"""Verify GITHUB_SCOPE_CONFIG.json alignment to ScopeParser contract (minimal repair check)."""
import json
import sys

sys.path.insert(0, "src")
from orchestrator.brain.scope_parser import create_scope_parser_from_file  # noqa: E402

# 1. Runtime loader contract (top-level keys -> fail-closed policy)
sp = create_scope_parser_from_file("configs/GITHUB_SCOPE_CONFIG.json")
tests = [
    ("api.github.com", True),
    ("raw.githubusercontent.com", True),
    ("registry.npmjs.org", True),
    ("github.com", True),
    ("blog.github.com", False),
    ("community.github.com", False),
    ("resources.github.com", False),
    ("smtp.github.com", False),
    ("evil.com", False),
    ("localhost", False),
    ("10.0.0.5", False),
]
ok = True
for target, expected in tests:
    allowed, reason = sp.is_target_allowed(target)
    status = "PASS" if allowed == expected else "FAIL"
    if allowed != expected:
        ok = False
    print(f"  [{status}] {target}: allowed={allowed} expected={expected} ({reason})")

# 2. Audit consumer (wrapper path still intact)
cfg = json.load(open("configs/GITHUB_SCOPE_CONFIG.json"))
assert "scope" in cfg and "in_scope" in cfg and "out_of_scope" in cfg, "key structure broken"
assert len(cfg["in_scope"]) == 16 and len(cfg["scope"]["in_scope"]) == 16, "in_scope count mismatch"
assert len(cfg["out_of_scope"]) == 5 and len(cfg["scope"]["out_of_scope"]) == 5, "out_of_scope count mismatch"
assert [i["asset_identifier"] for i in cfg["in_scope"]] == [i["asset_identifier"] for i in cfg["scope"]["in_scope"]], "wrapper/top-level divergence"
print("  [PASS] wrapper + top-level keys both present, counts match (16 in / 5 out), content identical")

print("ALL SCOPE CHECKS:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
