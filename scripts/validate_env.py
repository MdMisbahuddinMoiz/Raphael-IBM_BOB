#!/usr/bin/env python3
"""Validate .env configuration for security-critical values.

Tiered contract (REPAIR-VAL-01 + v3):
  - TIER 1 (NVIDIA dual-key): NVIDIA_API_KEY_A required; NVIDIA_API_KEY_B optional.
    If both present → dual-key failover mode (exit 0 if A present, 1 if only A).
  - TIER 2 (Legacy): TOR_CONTROL_PASS, API_KEY, NEO4J_PASS — optional (warning only).
  - TIER 3 (Services): GOPHISH_API_KEY, OMNIROUTE_API_KEY — optional (warning only).

Exit codes: 0 = OK (NVIDIA key A present), 1 = warnings only, 2 = NVIDIA key A missing.
"""
import os, sys

WEAK_PATTERNS = [
    "changeme", "change-me", "change_me", "password", "secret",
    "raphael-dev", "sk-omniroute-local", "raphael-layer5",
    "default", "test", "dev-key",
]

MIN_API_KEY_LENGTH = 32

ERRORS, WARNINGS = [], []

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if not os.path.exists(dotenv_path):
    print(f"  [!] .env not found at {dotenv_path}"); sys.exit(2)

env_vars = {}
with open(dotenv_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, _, v = line.partition("=")
        env_vars[k.strip()] = v.strip()

def check(var, label, required=False, min_length=0, reject_weak=True):
    val = env_vars.get(var, "")
    if required and not val:
        ERRORS.append(f"{var} ({label}): required but empty")
    elif not val:
        WARNINGS.append(f"{var} ({label}): empty (may be OK if not using this feature)")
    elif min_length and len(val) < min_length:
        ERRORS.append(f"{var} ({label}): too short ({len(val)} chars, min {min_length})")
    elif reject_weak:
        low = val.lower()
        for pat in WEAK_PATTERNS:
            if pat in low:
                ERRORS.append(f"{var} ({label}): weak pattern '{pat}'")
                break

def main():
    print("=" * 60)
    print("  Raphael v3 — Environment Validation (Tiered)")
    print("=" * 60); print()

    # TIER 1: NVIDIA dual-key (PRIMARY)
    check("NVIDIA_API_KEY_A", "NVIDIA API Key A", required=True, min_length=MIN_API_KEY_LENGTH)
    check("NVIDIA_API_KEY_B", "NVIDIA API Key B", required=False, min_length=MIN_API_KEY_LENGTH)

    # TIER 2: Legacy (optional)
    check("TOR_CONTROL_PASS", "Tor control password", required=False, min_length=16)
    check("API_KEY", "API gateway key", required=False, min_length=MIN_API_KEY_LENGTH)
    check("NEO4J_PASS", "Neo4j password", required=False, min_length=16)

    # TIER 3: Services (optional)
    check("GOPHISH_API_KEY", "Gophish API key", required=False, min_length=MIN_API_KEY_LENGTH)
    check("OMNIROUTE_API_KEY", "OmniRoute API key", required=False, min_length=8)
    check("OPENAI_API_KEY", "OpenAI API key", required=False, min_length=8)

    print()
    if ERRORS:
        print(f"  [✗] {len(ERRORS)} ERRORS:")
        for e in ERRORS: print(f"      - {e}")
        print()
    if WARNINGS:
        print(f"  [⚠] {len(WARNINGS)} WARNINGS:")
        for w in WARNINGS: print(f"      - {w}")
        print()

    has_nvidia_a = bool(env_vars.get("NVIDIA_API_KEY_A"))
    if not has_nvidia_a:
        print("  [✗] TIER 1 FAIL: NVIDIA_API_KEY_A missing — dual-key failover unavailable")
        return 2
    if not env_vars.get("NVIDIA_API_KEY_B"):
        print("  [⚠] TIER 1: NVIDIA_API_KEY_B absent — single-key mode (no failover)")
        return 1 if not ERRORS else 2
    print("  [✓] TIER 1 PASS: Dual-key failover ready")
    return 0 if not ERRORS else 2

if __name__ == "__main__":
    sys.exit(main())
