#!/usr/bin/env python3
"""RBS-v2R Phase 2 — Freeze GPT-OSS Provider Manifest.

Records the exact frozen inference configuration + all prompt/tool hashes
required by the SENTINEL directive BEFORE any experimental execution.
Output: baseline/rbs_v2r_freeze_manifest.json
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

# ── Import the FROZEN modules at HEAD a28c2159 ──
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

# ── Prompt hashes ──
print("Computing prompt hashes...")
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

# ── Tool schema hashes ──
# Find tool schema files
tool_files = []
for p in REPO.rglob("*.py"):
    if ".venv" in str(p) or "node_modules" in str(p):
        continue
    if "tools" in p.name.lower() or "schema" in p.name.lower():
        tool_files.append(p)
tool_schema_hashes = {}
for p in sorted(tool_files)[:40]:
    tool_schema_hashes[str(p.relative_to(REPO))] = file_hash(p)

# ── Code files that define the instrument ──
instrument_files = [
    "src/arena/ablation.py",
    "src/arena/ablation_runner.py",
    "src/arena/runner.py",
    "src/arena/semantic_inference.py",
    "src/arena/d6_manifest.py",
    "src/arena/d6c_holdout_runner.py",
    "src/orchestrator/brain/action.py",
    "scripts/run_rbsv2_campaign.py",
]
instrument_hashes = {}
for f in instrument_files:
    p = REPO / f
    if p.exists():
        instrument_hashes[f] = file_hash(p)

# ── Provider freeze ──
freeze = {
    "campaign": "rbs-v2r",
    "phase": 2,
    "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_head": git_head(REPO),
    "provider": {
        "name": "ollama_cloud",
        "model_id": "gpt-oss:20b-cloud",
        "remote_model": "gpt-oss:20b",
        "remote_host": "https://ollama.com",
        "digest": "9a01793d9ef8de5309f157c06dbcbadfb598001b4a6f13cbc699cdff5042eaae",
        "parameter_size": "20.9B",
        "quantization": "MXFP4",
        "context_length": 131072,
        "capabilities": ["completion", "tools", "thinking"],
        "api_base": "http://localhost:11434/v1",
        "ollama_version": "0.32.5",
        "python_version": platform.python_version(),
    },
    "inference": {
        "temperature": 0.0,
        "top_p": None,
        "top_k": None,
        "reasoning_effort": "default (thinking capability enabled)",
        "max_tokens": 4096,
        "timeout_seconds": 120,
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
    "tool_schema_hashes": tool_schema_hashes,
    "instrument_file_hashes": instrument_hashes,
    "freeze_integrity": {
        "no_parameter_change_after": True,
        "abort_policy": "any change -> ABORT -> new campaign ID -> preregister again",
    },
}

out = REPO / "baseline" / "rbs_v2r_freeze_manifest.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(freeze, indent=2, default=str))
print(f"Wrote freeze manifest: {out}")
print(f"  git_head: {freeze['git_head']}")
print(f"  model: {freeze['provider']['model_id']}")
print(f"  system_prompt_sha256: {prompt_hashes['envelope_system_prompt_sha256']}")
print(f"  templates hashed: {len(template_hashes)}")
print(f"  tool schema files hashed: {len(tool_schema_hashes)}")
print(f"  instrument files hashed: {len(instrument_hashes)}")
