"""Verify: which adapter name each arm actually used per JSONL row."""
import json, collections

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"):
    sub = [r for r in rows if r["arm"] == arm]
    c = collections.Counter(r.get("adapter_name") for r in sub)
    print(f"{arm:16s}: adapter_name -> {dict(c)}")

# any adapter_error_events?
for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT"):
    sub = [r for r in rows if r["arm"] == arm]
    errs = sum((r.get("adapter_error_events") or 0) for r in sub)
    print(f"{arm}: total adapter_error_events = {errs}")