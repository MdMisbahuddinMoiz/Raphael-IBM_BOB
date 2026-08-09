import re
with open("evaluations/campaign/rbs_v4_final_report.md") as f:
    txt = f.read()
for m in re.finditer(r"reproducib|independently|deterministic.*rerun|rerun", txt, re.I):
    i = m.start()
    print(f"--- [{i}] ---")
    print(txt[max(0,i-100):i+200])
    print()