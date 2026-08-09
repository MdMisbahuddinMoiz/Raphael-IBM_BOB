#!/bin/bash
# FORGE Audit Tool 12 — alternate tool names / count
set -u
docker exec kali-tools bash -lc 'for t in nxc crackmapexec searchsploit exploitdb wpscan sslscan subfinder amass dnsx netexec; do if command -v $t >/dev/null 2>&1; then echo PRESENT: $t; else echo MISSING: $t; fi; done
echo "---BINCOUNT---"
ls /usr/bin /usr/local/bin 2>/dev/null | wc -l
echo "---NUCLEI VERSION---"
nuclei -version 2>&1 | head -1
echo "---NMAP VERSION---"
nmap --version 2>&1 | head -1'