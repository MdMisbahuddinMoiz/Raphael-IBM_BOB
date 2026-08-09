#!/usr/bin/env python3
"""RBS-v2R Phase 2 (REVISION B) — Freeze Manifest for openai/gpt-oss-120b.

SENTINEL directive (2026-08-04): CONDITIONALLY AUTHORIZED use of
openai/gpt-oss-120b via NVIDIA API, provided it passes the same canary gate.

Configuration constraints per SENTINEL:
  - max_tokens MUST be 16384 (or higher) to defeat the thinking-budget trap
  - frozen parser (llm_service.py) reads only message.content — no src/ change
  - timeout: 180s (NVIDIA provider precedent from baseline/rbs_v3_manifest.json)
  - thinking: no disable parameter used; budget increase is the mitigation

Re-freeze provenance: ABORT of prior freeze (gpt-oss:20b-cloud @ max_tokens=4096
failed canary at 85%) -> NEW freeze ID rbs-v2r-freeze-B.
Output: baseline/rbs_v2r_freeze_manifest_B.json
"""
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from arena.semantic_inference import ENVELOPE_SYSTEM_PROMPT, ENVELOPE_VERSION
from arena.d6_manifest import SCENARIO_TEMPLATES

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def file_hash(p: Path) -> str:
    return sha256(p.read_text(encoding="utf-8", errors="replace"))

def git_head(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return "n/a"

prompt_hashes = {
    "envelope_version": ENVELOPE_VERSION,
    "envelope_system_prompt_sha256": sha256(ENVELOPE_SYSTEM_PROMPT),
}
template_hashes = {}
for key, info in sorted(SCENARIO_TEMPLATES.items()):
    template_hashes[key] = {
        "scenario_id": info.get("id"),
        "description_sha256": sha256(str(info)),
    }
prompt_hashes["d6_template_info_sha256"] = template_hashes

instrument_files = [
    "src/arena/ablation.py",
    "src/arena/ablation_runner.py",
    "src/arena/runner.py",
    "src/arena/semantic_inference.py",
    "src/arena/llm_service.py",
    "src/arena/d6_manifest.py",
    "src/orchestrator/brain/action.py",
    "scripts/run_rbsv2_campaign.py",
]
instrument_hashes = {}
for f in instrument_files:
    p = REPO / f
    if p.exists():
        instrument_hashes[f] = file_hash(p)

freeze = {
    "campaign": "rbs-v2r",
    "freeze_id": "rbs-v2r-freeze-B",
    "phase": 2,
    "revision": "B",
    "abort_reason": "freeze-A (gpt-oss:20b-cloud @ max_tokens=4096) failed canary at 85% (thinking-budget trap: empty content on 2/20 calls)",
    "authorization": "SENTINEL GLM-5.2 governance review 2026-08-04",
    "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_head": git_head(REPO),
    "provider": {
        "name": "nvidia_nim",
        "model_id": "openai/gpt-oss-120b",
        "api_base": "https://integrate.api.nvidia.com/v1",
        "api_key_source": "env: sentinel-provided nvapi key (verified 3/3 HTTP 200 reachability probe)",
        "context_length": None,
        "capabilities": ["completion", "reasoning", "thinking"],
        "ollama_version": None,
        "python_version": platform.python_version(),
    },
    "inference": {
        "temperature": 0.0,
        "top_p": None,
        "top_k": None,
        "reasoning_effort": "default (no disable parameter used; budget increase is mitigation)",
        "max_tokens": 16384,
        "timeout_seconds": 180,
        "timeout_precedent": "baseline/rbs_v3_manifest.json (NVIDIA path, 180s); ollama-local precedent was 120s",
        "retry_policy": {
            "health_probe_retries": 5,
            "health_probe_delay_seconds": 5.0,
            "per_run_retries": 3,
            "per_run_delay_seconds": 8.0,
            "campaign_abort_after_consecutive_zero_llm": 3,
        },
        "action_budget": 5,
        "random_seed_policy": "fixed seeds 1042-1071 (RBS-v2 set); pilot uses first 10",
    },
    "prompt_hashes": prompt_hashes,
    "instrument_file_hashes": instrument_hashes,
    "freeze_integrity": {
        "no_parameter_change_after": True,
        "abort_policy": "any change -> ABORT -> new campaign ID -> preregister again",
        "parser_constraint": "llm_service.py reads ONLY message.content (frozen, verified); no src/ change authorized",
    },
}

out = REPO / "baseline" / "rbs_v2r_freeze_manifest_B.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(freeze, indent=2, default=str))
print(f"Wrote freeze manifest B: {out}")
print(f"  freeze_id: {freeze['freeze_id']}")
print(f"  model: {freeze['provider']['model_id']}")
print(f"  max_tokens: {freeze['inference']['max_tokens']}")
print(f"  timeout: {freeze['inference']['timeout_seconds']}s")
print(f"  git_head: {freeze['git_head']}")
