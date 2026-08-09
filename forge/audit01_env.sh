#!/bin/bash
# FORGE Audit Tool 01b — Environment Recon v2 (no heredocs)
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
PY=/home/yaser/.local/bin/python3.12
echo "=== [1] INTERPRETER ==="
"$PY" --version 2>&1
echo "=== [2] CORE DEPS ==="
"$PY" forge/depcheck.py 2>&1 | tail -3
echo "=== [3] EVALUATIONS TREE ==="
find evaluations -maxdepth 3 -type d 2>/dev/null | head -40
echo "=== [4] BENCHMARKS ==="
find benchmarks -maxdepth 3 2>/dev/null | head -30
echo "=== [5] FAILURES ==="
ls failures/ 2>/dev/null
echo "=== [6] SCRIPTS: smoke_test presence ==="
ls scripts/smoke_test.py 2>&1
echo "=== [7] .env size ==="
ls -la .env && grep -c '=' .env
echo "=== [8] GIT ==="
git status --short 2>/dev/null | head -5
git log --oneline -5 2>/dev/null
echo "=== [9] LLM ENDPOINT CONFIG (redacted) ==="
grep -E 'OPENAI_BASE_URL|MODEL_ID' .env | sed 's/=.*/=<redacted>/'
