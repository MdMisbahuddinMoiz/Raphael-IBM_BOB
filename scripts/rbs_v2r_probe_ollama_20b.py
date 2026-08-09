#!/usr/bin/env python3
"""Single-call probe: gpt-oss:20b-cloud via local ollama /v1 endpoint.

SENTINEL directive: run the cloud model via ollama. max_tokens=16384
to defeat the thinking-budget trap (frozen parser reads message.content).
"""
import json
import time
import urllib.request

API_BASE = "http://localhost:11434/v1"
MODEL = "gpt-oss:20b-cloud"
MAX_TOKENS = 16384
TIMEOUT = 180

def probe(n, prompt):
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
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        lat = time.time() - t0
        d = json.loads(raw)
        msg = d["choices"][0]["message"]
        print(f"[{n}] HTTP 200 | {lat:.1f}s | msg keys: {list(msg.keys())}")
        print(f"    content({len(msg.get('content',''))}): {msg.get('content','')[:100]!r}")
        for k in msg:
            if k not in ("content", "role"):
                v = msg[k]
                if isinstance(v, str):
                    print(f"    {k}({len(v)}): {v[:80]!r}")
                else:
                    print(f"    {k}: {type(v).__name__}")
        print(f"    usage: {d.get('usage')} | finish: {d['choices'][0].get('finish_reason')}")
        return True
    except Exception as e:
        print(f"[{n}] ERROR {type(e).__name__}: {str(e)[:200]}")
        return False

if __name__ == "__main__":
    print(f"=== probe {MODEL} via ollama /v1 ===")
    probe(1, "Reply with exactly: {\"claim\": \"echo\", \"category\": \"connection\"}")
    probe(2, "New observable: port 3306 open on same host. Update identity. Return JSON {\"updated_identity\": str}.")
