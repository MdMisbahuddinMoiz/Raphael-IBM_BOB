#!/bin/bash
for b in nmap sqlmap gobuster nikto ffuf hydra john hashcat netexec crackmapexec nxc searchsploit wpscan sslscan subfinder amass dnsx masscan dirb whatweb curl wget; do
  if command -v "$b" >/dev/null 2>&1; then
    echo "PRESENT: $b"
  else
    echo "MISSING: $b"
  fi
done