#!/bin/bash
# FORGE Audit Tool 05 — "121 tests" claim provenance + pyproject structure
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] '121' mentions in docs ==="
grep -rn "121" README.md docs/*.md current-state/ 2>/dev/null | grep -iE "test|pass" | head -10
echo "=== [2] pyproject.toml head ==="
head -60 pyproject.toml
echo "=== [3] zero-dependency markers in tests ==="
head -30 tests/test_budget_contract.py
echo "=== [4] run command hints ==="
grep -rn "pytest" README.md docs/EvaluationProtocol.md 2>/dev/null | head -10
echo "=== [5] nodeids: how many unique test files ==="
grep -o '^  "[^"]*::' .pytest_cache/v/cache/nodeids | sort -u | head -40
echo "=== [6] nodeids count by file ==="
grep -o '^  "[^"]*' .pytest_cache/v/cache/nodeids | sed 's/^ *"//' | sed 's/::.*//' | sort | uniq -c | sort -rn | head -35