#!/usr/bin/env bash
set -x
cd /home/yaser/raphael-2.0-rbsv2r || { echo "cd fail"; exit 1; }
source /etc/profile 2>/dev/null
export PATH="/home/yaser/raphael-2.0/.venv/bin:$PATH"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
/home/yaser/raphael-2.0/.venv/bin/python scripts/run_rbs_v4_validation.py >> /home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/REPAIR_VAL_02_RERUN.log 2>&1
echo "EXIT=$? END $(date -u +%Y-%m-%dT%H:%M:%SZ)"