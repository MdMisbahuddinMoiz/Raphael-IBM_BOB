import sys, json, os
from pathlib import Path
fcwd = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(fcwd, "..", ".."))
_SRC = _REPO_ROOT + "/src"
print("REPO_ROOT:", _REPO_ROOT, "SRC:", _SRC)
for p in ( _SRC, _REPO_ROOT):
    while p in sys.path: sys.path.remove(p)
sys.path.insert(0, _SRC)
os.chdir(_REPO_ROOT)

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.templates import TEMPLATE_REGISTRY, ScenarioSplit
from arena.d6_manifest import ITERATION_BUDGET

MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
ARMS = ["FULL_RAPHAEL", "NO_WORLD_MODEL", "PROMPTED_AGENT", "SCRIPTED_BASELINE"]
FAMILY = "known-observable"
print("=== DRY PARITY PROBE (HOLDOUT split, first family) ===")
ok = True
for config_id in ARMS:
    template = TEMPLATE_REGISTRY[FAMILY]
    runner = AblationRunner(
        template=template,
        config=ABLATION_PRESETS[config_id],
        seed=0,
        split="holdout",
        llm_config_override=None,
    )
    cfg = runner.llm_service.config
    print(f"  {config_id:18s} model={cfg.model_id} provider={cfg.provider} "
          f"api_base={cfg.api_base} temp={cfg.temperature} max_tokens={cfg.max_tokens} "
          f"timeout={cfg.timeout_seconds}")
    if config_id != "SCRIPTED_BASELINE":
        parity = (cfg.model_id == MODEL_ID and cfg.provider == "nvidia")
    else:
        parity = True  # hermetic, no llm
    ok = ok and parity
print("ITERATION_BUDGET:", ITERATION_BUDGET)
print("PARITY PROBE:", "PASS" if ok else "FAIL")