#!/bin/bash
cd /home/yaser/raphael-2.0-rbsv2r
/home/yaser/raphael-2.0/.venv/bin/python -u scripts/run_rbs_v4_pilot.py 2>&1 | tee evaluations/campaign/rbs_v4_pilot.log
echo "Pilot exited with code $?"