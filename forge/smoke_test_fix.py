"""Quick smoke test for actions_dispatched fix."""
import sys, json
from pathlib import Path
sys.path.insert(0, "src")
from arena.ablation_runner import AblationRunner
from arena.templates import TEMPLATE_REGISTRY
from arena.ablation import ABLATION_PRESETS

template = TEMPLATE_REGISTRY["known-observable"]
runner = AblationRunner(template=template, config=ABLATION_PRESETS["FULL_RAPHAEL"], seed=0, split="holdout")
metrics = runner.run()
m = metrics.to_dict()
print(f"actions_dispatched: {m.get('actions_dispatched')}")
print(f"actions_authorized: {m.get('actions_authorized')}")
print(f"actions_started: {m.get('actions_started')}")
print(f"actions_succeeded: {m.get('actions_succeeded')}")
print(f"score: {runner.evaluation_result.score if runner.evaluation_result else None}")