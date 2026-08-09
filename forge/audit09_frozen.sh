#!/bin/bash
# FORGE Audit Tool 09 — Frozen subset vs working tree
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] tracked test files ==="
TRACKED="tests/e1_interactive_shell_test.py tests/e2_shell_candidate_generation_test.py tests/test_cli_smoke.py tests/test_d5_preflight.py tests/test_d5_seven_gate_proof.py tests/test_rbs_v2_repairs.py tests/test_stage1_invariants.py"
echo "=== [2] run TRACKED subset only ==="
.venv/bin/python -m pytest $TRACKED -q --tb=no 2>&1 | tail -3
echo "=== [3] test_cli_smoke git status ==="
git diff --stat tests/test_cli_smoke.py
git log --oneline -2 -- tests/test_cli_smoke.py
echo "=== [4] arena tests subset ==="
.venv/bin/python -m pytest src/arena/tests/ -q --tb=no 2>&1 | tail -3
echo "=== [5] LLM endpoint reachability ==="
grep -E 'OPENAI|MODEL_ID' .env | sed 's/=.*/=<redacted>/'
curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:11434/v1/models 2>&1
echo ""
curl -s -m 5 http://localhost:3201/health 2>&1 | head -2