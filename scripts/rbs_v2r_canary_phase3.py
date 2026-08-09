#!/usr/bin/env python3
"""RBS-v2R Phase 3 — Provider Canary for gpt-oss:20b-cloud.

Executes 20 representative inference calls against the FROZEN provider config.
Measures: successful responses, empty responses, malformed structured responses,
timeouts, quota failures, mean latency, p95 latency.

Acceptance: call_success_rate >= 90%.
Quota/rate-limit events are recorded SEPARATELY from model failures and are
NOT silently retried (per SENTINEL directive).

Telemetry: evaluations/campaign/rbs_v2r_canary.jsonl
"""
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/yaser/raphael-2.0-rbsv2r")
OUT = REPO / "evaluations" / "campaign" / "rbs_v2r_canary.jsonl"

# FROZEN provider config (Phase 2 manifest)
API_BASE = "http://localhost:11434/v1"
MODEL = "gpt-oss:20b-cloud"
MAX_TOKENS = 4096
TIMEOUT = 120
TEMPERATURE = 0.0

# 20 representative calls: mix of prompt shapes used by the campaign
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
    """One inference call. Returns {status, latency, detail}."""
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
        content = d["choices"][0]["message"].get("content", "")
        usage = d.get("usage", {})
        return {
            "status": "success",
            "latency": round(latency, 2),
            "content": content,
            "content_len": len(content),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    except urllib.error.HTTPError as e:
        latency = time.time() - t0
        body = e.read().decode("utf-8", errors="replace")[:300]
        # Distinguish QUOTA (429/rate-limit) from model failure
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
    """Add classification: success/empty/malformed/timeout/quota/failure."""
    row = dict(result)
    row["prompt_kind"] = prompt_kind
    if result["status"] == "success":
        content = result.get("content", "")
        if not content.strip():
            row["class"] = "empty"
        else:
            # Structured prompts expect JSON; malformed = no JSON object at all
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
    print(f"=== RBS-v2R PHASE 3: PROVIDER CANARY ===")
    print(f"Model: {MODEL} | calls: 20 | timeout: {TIMEOUT}s | temp: {TEMPERATURE}")
    print()
    for i, (kind, prompt) in enumerate(PROMPTS, 1):
        r = call(prompt)
        row = classify(r, kind)
        results.append(row)
        print(f"  [{i:02d}] {kind:22s} class={row['class']:10s} "
              f"latency={row.get('latency', '?'):>7} "
              f"len={row.get('content_len', '-'):>5}")
        # Write incrementally (crash-safe telemetry)
        with open(OUT, "a") as f:
            f.write(json.dumps(row) + "\n")

    # ── Summary ──
    classes = {}
    for r in results:
        classes[r["class"]] = classes.get(r["class"], 0) + 1
    latencies = [r["latency"] for r in results if isinstance(r.get("latency"), (int, float))]
    success = classes.get("success", 0)
    rate = success / len(results)

    print(f"\n=== CANARY SUMMARY ===")
    for k, v in sorted(classes.items()):
        print(f"  {k}: {v}")
    if latencies:
        latencies.sort()
        mean = sum(latencies) / len(latencies)
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        print(f"  mean latency: {mean:.2f}s")
        print(f"  p95 latency: {p95:.2f}s")
    print(f"  call_success_rate: {rate:.1%} ({success}/{len(results)})")

    summary = {
        "phase": 3,
        "model": MODEL,
        "calls": len(results),
        "classes": classes,
        "success_rate": rate,
        "mean_latency": round(mean, 2) if latencies else None,
        "p95_latency": round(p95, 2) if latencies else None,
        "acceptance": rate >= 0.90,
        "verdict": "PROVIDER_RELIABLE" if rate >= 0.90 else "PROVIDER_NOT_RELIABLE",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (REPO / "evaluations" / "campaign" / "rbs_v2r_canary_summary.json").write_text(
        json.dumps(summary, indent=2))

    print(f"\n  VERDICT: {summary['verdict']} (acceptance >= 90%)")
    print(f"  Telemetry: {OUT}")
    if rate >= 0.90:
        print("PHASE 3 GATE: PASS — proceed to Phase 4 pilot")
        return 0
    print("PHASE 3 GATE: FAIL — STOP, PROVIDER_NOT_RELIABLE. No architectural conclusion.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
