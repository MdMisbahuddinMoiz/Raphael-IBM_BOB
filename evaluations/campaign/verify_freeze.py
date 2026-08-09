import json, hashlib, os
ROOT="/home/yaser/raphael-2.0-rbsv2r"
freeze=json.load(open(os.path.join(ROOT,"evaluations/campaign/TERMINAL_VALIDATION_FREEZE.json")))
files=freeze["files_sha256"]
print("=== FREEZE HASH VERIFICATION ===")
allok=True
for rel,sha in files.items():
    p=os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print(f"  MISSING {rel}")
        allok=False; continue
    h=hashlib.sha256(open(p,"rb").read()).hexdigest()
    match = (h==sha)
    ok = "PASS" if match else "*MISMATCH*"
    if not match: allok=False
    print(f"  {rel:48s} {ok}  {h[:20]}...")
print("\nOVERALL:", "PASS" if allok else "FAIL")