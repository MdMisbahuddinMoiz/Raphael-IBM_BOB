#!/usr/bin/env python3
"""RBS-v2R Phase 3 — Failure-genesis probe.

Determines whether the 2 'empty' canary responses are:
  (A) provider failure (genuinely empty)        -> counts against reliability
  (B) thinking-budget trap (reasoning_content present, max_tokens exhausted)
     -> a frozen-config measurement defect, distinct from provider reliability

Inspects the FULL message object including reasoning_content / content.
Does NOT modify any frozen parameter. This is diagnostics only.
"""
import json
import sys
import urllib.request

API_BASE = "http://localhost:11434/v1"
MODEL = "gpt-oss:20b-cloud"
MAX_TOKENS = 4096
TIMEOUT = 150

PROBES = [
    ("world_model_update", "New observable: port 3306 open on same host. Update identity. Return JSON {\"updated_identity\": str}."),
    ("planner_rerank", "New evidence: version disclosure Apache/2.4.49. Rerank exploit feasibility. Return JSON {\"rerank\": [str]}."),
]

for kind, prompt in PROBES:
    print(f"=== probe: {kind} ===")
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            d = json.loads(resp.read())
        msg = d["choices"][0]["message"]
        print("  message keys:", list(msg.keys()))
        for k, v in msg.items():
            if isinstance(v, str):
                print(f"    {k}: len={len(v)} | head={v[:80]!r}")
            else:
                print(f"    {k}: {v!r}")
        usage = d.get("usage", {})
        print("  usage:", usage)
        finish = d["choices"][0].get("finish_reason")
        print("  finish_reason:", finish)
    except Exception as e:
        print("  ERROR:", e)
    print()