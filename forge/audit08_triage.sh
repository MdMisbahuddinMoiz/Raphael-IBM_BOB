#!/bin/bash
# FORGE Audit Tool 08 — Full failure triage with exception types
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
.venv/bin/python -m pytest -q --tb=no 2>&1 | grep -E '^(FAILED|ERROR)' > forge/pytest_failures.txt
echo "=== Failure signature extraction ==="
.venv/bin/python - <<'EOF' 2>/dev/null || .venv/bin/python forge/failtriage.py
EOF
# per-test error type via -rf
.venv/bin/python -m pytest -q --tb=line 2>&1 | grep -E "^tests" | sed 's/ - / :: /' | awk -F' :: ' '{print $NF}' | sort | uniq -c | sort -rn | head -25