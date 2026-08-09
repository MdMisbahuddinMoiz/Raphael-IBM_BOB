#!/usr/bin/env python3
"""FORGE import-map sweep across ALL src packages (Rule 2).

For every package dir under src/, attempt `import <pkg>.<module>` and report.
Run: .venv/bin/python forge/sweep_imports.py
"""
import importlib, os, sys

SRC = "/home/yaser/raphael-2.0-rbsv2r/src"
sys.path.insert(0, SRC)

ok, fail = [], []
for root, dirs, files in os.walk(SRC):
    if "__pycache__" in root:
        continue
    rel = os.path.relpath(root, SRC)
    for fn in sorted(files):
        if not fn.endswith(".py") or fn.startswith("__"):
            continue
        mod = os.path.join(rel, fn[:-3]).replace(os.sep, ".")
        try:
            importlib.import_module(mod)
            ok.append(mod)
        except Exception as e:
            fail.append((mod, f"{type(e).__name__}: {str(e)[:110]}"))

print(f"IMPORTABLE: {len(ok)}   FAILED: {len(fail)}")
for mod, err in fail:
    print(f"  [x] {mod} -> {err}")
print("VERDICT:", "ALL MODULES RESOLVE" if not fail else f"{len(fail)} MODULES FAIL TO RESOLVE")