"""Step 2b: normalize the remaining two param patterns (12-space site 666, 16-space sites)."""
from pathlib import Path

p = Path("src/arena/ablation_runner.py")
t = p.read_text()

# Site at line ~666 uses 16-space indent under 12-space call? Actual: 16 spaces for params.
OLD_16 = "                    timeout_seconds=15,\n                    temperature=0.0,\n                    max_tokens=512,"
NEW_16 = "                    timeout_seconds=180,\n                    temperature=0.0,\n                    max_tokens=16384,"
n16 = t.count(OLD_16)
print("16-space pattern:", n16)

OLD_12 = "                timeout_seconds=15,\n                temperature=0.0,\n                max_tokens=512,"
NEW_12 = "                timeout_seconds=180,\n                temperature=0.0,\n                max_tokens=16384,"
n12 = t.count(OLD_12)
print("12-space pattern:", n12)

assert n16 + n12 == 3, f"total param sites {n16}+{n12} != 3"
t = t.replace(OLD_16, NEW_16).replace(OLD_12, NEW_12)
p.write_text(t)
print("OK: all 3 sites have timeout 180 / max_tokens 16384")
print("remaining 'timeout_seconds=15':", t.count("timeout_seconds=15"))
print("remaining 'deepseek':", t.count("deepseek"))
