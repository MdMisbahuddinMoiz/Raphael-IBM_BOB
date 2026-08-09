#!/bin/bash
# FORGE Audit Tool 17 — env validation + target reachability
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] validate_env.py (expects TOR/API/NEO4J keys) ==="
.venv/bin/python scripts/validate_env.py 2>&1 | tail -12
echo "=== [2] DVWA reachability ==="
curl -s -m 5 -o /dev/null -w "dvwa HTTP %{http_code}\n" http://localhost:4280 2>&1 || curl -s -m 5 -o /dev/null -w "dvwa HTTP %{http_code}\n" http://dvwa:80 2>&1
docker exec dvwa sh -c 'echo dvwa-shell-ok' 2>&1 | head -1
echo "=== [3] .env keys present ==="
grep -oE '^[A-Z_]+' .env | sort
echo "=== [4] nvidia keys usable? (count, no value) ==="
grep -cE '^NVIDIA_API_KEY_[AB]=.{40,}' .env