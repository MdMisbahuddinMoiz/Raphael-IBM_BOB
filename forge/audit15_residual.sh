#!/bin/bash
# FORGE Audit Tool 15 — residual import failures: structural vs real
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] case_store exists? ==="
ls src/recon-pipeline/case_store.py 2>&1
echo "=== [2] import style in case_api ==="
grep -n "import" src/recon-pipeline/case_api.py | head -6
echo "=== [3] d6c_holdout_runner import in arena d16 ==="
grep -n "import" src/arena/d16_holdout_runner.py | head -6
echo "=== [4] is d6c_holdout_runner in scripts? ==="
ls scripts/d6c_holdout_runner.py 2>&1
echo "=== [5] dash-package dirs (cannot be dotted-imported) ==="
ls -d src/*-* 2>/dev/null
echo "=== [6] how are dash services imported in pyproject? ==="
grep -A 6 'packages.find' pyproject.toml