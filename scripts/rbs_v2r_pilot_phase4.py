#!/usr/bin/env python3
"""RBS-v2R Phase 4 — Cross-Model Pilot Runner (GPT-OSS-20B Cloud vs Gemma reference).

FROZEN INSTRUMENT: detached-HEAD worktree /home/yaser/raphael-2.0-rbsv2r @ a28c2159.
FREEZE OF RECORD: baseline/rbs_v2r_freeze_manifest_C.json (rbs-v2r-freeze-C)
  - provider: gpt-oss:20b-cloud via ollama (localhost:11434/v1)
  - max_tokens=16384, timeout=180s, temperature=0.0
  - canary C2: 20/20 = 100% SemanticInferenceSuccess, 0 degraded (PROVIDER_RELIABLE)

PILOT DESIGN (per RBS-v2R directive):
  - 10 seeds (1042-1051) x 5 configs x 5 relevant templates
  - Configs: FULL_RAPHAEL, NO_LLM, NO_HYPOTHESIS, NO_FALSIFICATION, SCRIPTED_BASELINE
  - Templates: T1, T3, T5, T6, T7 (representative + Phase-1 failure-relevant)
  - Telemetry schema is BYTE-IDENTICAL to the Gemma reference campaign: this
    script imports the frozen scripts/run_rbsv2_campaign.py module and calls its
    exact run_one(), only swapping the frozen OVERRIDE to GPT-OSS. No src/ change.

Output: evaluations/campaign/rbs_v2r_pilot.jsonl
"""
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent)
_SRC = _REPO_ROOT + "/src"
for p in (_SCRIPTS, _SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _SRC)

# ── Freeze C provider override (module swap, no file change) ──────────
import run_rbsv2_campaign as frozen_campaign
from arena.semantic_inference import LLMProviderConfig

frozen_campaign.OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

PILOT_CONFIGS = ["FULL_RAPHAEL", "NO_LLM", "NO_HYPOTHESIS", "NO_FALSIFICATION", "SCRIPTED_BASELINE"]
PILOT_TEMPLATES = ["T1_NEGATIVE_CONTROL", "T3_FALSIFICATION_SENSITIVE",
                   "T5_PLANNING_COST", "T6_SEMANTIC_LLM", "T7_DEFEATER_SENSITIVE"]
PILOT_SEEDS = list(range(1042, 1052))  # first 10 of RBS-v2 seed set

OUT = Path(_REPO_ROOT) / "evaluations" / "campaign" / "rbs_v2r_pilot.jsonl"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = len(PILOT_CONFIGS) * len(PILOT_TEMPLATES) * len(PILOT_SEEDS)
    print("=== RBS-v2R PHASE 4 — PILOT (GPT-OSS-20B Cloud) ===")
    print(f"freeze: rbs-v2r-freeze-C | model: {frozen_campaign.OVERRIDE.model_id}")
    print(f"configs={PILOT_CONFIGS}")
    print(f"templates={PILOT_TEMPLATES}")
    print(f"seeds={PILOT_SEEDS}  total episodes={total}")
    print("schema: imported run_rbsv2_campaign.run_one (byte-identical to reference)")
    print()

    rows = []
    t_start = time.time()
    for config_id in PILOT_CONFIGS:
        for template_key in PILOT_TEMPLATES:
            for seed in PILOT_SEEDS:
                label = f"{config_id:18s} {template_key:24s} s{seed}"
                t0 = time.time()
                row, run_dir = frozen_campaign.run_one(config_id, template_key, seed)
                dt = time.time() - t0
                rows.append(row)
                print(f"  [{len(rows):3d}/{total}] {label} "
                      f"safety={row.get('safety_pass')} llm={row.get('llm_invocations')}/{row.get('llm_produced')} "
                      f"student={row.get('student_candidates_selected')} t={dt:.1f}s")
                with open(OUT, "a") as f:
                    f.write(json.dumps(row) + "\n")

    elapsed = time.time() - t_start
    print(f"\n=== PILOT COMPLETE ===")
    print(f"episodes: {len(rows)}/{total} | wall time: {elapsed:.1f}s")
    print(f"telemetry: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
