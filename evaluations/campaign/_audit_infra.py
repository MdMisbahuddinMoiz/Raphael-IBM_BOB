"""Resolve infra_failures field semantics + details payload for PROMPTED rows."""
import json, collections

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

# infra_failures: type + sample
for r in rows[:60]:
    v = r.get("infra_failures")
    if isinstance(v, list):
        print("infra_failures is LIST. sample:", json.dumps(v)[:300])
        break
    if v:
        print("infra_failures scalar sample:", repr(v)[:200])
        break

# tally by arm: total infra_failures
for arm in ["FULL_RAPHAEL", "PROMPTED_AGENT", "NO_WORLD_MODEL", "SCRIPTED_BASELINE"]:
    sub = [r for r in rows if r["arm"] == arm]
    tot = 0
    nmax = 0
    for r in sub:
        v = r.get("infra_failures")
        if isinstance(v, list):
            nmax = max(nmax, len(v))
            tot += len(v)
        elif v:
            nmax = max(nmax, int(v))
            tot += int(v)
    print(f"{arm:16s}: infra_failures total={tot} max_row={nmax}")

# details sample for one PROMPTED row
probe = rows[0]
print("\nBONUS: one row 'details' :", json.dumps(probe["details"])[:400])
print("actions dispatched/started/successful:", probe.get("actions_dispatched"), probe.get("actions_started"), probe.get("actions_succeeded"))
print("iterations_used / ceiling / ACTION_CAP:", probe.get("iterations_used"), probe.get("budget_iteration_ceiling"), probe.get("budget_action_ceiling"), probe.get("ACTION_CAP"))

# what does 'model' of 'envelope' mean — check failure_class empty, final_provider_status
print("\nfinal_provider_status per arm:")
for arm in ("FULL_RAPHAEL", "PROMPTED_AGENT"):
    sub = [r for r in rows if r["arm"] == arm]
    c = collections.Counter(str(r.get("final_provider_status")) for r in sub)
    print(f"  {arm}: {dict(c)}")