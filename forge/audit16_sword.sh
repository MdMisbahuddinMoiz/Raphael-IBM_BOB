#!/bin/bash
# FORGE Audit Tool 16 — container-side import reality
set -u
docker exec raphael_redteam-sword-1 python3 -c "import config; print('sword config OK:', config.__file__)" 2>&1 | tail -2
docker exec raphael_redteam-sword-1 python3 -c "import orchestrator; print('sword orchestrator OK')" 2>&1 | tail -2
docker exec raphael_redteam-sword-1 python3 -c "import arena; print('sword arena OK:', arena.__file__)" 2>&1 | tail -2