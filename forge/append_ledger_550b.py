"""Step 3+4: compute SHA of the ACTUAL runtime PROMPTED_AGENT_SYSTEM_PROMPT + append ledger entry."""
import hashlib, json, sys
from pathlib import Path

ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, str(ROOT / "src"))

# ── Step 4: SHA of the runtime prompt VALUE (imported, not regex) ──
from arena.semantic_inference import PROMPTED_AGENT_SYSTEM_PROMPT as RUNTIME_PROMPT
sha = hashlib.sha256(RUNTIME_PROMPT.encode("utf-8")).hexdigest()
print("RUNTIME PROMPTED_AGENT_SYSTEM_PROMPT sha256:", sha)
print("prompt length:", len(RUNTIME_PROMPT))

# ── Step 3: ledger append ──
CAM = ROOT / "evaluations/campaign"
ledger_path = CAM / "AMENDMENT_LEDGER.json"
d = json.load(open(ledger_path))
entry = {
    "amendment_id": "AMENDMENT-MODEL-550B-2026-08-09",
    "title": "Model hierarchy: 550B primary, 49B fallback; DeepSeek removed; transport wiring restored",
    "authorizer": "SENTINEL (GLM-5.2 governance review, 2026-08-09)",
    "applied_at_utc": "2026-08-09T13:30:00Z",
    "reason": (
        "DeepSeek removed entirely from the fallback chain (frozen deepseek-v4-flash EOL 2026-08-07; "
        "-0731 variant not functioning in environment). New hierarchy: PRIMARY nvidia/nemotron-3-ultra-550b-a55b, "
        "FALLBACK nvidia/llama-3.3-nemotron-super-49b-v1 (campaign-level only, NEVER mid-run). "
        "Transport policy frozen: KEY_A -> KEY_B failover (same model), exponential backoff base 1s cap 8s, "
        "2 retries/key/cycle, 2 cycles, temperature 0.0, max_tokens 16384, timeout 180s. "
        "REPAIR-VAL-01 llm_transport wiring into LLMService.call_llm_provider restored (was present at "
        "2026-08-07 holdout launch, lost since; holdout showed 900 rows of failover telemetry proving prior wiring)."
    ),
    "files_changed": [
        "src/arena/ablation_runner.py: 3 LLMProviderConfig sites -> model nvidia/nemotron-3-ultra-550b-a55b, timeout_seconds=180, max_tokens=16384 (temperature 0.0 kept); api_key stays _resolve_nvidia_api_key()",
        "src/arena/semantic_inference.py: LLMProviderConfig default model_id -> nvidia/nemotron-3-ultra-550b-a55b, timeout_seconds=180, max_tokens=16384",
        "src/arena/llm_service.py: call_llm_provider routes through llm_transport.call_chat_completion (byte-identical payload retries, KEY_A->KEY_B failover, bounded backoff); LLMService exposes provider_attempts, failover_count, retries_by_key_alias, final_key_alias, failure_class, final_provider_status, envelope_failures, input/output tokens; RawResponse parses usage; DiagnosticRawRecord carries tokens",
        "backups: src/arena/llm_service.py.forge_backup.550b; ablation_runner.py/.semantic_inference.py .forge_backup.d13 (pre-D13)",
    ],
    "supersedes": "AMENDMENT-MODEL-EOL-2026-08-09 (model choice portion); AMENDMENT-A-2026-08-06 (nemotron-49b as PRIMARY superseded -> 49b is FALLBACK only)",
    "transport_policy_freeze": {
        "provider": "NVIDIA NIM",
        "primary_model": "nvidia/nemotron-3-ultra-550b-a55b",
        "fallback_model": "nvidia/llama-3.3-nemotron-super-49b-v1 (campaign-level only, NOT mid-run)",
        "keys": {"primary": "KEY_A (env NVIDIA_API_KEY_A)", "secondary": "KEY_B (env NVIDIA_API_KEY_B)"},
        "allowed_failover": ["550B(KEY_A) -> 550B(KEY_B)", "49B(KEY_A) -> 49B(KEY_B)"],
        "forbidden": ["550B -> 49B mid-run", "any -> DeepSeek", "any -> other provider"],
        "retry_policy": "exponential backoff base 1s cap 8s; max 2 retries/key/cycle; max 2 cycles; KEY_B only after KEY_A exhaustion",
        "temperature": 0.0,
        "max_tokens": 16384,
        "timeout_seconds": 180,
    },
    "prompt_freeze": {
        "note": "D13 Fix 2 rewrote PROMPTED_AGENT_SYSTEM_PROMPT (v2.0). PROMPTED_PROMPT_FREEZE.json remains the frozen v1.0 record and is NOT modified. New runtime prompt SHA recorded for runner telemetry.",
        "runtime_prompt_sha256": sha,
        "old_frozen_instruction_block_sha256": "4c2f846495ad0ca8427df19ce253f985765991a79cd7a079e590782537865b5a",
    },
    "seed_scheme_ruling": (
        "SENTINEL CLARIFICATION: earlier '1072-1101' reference factually incorrect (VALIDATION band, "
        "used by quarantined stale T1T12 GPTOSS run). Authoritative: pre-registered HOLDOUT split, "
        "relative 0..59 -> absolute 2000..2059 (TERMINAL_FALSIFICATION_PREREGISTRATION + frozen runner guard)."
    ),
    "verification": [
        "compile OK: ablation_runner.py, llm_service.py, semantic_inference.py, llm_transport.py",
        "tests/test_llm_transport.py contract: seam source contains llm_transport, no nvapi",
        "tracked suite 127/127 re-verified post-patch",
        "gate on 550B: 10 stratified samples, >= 8/10 fallback-sourced typed predicates, < 2/10 MECHANICAL (pending execution)",
    ],
}
ids = [e["amendment_id"] for e in d["entries"]]
assert entry["amendment_id"] not in ids, "already present"
d["entries"].append(entry)
with open(ledger_path, "w") as f:
    json.dump(d, f, indent=2)
print("ledger entries:", len(d["entries"]))
print("appended:", entry["amendment_id"])
