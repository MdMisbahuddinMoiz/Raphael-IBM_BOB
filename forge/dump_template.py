"""Locate templates module + dump contradiction template evidence."""
import sys, inspect
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
import arena.templates as T
print("templates file:", T.__file__)
reg = T.TEMPLATE_REGISTRY
t = reg["contradiction"]
print("\ntemplate keys:", list(t.keys()) if hasattr(t, "keys") else dir(t))
evs = t.get("evidence", t.get("observations", []))
print("evidence entries:", len(evs))
for e in evs:
    if isinstance(e, dict):
        print(" ", e.get("type", "?"), "|", str(e.get("content", ""))[:150])
    else:
        print(" ", str(e)[:150])
