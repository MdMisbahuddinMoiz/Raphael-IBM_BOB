"""Update the reproducibility wording in rbs_v4_final_report.md per D4."""
import re

with open("evaluations/campaign/rbs_v4_final_report.md") as f:
    txt = f.read()

# Find and replace the reproducibility note
old = "*Report generated 2026-08-05. Campaign data unmodified. All analyses in `rbs_v4_statistics.json` are reproducible from the raw JSONL with fixed seed bootstrap.*"
new = "*Report generated 2026-08-05. Campaign data unmodified. All analyses in `rbs_v4_statistics.json` are deterministic and rerunnable from the raw JSONL with fixed seed bootstrap; independent recomputation (D3) completed 2026-08-08 with identical numerical results.*"

if old in txt:
    txt = txt.replace(old, new)
    print("Replaced successfully")
else:
    print("OLD text not found exactly")
    # Try to find it
    for m in re.finditer(r"reproducible from the raw JSONL", txt):
        i = m.start()
        print(f"Found at {i}: {txt[i-50:i+150]}")

with open("evaluations/campaign/rbs_v4_final_report.md", "w") as f:
    f.write(txt)
print("Written")