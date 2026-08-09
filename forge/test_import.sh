#!/bin/bash
cd /home/yaser/raphael-2.0-rbsv2r
find . -name '*.pyc' -path '*/conclusion_adapters*' -delete 2>/dev/null
find . -name '__pycache__' -path '*/arena/*' -exec rm -rf {} + 2>/dev/null
PYTHONPATH=/home/yaser/raphael-2.0-rbsv2r/src:/home/yaser/raphael-2.0-rbsv2r .venv/bin/python -c "import arena.conclusion_adapters; print('Import OK')"