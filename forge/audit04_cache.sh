#!/bin/bash
# FORGE Audit Tool 04 — Cache timeline + test inventory
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] pytest cache timestamps ==="
ls -la .pytest_cache/v/cache/
echo "=== [2] lastfailed sample (first 15) ==="
head -15 .pytest_cache/v/cache/lastfailed
echo "=== [3] test function inventory (count def test_) ==="
grep -rc "def test_" tests/*.py src/arena/tests/*.py 2>/dev/null | awk -F: '{s+=$2; print} END {print "TOTAL:", s}'
echo "=== [4] pyproject deps ==="
grep -A 40 "\[project.dependencies\]" pyproject.toml | head -45
echo "=== [5] pytest.ini / conftest ==="
ls pytest.ini setup.cfg tox.ini conftest.py 2>&1
echo "=== [6] modified file diff ==="
git diff src/arena/ablation_runner.py 2>/dev/null | head -40
