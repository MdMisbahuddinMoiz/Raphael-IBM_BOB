#!/bin/bash
# FORGE Audit Tool — Binary Coverage Manifest (G-03)
# Enumerates every external binary referenced in src/ vs present in kali-tools container
set -u
cd /home/yaser/raphael-2.0-rbsv2r || exit 1

echo "=== Scanning src/ for binary references ==="
# Extract unique binary names from subprocess/tool calls
grep -rhoE "\b(nmap|sqlmap|gobuster|nikto|ffuf|hydra|john|hashcat|netexec|crackmapexec|nxc|msfconsole|metasploit|searchsploit|wpscan|dirb|whatweb|netcat|nc |socat|tcpdump|sslscan|testssl|enum4linux|smbmap|impacket|responder|masscan|amass|dnsx|subfinder|wget|curl|python3 |sh -c|/bin/sh|cmd\.exe|powershell)\b" src/ --include="*.py" | \
  grep -v "^\s*#" | \
  sed -E 's/.*\b(nmap|sqlmap|gobuster|nikto|ffuf|hydra|john|hashcat|netexec|crackmapexec|nxc|msfconsole|metasploit|searchsploit|wpscan|dirb|whatweb|netcat|socat|tcpdump|sslscan|testssl|enum4linux|smbmap|impacket|responder|masscan|amass|dnsx|subfinder|wget|curl|python3|sh|cmd\.exe|powershell)\b.*/\1/' | \
  sort | uniq -c | sort -rn > /tmp/binary_refs.txt

echo "=== Checking kali-tools container ==="
for b in $(awk '{print $2}' /tmp/binary_refs.txt); do
  if docker exec kali-tools sh -c "command -v $b >/dev/null 2>&1"; then
    status="PRESENT"
  else
    status="MISSING"
  fi
  count=$(grep -w "$b" /tmp/binary_refs.txt | awk '{print $1}')
  echo "$status: $b (refs: $count)"
done | tee /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.txt

echo "=== JSON Output ==="
cat > /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json << 'JSONEOF'
{
  "generated": "2026-08-08T16:30:00Z",
  "kali_tools_image": "kali-tools:latest",
  "binaries": [
JSONEOF

while read -r line; do
  count=$(echo "$line" | awk '{print $1}')
  bin=$(echo "$line" | awk '{print $2}')
  status=$(docker exec kali-tools sh -c "command -v $bin >/dev/null 2>&1" && echo "PRESENT" || echo "MISSING")
  caller_count=$(grep -r "\b$bin\b" src/ --include="*.py" -l | wc -l)
  echo "    {\"binary\": \"$bin\", \"status\": \"$status\", \"src_refs\": $count, \"caller_files\": $caller_count}," >> /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json
done < /tmp/binary_refs.txt

# Remove trailing comma and close
sed -i '$ s/,$//' /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json
echo "  ]" >> /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json
echo "}" >> /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json

cat /home/yaser/raphael-2.0-rbsv2r/forge/BINARY_COVERAGE_MANIFEST_20260808.json