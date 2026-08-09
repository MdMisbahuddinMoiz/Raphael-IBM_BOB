#!/bin/bash
# FORGE Audit Tool 06 — install leftover deps + verify
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
uv pip install dnspython pywinrm 2>&1 | tail -6
echo "=== verify ==="
.venv/bin/python -c "import dns, winrm; print('dns+winrm OK')" 2>&1 | tail -2
.venv/bin/python forge/depcheck.py