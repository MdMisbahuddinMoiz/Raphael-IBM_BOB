#!/bin/bash
# FORGE Audit Tool 03 — Test suite provenance: which interpreter ran 121 tests?
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] src/arena/tests exists? ==="
ls src/arena/tests/ 2>&1 | head -10
echo "=== [2] uv available? ==="
which uv 2>&1; uv --version 2>&1 | head -1
echo "=== [3] uv.lock / pyproject ==="
ls uv.lock pyproject.toml 2>&1
echo "=== [4] sibling venv deps (raphael-2.0/.venv) ==="
/home/yaser/raphael-2.0/.venv/bin/python --version 2>&1
/home/yaser/raphael-2.0/.venv/bin/python -c "import requests, numpy, fastapi, pytest; print('sibling venv: core deps OK')" 2>&1 | tail -1
echo "=== [5] nodeids count from pytest cache ==="
wc -l .pytest_cache/v/cache/nodeids 2>/dev/null
echo "=== [6] lastfailed count ==="
wc -l .pytest_cache/v/cache/lastfailed 2>/dev/null
echo "=== [7] git diff of ablation_runner (uncommitted change) ==="
git diff --stat 2>/dev/null
echo "=== [8] pytest cache step ==="
cat .pytest_cache/v/cache/step 2>/dev/null
echo "=== [9] recent test reports in repo ==="
find . -maxdepth 3 -name "*.xml" -o -maxdepth 3 -name "junit*" 2>/dev/null | grep -v node_modules | head -10
echo "=== [10] tests dir count ==="
ls tests/*.py | wc -l
