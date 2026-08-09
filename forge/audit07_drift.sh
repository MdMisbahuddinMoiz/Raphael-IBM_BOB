#!/bin/bash
# FORGE Audit Tool 07 — Drift analysis: tests vs src vs git history
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] git status full ==="
git status --short | head -30
echo "=== [2] is ablation_runner tracked? last commit touching it ==="
git log --oneline -5 -- src/arena/ablation_runner.py 2>/dev/null
echo "=== [3] is test_budget_contract tracked? ==="
git log --oneline -3 -- tests/test_budget_contract.py 2>/dev/null
echo "=== [4] RunMetrics definition location ==="
grep -rn "iterations_used\|class RunMetrics" src/arena/metrics.py 2>/dev/null | head -10
echo "=== [5] file mtimes (tests vs src) ==="
ls -la --time-style=full-iso tests/test_budget_contract.py src/arena/metrics.py src/arena/ablation_runner.py src/arena/d6_manifest.py 2>/dev/null
echo "=== [6] untracked test files ==="
git ls-files tests/ | wc -l
ls tests/*.py | wc -l
echo "=== [7] which tests are tracked ==="
for f in tests/*.py; do git ls-files --error-unmatch "$f" >/dev/null 2>&1 && echo "TRACKED $f" || echo "UNTRACKED $f"; done
echo "=== [8] RunMetrics fields available ==="
grep -n "    [a-z_]*:" src/arena/metrics.py 2>/dev/null | head -40