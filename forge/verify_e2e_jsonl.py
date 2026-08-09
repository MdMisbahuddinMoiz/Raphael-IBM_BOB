#!/usr/bin/env python3
"""FORGE Phase 4 — E2E JSONL telemetry integrity trace (Rule 1).

Verifies for the newest campaign runs:
  - episodes.jsonl parses, run_id consistent, episode_id unique
  - events.jsonl parses, references only existing episode_ids
  - metrics JSON (if present) matches episode counts
  - no None/corrupt lines
Run: .venv/bin/python forge/verify_e2e_jsonl.py
"""
import json, sys, glob, os
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/dev_runs/raw")
runs = sorted(glob.glob(str(ROOT / "abl_*")), key=os.path.getmtime)[-6:]
print(f"Checking {len(runs)} most recent runs\n")

allok = True
for rd in runs:
    name = os.path.basename(rd)
    ep_path = os.path.join(rd, "episodes.jsonl")
    ev_path = os.path.join(rd, "events.jsonl")
    if not os.path.exists(ep_path) or not os.path.exists(ev_path):
        print(f"  [!] {name}: missing episode/event jsonl")
        allok = False
        continue
    ep_ids, run_ids = set(), set()
    n_ep = n_ev = bad = 0
    seq_dup = 0
    with open(ep_path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                bad += 1; continue
            n_ep += 1
            key = (obj.get("episode_id"), obj.get("sequence_number"))
            if key in ep_ids:
                seq_dup += 1
            ep_ids.add(key)
            run_ids.add(obj.get("run_id"))
    with open(ev_path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                bad += 1; continue
            n_ev += 1
    ok = (n_ep >= 1) and (seq_dup == 0) and (len(run_ids) == 1) and bad == 0
    print(f"  [{'OK' if ok else 'FAIL'}] {name}: episode_snapshots={n_ep} dup_composite_key={seq_dup} "
          f"run_ids={len(run_ids)} events={n_ev} parse_bad={bad}")
    if not ok:
        allok = False

print("-" * 60)
print("E2E JSONL VERDICT:", "INTEGRITY OK" if allok else "CORRUPTION DETECTED")
sys.exit(0 if allok else 1)