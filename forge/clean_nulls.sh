#!/bin/bash
cd /home/yaser/raphael-2.0-rbsv2r
cp src/arena/conclusion_adapters.py src/arena/conclusion_adapters.py.bak
tr -d '\000' < src/arena/conclusion_adapters.py.bak > src/arena/conclusion_adapters.py
PYTHONPATH=/home/yaser/raphael-2.0-rbsv2r/src:/home/yaser/raphael-2.0-rbsv2r .venv/bin/python -c "import arena.conclusion_adapters; print('Import OK')"