#!/usr/bin/env python3
"""RBS-v2R — single-call reachability probe for openai/gpt-oss-120b via NVIDIA.

Verifies the POST /chat/completions path works (earlier attempts returned
HTTP 000 / connection failures) before the full N=20 canary.
Frozen per SENTINEL directive: max_tokens=16384, temp=0.0.
"""
import json
import sys
import time
import urllib.request

API_BASE = "https://integrate.api.nvidia.com/v1"
API_KEY = "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"
MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 16384
TIMEOUT = 180

def probe(n):
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": (
            "Return JSON: {\"claim\": \"echo\", \"category\": \"connection\"}")}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        lat = time.time() - t0
        d = json.loads(raw)
        msg = d["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning", msg.get("reasoning_content", ""))
        print(f"[probe {n}] HTTP 200 | latency={lat:.2f}s | "
              f"content_len={len(content)} | reasoning_len={len(reasoning)} | "
              f"finish={d['choices'][0].get('finish_reason')}")
        print(f"  content head: {content[:120]!r}")
        usage = d.get("usage", {})
        print(f"  usage: {usage}")
        return True
    except urllib.error.HTTPError as e:
        print(f"[probe {n}] HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")
        return False
    except Exception as e:
        print(f"[probe {n}] ERROR ({type(e).__name__}): {str(e)[:200]}")
        return False

if __name__ == "__main__":
    print(f"=== reachability probe: {MODEL} @ {API_BASE} ===")
    ok = 0
    for i in range(1, 4):
        r = probe(i)
        ok += 1 if r else 0
        time.sleep(2)
    print(f"\n  reachability: {ok}/3 calls returned HTTP 200")
    sys.exit(0 if ok >= 1 else 1)
