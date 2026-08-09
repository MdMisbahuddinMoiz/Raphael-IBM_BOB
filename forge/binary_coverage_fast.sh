#!/bin/bash
# FORGE — Binary Coverage Manifest (fast version)
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1

BINS="nmap sqlmap gobuster nikto ffuf hydra john hashcat netexec crackmapexec nxc msfconsole metasploit searchsploit wpscan dirb whatweb netcat socat tcpdump sslscan testssl enum4linux smbmap impacket responder masscan amass dnsx subfinder curl wget python3"
OUT="/home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json"

echo "{" > "$OUT"
echo '  "generated": "2026-08-08T16:35:00Z",' >> "$OUT"
echo '  "kali_tools_image": "kali-tools:latest",' >> "$OUT"
echo '  "binaries": [' >> "$OUT"

first=1
for b in $BINS; do
  if docker exec kali-tools sh -c "command -v $b >/dev/null 2>&1"; then
    status="PRESENT"
  else
    status="MISSING"
  fi
  count=$(grep -r "\b$b\b" src/ --include="*.py" 2>/dev/null | wc -l)
  callers=$(grep -r "\b$b\b" src/ --include="*.py" -l 2>/dev/null | wc -l)
  if [ $first -eq 1 ]; then first=0; else echo "," >> "$OUT"; fi
  echo "    {\"binary\": \"$b\", \"status\": \"$status\", \"src_refs\": $count, \"caller_files\": $callers}" >> "$OUT"
done

echo "  ]" >> "$OUT"
echo "}" >> "$OUT"
cat "$OUT"