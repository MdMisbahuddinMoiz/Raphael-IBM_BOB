"""Probe NVIDIA API: check .env keys, list live models, test alternatives."""
import json, re, sys

# 1. What keys does .env hold?
try:
    env_text = open("/home/yaser/raphael-2.0-rbsv2r/.env").read()
except Exception as e:
    print("read .env ERROR:", repr(e))
    sys.exit(1)

keys = {}
for m in re.finditer(r"^(NVIDIA_API_KEY[A-Z_]*)=(\S+)", env_text, re.M):
    keys[m.group(1)] = m.group(2)
print("env keys found:", {k: v[:20] + "..." for k, v in keys.items()})

frozen_key = "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"

def probe(key, label):
    import urllib.request
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        ids = [m["id"] for m in data.get("data", [])]
        # filter to likely-relevant ids
        interesting = [i for i in ids if any(
            t in i.lower() for t in ("deepseek", "nemotron", "qwen", "llama-4", "gpt"))
        ]
        print(f"\n[{label}] HTTP OK, {len(ids)} models total")
        print("  interesting:", interesting[:30])
        return ids
    except Exception as e:
        print(f"\n[{label}] ERROR: {repr(e)}")
        return []

frozen_ids = probe(frozen_key, "frozen-key")

# 2. Test frozen model + alternatives directly
def chat(model, key, label):
    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
        "max_tokens": 16,
    }).encode()
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read().decode())
        txt = out["choices"][0]["message"]["content"]
        print(f"[{label}] {model}: OK -> {txt[:80]!r}")
        return True
    except Exception as e:
        msg = str(e)
        if hasattr(e, "read"):
            try:
                msg = e.read().decode()[:200]
            except Exception:
                pass
        print(f"[{label}] {model}: FAIL -> {msg}")
        return False

print("\n--- live-model tests (frozen key) ---")
if frozen_ids:
    for m in frozen_ids[:6]:
        chat(m, frozen_key, "frozen-key")
else:
    print("no model list; will test named candidates")
    for m in ("nvidia/llama-3.3-nemotron-super-49b-v1",
              "deepseek-ai/deepseek-r1",
              "deepseek-ai/deepseek-v3",
              "nvidia/llama-3.1-nemotron-ultra-253b-v1",
              "qwen/qwen3-32b"):
        chat(m, frozen_key, "frozen-key")
