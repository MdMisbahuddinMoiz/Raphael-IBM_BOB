#!/usr/bin/env python3
"""FORGE — live LLM transport smoke (NVIDIA endpoint, dual-key failover).

Sends one minimal inference call through the frozen transport and records
outcome + telemetry fields. Never prints credentials.
"""
import os, sys, json
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")
from dotenv import load_dotenv  # if present
load_dotenv("/home/yaser/raphael-2.0-rbsv2r/.env")

mods = ["arena.ablation_runner", "arena.llm_transport", "arena.semantic_inference"]
for m in mods:
    try:
        __import__(m)
        print(f"[+] import {m} OK")
    except Exception as e:
        print(f"[x] import {m}: {type(e).__name__}: {e}")

# Direct transport-level probe (no credentials printed)
from arena.llm_transport import resolve_keys, execute_with_failover
keys = resolve_keys()
print(f"[i] key aliases resolved: {list(keys.keys())}")

try:
    out = execute_with_failover(
        url="https://integrate.api.nvidia.com/v1/chat/completions",
        payload_bytes=b"{}",  # empty payload — transport probe only
        headers_template={"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        timeout_seconds=20,
        keys=keys,
    )
    print(f"[i] transport probe: final_status={getattr(out, 'final_provider_status', '?')} class={getattr(out, 'failure_class', '?')}")
except Exception as e:
    print(f"[x] transport probe: {type(e).__name__}: {str(e)[:100]}")