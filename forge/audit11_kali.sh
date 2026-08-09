#!/bin/bash
# FORGE Audit Tool 11 — kali-tools container reality (Rule 3)
set -u
echo "=== [1] container tool inventory ==="
docker exec kali-tools sh -c 'for t in nmap sqlmap gobuster nikto ffuf hydra whatweb netexec hashcat john searchsploit masscan wpscan dirb sslscan nuclei subfinder; do if command -v $t >/dev/null 2>&1; then echo "PRESENT: $t"; else echo "MISSING: $t"; fi; done' 2>&1
echo "=== [2] impacket availability ==="
docker exec kali-tools sh -c 'python3 -c "import impacket; print(\"impacket OK\")" 2>&1' 2>&1
echo "=== [3] kali-tools service health ==="
curl -s -m 5 http://localhost:3800/health 2>&1 | head -3
echo ""
echo "=== [4] kali server tool route sample ==="
curl -s -m 5 "http://localhost:3800/run?tool=nmap&args=--version" 2>&1 | head -5
echo ""
echo "=== [5] does the local server even exist? (docker ps) ==="
docker ps --format '{{.Names}} {{.Ports}}' | grep -i kali