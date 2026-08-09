#!/bin/bash
# FORGE Audit Tool 10 — Subprocess reality scan (Rule 3)
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1
echo "=== [1] subprocess invocations in src (files + binary names) ==="
grep -rn "subprocess\.\(run\|Popen\|call\)\|os\.system\|check_output\|check_call" src/ --include="*.py" -l | head -40
echo ""
echo "=== [2] external binary names referenced ==="
grep -rhoE "(nmap|sqlmap|gobuster|nikto|ffuf|hydra|john|hashcat|netexec|crackmapexec|metasploit|msfconsole|searchsploit|wpscan|dirb|whatweb|netcat|nc |socat|tcpdump|sslscan|testssl|enum4linux|smbmap|impacket|responder|masscan|hydra|curl|wget|python3 |sh -c|/bin/sh|cmd\.exe|powershell)" src/ --include="*.py" | sort | uniq -c | sort -rn | head -30
echo ""
echo "=== [3] kali_tools_client subprocess patterns ==="
grep -n "subprocess\|docker exec\|kali-tools\|timeout" src/orchestrator/kali_tools_client.py | head -30