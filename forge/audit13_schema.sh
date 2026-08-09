#!/bin/bash
# FORGE Audit Tool 13 — inspect jsonl schema
set -u
cd /home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/dev_runs/raw || exit 1
D=abl_PROMPTED_AGENT_arena-d6-013_s1357447574_dev
echo "=== episodes.jsonl line 1 (full) ==="
head -1 "$D/episodes.jsonl"
echo ""
echo "=== episodes.jsonl all ep ids ==="
grep -o '"episode_id"[^,]*' "$D/episodes.jsonl" | head -12
echo "=== events.jsonl line 1 ==="
head -1 "$D/events.jsonl"
echo ""
echo "=== episode keys ==="
head -1 "$D/episodes.jsonl" | python3 -c "import json,sys; print(list(json.load(sys.stdin).keys()))"
echo "=== event keys ==="
head -1 "$D/events.jsonl" | python3 -c "import json,sys; print(list(json.load(sys.stdin).keys()))"