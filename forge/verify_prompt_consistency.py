"""Verify: (1) where the PROMPTED_AGENT prompt lives, (2) what D13 changed vs backups, (3) seed scheme for SENTINEL's 1072-1101."""
import json, hashlib, re, sys
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
SRC = ROOT / "src/arena"

print("=== 1. WHERE DOES THE PROMPTED_AGENT PROMPT LIVE? ===")
for fn in ["ablation_runner.py", "semantic_inference.py", "llm_service.py"]:
    txt = (SRC / fn).read_text()
    for pat in ["PROMPTED_AGENT_SYSTEM_PROMPT", "ENVELOPE_SYSTEM_PROMPT", "_build_prompted_context", "_run_llm_only", "frozen instruction", "instruction block"]:
        hits = [i for i, l in enumerate(txt.splitlines(), 1) if pat in l]
        if hits:
            print(f"{fn}: {pat} @ lines {hits[:8]}")

print("\n=== 2. D13 DIFF vs BACKUP (which files changed & what) ===")
for fn in ["ablation_runner.py", "semantic_inference.py", "conclusion_adapters.py"]:
    cur = SRC / fn
    bak = SRC / f"{fn}.forge_backup.d13"
    if bak.exists():
        a = bak.read_text().splitlines()
        b = cur.read_text().splitlines()
        import difflib
        diff = list(difflib.unified_diff(a, b, lineterm="", n=1))
        adds = [d for d in diff if d.startswith("+") and not d.startswith("+++")]
        dels = [d for d in diff if d.startswith("-") and not d.startswith("---")]
        print(f"{fn}: +{len(adds)} -{len(dels)} lines")
        # show prompt-related changed lines
        for d in adds:
            if any(k in d for k in ["rule", "Rule", "PROMPTED", "service_identification", "has_service", "escape", "{}"]):
                print("   +", d[:120])
    else:
        print(f"{fn}: NO .forge_backup.d13 backup")

print("\n=== 3. PROMPTED PROMPT in ablation_runner (the freeze file's implementation_source) ===")
ar = (SRC / "ablation_runner.py").read_text()
lines = ar.splitlines()
# print lines 2690-2760 to see the prompted context builder
for i in range(2685, min(2775, len(lines))):
    print(f"{i+1}: {lines[i][:130]}")
