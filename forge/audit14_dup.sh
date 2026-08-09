#!/bin/bash
# FORGE Audit Tool 14 — duplicate comparison + scripted arm listing
set -u
.venv/bin/python forge/verify_dup_compare.py 2>&1 | head -12
echo "---SCRIPTED ARM (newest)---"
D2=$(ls -td /home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/dev_runs/raw/abl_SCRIPTED_* 2>/dev/null | head -1)
echo "$D2"
ls "$D2" 2>/dev/null