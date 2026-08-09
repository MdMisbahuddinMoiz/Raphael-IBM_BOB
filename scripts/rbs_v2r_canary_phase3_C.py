#!/usr/bin/env python3
"""RBS-v2R Phase 3 (REVISION C) — Canary: gpt-oss:20b-cloud via LOCAL OLLAMA.

SENTINEL directive: "just run the cloud model via ollama".
Config: ollama /v1 (localhost:11434), model gpt-oss:20b-cloud,
max_tokens=16384 (thinking-budget mitigation per SENTINEL), timeout=180s.

Ollama emits reasoning field alongside content; frozen parser reads
message.content. Classification mirrors the frozen parser.

Telemetry: evaluations/campaign/rbs_v2r_canary_C.jsonl
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/yaser/raphael-2.0-rbsv2r")
OUT = REPO / "evaluations" / "campaign" / "rbs_v2r_canary_C.jsonl"

API_BASE = "http://localhost:11434/v1"
MODEL = "gpt-oss:20b-cloud"
MAX_TOKENS = 16384
TIMEOUT = 180
TEMPERATURE = 0.0

PROMPTS = [
    ("hypothesis", "Given evidence: SSH-2.0-OpenSSH_8.9p1 on 10.0.38.29. Propose a falsifiable hypothesis about the service stack. Return JSON {\"hypothesis\": str, \"prediction\": str}."),
    ("falsification", "Contradiction: nmap shows port 80 open but curl returns 404 on /. Design a discriminating test. Return JSON {\"discriminator\": str}."),
    ("world_model", "Correlate services ftp+ssh on host 10.0.38.29 into an identity hypothesis. Return JSON {\"identity\": str, \"confidence\": float}."),
    ("planning", "Action budget: 5. Rank: scan, banner, exploit, escalate, capture. Return JSON {\"plan\": [str]}."),
    ("semantic_llm", "Chain CVE-2025-69212 with an upload endpoint to reach RCE. Return JSON {\"chain\": [str], \"feasible\": bool}."),
    ("defeater", "Evidence X says HTTP 200 on /admin. Evidence Y says 404. Which defeats which? Return JSON {\"defeater\": str}."),
    ("probe_echo", "Reply with exactly: {\"claim\": \"echo\", \"category\": \"connection\"}"),
    ("short_schema", "Return JSON {\"ok\": true}"),
    ("rank_candidates", "Candidates: scan(0.9), ssh_banner(0.7), exploit(0.4). Choose one. Return JSON {\"selected\": str, \"rationale\": str}."),
    ("update_belief", "Prior P(service=apache)=0.6. Evidence: Server: nginx/1.18. Return JSON {\"posterior\": float}."),
    ("student_candidate", "Propose a stack-matched exploit technique for wordpress + mysql. Return JSON {\"technique\": str, \"capability\": str}."),
    ("contradiction_detect", "Episodes: [allow, deny, allow]. Detect tool disagreement. Return JSON {\"contradictions\": int}."),
    ("hypothesis_revise", "Hypothesis H1 failed its prediction. Revise. Return JSON {\"revised_hypothesis\": str}."),
    ("world_model_update", "New observable: port 3306 open on same host. Update identity. Return JSON {\"updated_identity\": str}."),
    ("planner_rerank", "New evidence: version disclosure Apache/2.4.49. Rerank exploit feasibility. Return JSON {\"rerank\": [str]}."),
    ("semantic_chain2", "Is 10.0.55.10 webapp vulnerable to path traversal? Return JSON {\"vulnerable\": bool, \"cve\": str}."),
    ("falsify_candidate", "Discriminator result: banner matches. Does this falsify H1? Return JSON {\"falsified\": bool}."),
    ("probe_schema", "Return JSON {\"schema\": \"d4-envelope-v2\", \"status\": \"ok\"}"),
    ("budget_check", "2 actions used, budget 5. Continue? Return JSON {\"continue\": bool}."),
    ("safety_check", "Action: write to /etc/passwd. Authorize? Return JSON {\"authorized\": bool, \"reason\": str}."),
]

def call(prompt: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
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
        latency = time.time() - t0
        d = json.loads(raw)
        msg = d["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
        usage = d.get("usage", {})
        return {
            "status": "success",
            "latency": round(latency, 2),
            "content": content,
            "content_len": len(content),
            "reasoning_len": len(reasoning),
            "finish_reason": d["choices"][0].get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    except urllib.error.HTTPError as e:
        latency = time.time() - t0
        body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 429 or "quota" in body.lower() or "rate" in body.lower():
            return {"status": "quota", "latency": round(latency, 2), "http": e.code, "detail": body}
        return {"status": "http_error", "latency": round(latency, 2), "http": e.code, "detail": body}
    except urllib.error.URLError as e:
        latency = time.time() - t0
        return {"status": "timeout" if "timed out" in str(e).lower() else "conn_error",
                "latency": round(latency, 2), "detail": str(e)[:200]}
    except Exception as e:
        latency = time.time() - t0
        return {"status": "error", "latency": round(latency, 2), "detail": str(e)[:200]}

def classify(result: dict, prompt_kind: str) -> dict:
    row = dict(result)
    row["prompt_kind"] = prompt_kind
    if result["status"] == "success":
        content = result.get("content", "")
        if not content.strip():
            row["class"] = "empty"
        else:
            stripped = content.strip()
            if not (stripped.startswith("{") or "{" in stripped[:20]):
                row["class"] = "malformed"
            else:
                row["class"] = "success"
    elif result["status"] == "quota":
        row["class"] = "quota"
    elif result["status"] == "timeout":
        row["class"] = "timeout"
    else:
        row["class"] = "failure"
    return row

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"=== RBS-v2R PHASE 3C: PROVIDER CANARY (gpt-oss:20b-cloud via ollama) ===")
    print(f"Model: {MODEL} | calls: 20 | max_tokens: {MAX_TOKENS} | timeout: {TIMEOUT}s")
    print()
    t_start = time.time()
    for i, (kind, prompt) in enumerate(PROMPTS, 1):
        r = call(prompt)
        row = classify(r, kind)
        results.append(row)
        print(f"  [{i:02d}] {kind:22s} class={row['class']:10s} "
              f"latency={row.get('latency', '?'):>6}s "
              f"reasoning={row.get('reasoning_len', '-'):>5} "
              f"content={row.get('content_len', '-'):>5} "
              f"finish={row.get('finish_reason', '?'):>6}")
        with open(OUT, "a") as f:
            f.write(json.dumps(row) + "\n")

    classes = {}
    for r in results:
        classes[r["class"]] = classes.get(r["class"], 0) + 1
    latencies = [r["latency"] for r in results if isinstance(r.get("latency"), (int, float))]
    success = classes.get("success", 0)
    rate = success / len(results)

    print(f"\n=== CANARY SUMMARY (gpt-oss:20b-cloud / ollama) ===")
    for k, v in sorted(classes.items()):
        print(f"  {k}: {v}")
    if latencies:
        latencies.sort()
        mean = sum(latencies) / len(latencies)
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        print(f"  mean latency: {mean:.2f}s")
        print(f"  p95 latency: {p95:.2f}s")
    print(f"  call_success_rate: {rate:.1%} ({success}/{len(results)})")
    print(f"  total wall time: {time.time() - t_start:.0f}s")

    summary = {
        "phase": 3, "revision": "C", "model": MODEL,
        "provider": "ollama_cloud", "api_base": API_BASE,
        "max_tokens": MAX_TOKENS, "timeout_seconds": TIMEOUT,
        "calls": len(results), "classes": classes,
        "success_rate": rate,
        "mean_latency": round(mean, 2) if latencies else None,
        "p95_latency": round(p95, 2) if latencies else None,
        "acceptance": rate >= 0.90,
        "verdict": "PROVIDER_RELIABLE" if rate >= 0.90 else "PROVIDER_NOT_RELIABLE",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (REPO / "evaluations" / "campaign" / "rbs_v2r_canary_C_summary.json").write_text(
        json.dumps(summary, indent=2))

    print(f"\n  VERDICT: {summary['verdict']} (acceptance >= 90%)")
    print(f"  Telemetry: {OUT}")
    if rate >= 0.90:
        print("PHASE 3C GATE: PASS — proceed to Phase 4 pilot (pending SENTINEL)")
        return 0
    print("PHASE 3C GATE: FAIL — PROVIDER_NOT_RELIABLE")
    return 1

if __name__ == "__main__":
    sys.exit(main())
