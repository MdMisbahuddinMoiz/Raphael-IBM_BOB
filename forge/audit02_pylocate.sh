#!/bin/bash
# FORGE Audit Tool 02 — Locate python3.12 site-packages / alternate venvs
set -u
echo "=== [1] python3.12 sys.path ==="
/home/yaser/.local/bin/python3.12 -c "import sys; [print(p) for p in sys.path]" 2>&1
echo "=== [2] system python3.14 deps ==="
python3 -c "import requests, numpy; print('sys314 HAS requests+numpy')" 2>&1 | tail -1
echo "=== [3] find venvs ==="
find /home/yaser -maxdepth 3 -name "pyvenv.cfg" 2>/dev/null
find /home/yaser -maxdepth 3 -type d -name ".venv" 2>/dev/null
echo "=== [4] find site-packages for 3.12 ==="
find /home/yaser -maxdepth 5 -type d -name "site-packages" 2>/dev/null | head -10
find /opt -maxdepth 4 -type d -name "site-packages" 2>/dev/null | head -5
echo "=== [5] sword container python ==="
docker exec raphael_redteam-sword-1 python3 --version 2>&1
docker exec raphael_redteam-sword-1 python3 -c "import requests; print('sword: requests OK')" 2>&1 | tail -1
echo "=== [6] where was pytest run? cached? ==="
ls /home/yaser/raphael-2.0-rbsv2r/.pytest_cache/v/cache/lastfailed 2>/dev/null
cat /home/yaser/raphael-2.0-rbsv2r/.pytest_cache/v/cache/nodeids 2>/dev/null | head -40
echo "=== [7] pip3.12 list count ==="
/home/yaser/.local/bin/python3.12 -m pip list 2>&1 | wc -l
echo "=== [8] any global 3.12 dist-packages ==="
ls /usr/lib/python3/dist-packages 2>/dev/null | head -5
ls /usr/local/lib/python3.12/dist-packages 2>/dev/null | head -5
