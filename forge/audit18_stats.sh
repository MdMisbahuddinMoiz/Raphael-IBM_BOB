#!/bin/bash
# FORGE Audit Tool 18 — final repo statistics for architecture doc
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== src/ python files & LOC ==="
find src -name '*.py' -not -path '*__pycache__*' | wc -l
find src -name '*.py' -not -path '*__pycache__*' -exec cat {} + | wc -l
echo "=== by top-level package ==="
for d in src/*/; do
  n=$(find "$d" -name '*.py' -not -path '*__pycache__*' | wc -l)
  loc=$(find "$d" -name '*.py' -not -path '*__pycache__*' -exec cat {} + | wc -l)
  echo "$d: files=$n loc=$loc"
done
echo "=== tests total LOC ==="
find tests src/arena/tests -name '*.py' -not -path '*__pycache__*' -exec cat {} + | wc -l
echo "=== git tracked vs untracked py in tests ==="
git ls-files 'tests/*.py' | wc -l
ls tests/*.py | wc -l