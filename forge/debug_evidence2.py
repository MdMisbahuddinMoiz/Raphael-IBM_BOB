#!/usr/bin/env python3
import sys
import os

# Add the src directory to the path
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/scripts")
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r")

from arena.ablation_runner import AblationRunner
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS

# Run a single test to see what's happening
template = TEMPLATE_REGISTRY["contradiction"]
runner = AblationRunner(
    template=template,
    config=ABLATION_PRESETS["PROMPTED_AGENT"],
    seed=0,
    split="holdout",
)

# Run just the first iteration to see what happens
print("Running first iteration...")
runner.run()

# Check the evidence graph
print("\nEvidence in graph:")
for ev in runner.evidence_graph.get_all_evidence():
    print(f"  {ev.evidence_id}: type={ev.evidence_type}, target={ev.target}")

print("\nPending SI evidence IDs:", runner._pending_si_evidence_ids)
print("Episodes:", len(runner.episodes.episodes))
for i, ep in enumerate(runner.episodes.episodes):
    print(f"  Episode {i}: evidence_created={ep.evidence_created}")