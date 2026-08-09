"""Verify the ACTUAL transport implementation in llm_service.py vs SENTINEL's transport policy."""
import sys, inspect
from pathlib import Path
ROOT = Path("/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, str(ROOT / "src"))

src = (ROOT / "src/arena/llm_service.py").read_text()
lines = src.splitlines()

print("=== llm_service.py structure ===")
for pat in ["def ", "class ", "failover", "retry", "backoff", "KEY_", "api_key", "timeout", "max_tokens",
            "requests.", "httpx", "urllib", "transport", "cycle", "envelope_failures", "provider_attempts"]:
    hits = [i for i, l in enumerate(lines, 1) if pat.lower() in l.lower()]
    if hits:
        print(f"  {pat!r}: lines {hits[:12]}")

print("\n=== class/method inventory ===")
for i, l in enumerate(lines, 1):
    if l.startswith("def ") or l.startswith("class "):
        print(f"  {i}: {l.strip()[:100]}")

print("\n=== REPAIR-VAL-01 wiring check: does LLMService use llm_transport? ===")
lt = (ROOT / "src/arena/llm_transport.py")
print("llm_transport.py exists:", lt.exists())
if lt.exists():
    lt_src = lt.read_text()
    print("  llm_transport defines:", [l.strip()[:70] for l in lt_src.splitlines() if l.startswith("class ") or l.startswith("def ")][:12])
print("  llm_service imports llm_transport:", "llm_transport" in src)
print("  llm_service imports .llm_transport:", ".llm_transport" in src or "from arena.llm_transport" in src)

print("\n=== where do failover_count etc. come from? (runner reads _svc attrs) ===")
for pat in ["failover_count", "retries_by_key_alias", "final_key_alias", "failure_class",
            "final_provider_status", "logical_llm_calls", "provider_attempts", "envelope_failures"]:
    hits = [i for i, l in enumerate(lines, 1) if pat in l]
    print(f"  {pat}: {hits[:6]}")
