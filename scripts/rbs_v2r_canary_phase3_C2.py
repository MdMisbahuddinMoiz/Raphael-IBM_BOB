#!/usr/bin/env python3
"""RBS-v2R Phase 3 (REVISION C2) — FROZEN-PATH PROVIDER CANARY.

This is the measurement-fidelity-correct canary. It exercises the EXACT
call chain the campaign uses: LLMService.run_inference() (build_envelope ->
call_llm_provider -> process_llm_response), with real evidence context.

Two complementary metrics are reported:
  * success_rate: fraction of calls yielding SemanticInferenceSuccess
    (the frozen instrument's own success criterion = the "llm_produced" metric).
  * degradation_rate: of those Successes, the fraction whose category == UNCLEAR
    because the parser fell back to "treat entire content as claim".
    The Gemma reference produced ZERO "unclear" outputs, so a non-zero
    unclear rate is silent semantic degradation (refusals/prose masquerading
    as valid inference) and confounds the causal measurement.

Telemetry: evaluations/campaign/rbs_v2r_canary_C2.jsonl
"""
import json
import sys
import time
from pathlib import Path

REPO = Path("/home/yaser/raphael-2.0-rbsv2r")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))
OUT = REPO / "evaluations" / "campaign" / "rbs_v2r_canary_C2.jsonl"

from arena.llm_service import LLMService, LLMProviderConfig, SemanticInferenceSuccess, SemanticInferenceFailure
from arena.semantic_inference import build_evidence_context
from arena.semantic_inference import InferenceCategory

OVERRIDE = LLMProviderConfig(
    model_id="gpt-oss:20b-cloud",
    provider="ollama",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    timeout_seconds=180,
    temperature=0.0,
    max_tokens=16384,
)

# Real evidence items in the format build_evidence_context expects
EVIDENCE_SET = [
    ("hypothesis", "arena-d6-001", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "22/tcp open SSH-2.0-OpenSSH_8.9p1"}]),
    ("hypothesis_ent", "arena-d6-002", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "21/tcp open ftp vsftpd 3.0.3"}]),
    ("falsification", "arena-d6-003", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "80/tcp open http"}, {"type": "http_response", "target": "10.0.38.29", "source": "curl", "content": "HTTP/1.1 404 Not Found"}]),
    ("world_model", "arena-d6-004", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "21/tcp ftp, 22/tcp ssh, 80/tcp http"}]),
    ("planning", "arena-d6-005", [{"type": "state", "target": "10.0.38.29", "source": "planner", "content": "4 services discovered; 5 actions remain in budget"}]),
    ("semantic_llm", "arena-d6-006", [{"type": "http_response", "target": "10.0.38.29", "source": "web", "content": "wordpress upload endpoint /wp-content/uploads/ writable"}, {"type": "kb", "target": "CVE", "source": "cve_feeds", "content": "CVE-2025-69212 php path traversal to RCE"}]),
    ("defeater", "arena-d6-007", [{"type": "http_response", "target": "10.0.38.29", "source": "probe", "content": "HTTP 200 on /admin"}, {"type": "http_response", "target": "10.0.38.29", "source": "probe", "content": "HTTP 404 on /admin"}]),
    ("student_cand", "arena-d6-001", [{"type": "recon", "target": "10.0.38.29", "source": "student", "content": "wordpress + mysql service stack identified"}]),
    ("contradiction", "arena-d6-003", [{"type": "state", "target": "episode", "source": "broker", "content": "action allowed then denied then allowed on same evidence"}]),
    ("belief_update", "arena-d6-004", [{"type": "http_response", "target": "10.0.38.29", "source": "http_headers", "content": "Server: nginx/1.18.0"}]),
    # -- second block (N=20) covering remaining semantic task kinds --
    ("host_identity", "arena-d6-002", [{"type": "dns", "target": "10.0.38.29", "source": "dns_reverse", "content": "PTR record host-a.internal"}, {"type": "dns", "target": "10.0.38.29", "source": "dns_forward", "content": "A record host-a.internal -> 10.0.38.29"}]),
    ("vuln_indication", "arena-d6-006", [{"type": "http_response", "target": "10.0.38.29", "source": "web", "content": "Apache/2.4.49 present on 8080"}, {"type": "kb", "target": "CVE", "source": "cve_feeds", "content": "CVE-2021-41773 path traversal in Apache 2.4.49"}]),
    ("version_assess2", "arena-d6-006", [{"type": "banner", "target": "10.0.38.29", "source": "netcat", "content": "220 (vsFTPd 3.0.3)"}]),
    ("state_desc2", "arena-d6-004", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "443/tcp filtered https, 3306/tcp closed mysql"}]),
    ("defeater2", "arena-d6-007", [{"type": "http_response", "target": "10.0.38.29", "source": "probe", "content": "HTTP 302 redirect to /login on /admin"}, {"type": "http_response", "target": "10.0.38.29", "source": "probe", "content": "HTTP 200 on /admin/index.html"}]),
    ("service_id2", "arena-d6-001", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "445/tcp open microsoft-ds, 139/tcp open netbios-ssn"}]),
    ("contradiction2", "arena-d6-003", [{"type": "banner", "target": "10.0.38.29", "source": "ssh", "content": "SSH-2.0-OpenSSH_7.6p1"}, {"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "22/tcp closed ssh"}]),
    ("semantic_llm2", "arena-d6-006", [{"type": "http_response", "target": "10.0.38.29", "source": "web", "content": "login.php reflects POST username in page body"}, {"type": "kb", "target": "CVE", "source": "cve_feeds", "content": "SQL injection in login parameter (generic pattern)"}]),
    ("planning2", "arena-d6-005", [{"type": "state", "target": "10.0.38.29", "source": "planner", "content": "2 of 5 actions used; exploit phase pending; capture objective unsolved"}]),
    ("world_model2", "arena-d6-004", [{"type": "port_scan", "target": "10.0.38.29", "source": "nmap", "content": "8080/tcp open http-proxy, 22/tcp open ssh"}]),
]


def classify(result) -> dict:
    """Classify a frozen run_inference result with degradation detection."""
    if isinstance(result, SemanticInferenceSuccess):
        degraded = (result.category == InferenceCategory.UNCLEAR)
        return {
            "class": "success_degraded" if degraded else "success",
            "category": str(result.category.value),
            "confidence": result.confidence,
            "claim_head": result.claim[:120],
            "inference_id": result.inference_id,
        }
    # SemanticInferenceFailure
    return {
        "class": "failure",
        "failure_type": result.failure_type,
        "diagnostic": getattr(result, "diagnostic_detail", "")[:150],
        "attempt_id": result.attempt_id,
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    service = LLMService(config=OVERRIDE)
    results = []
    print("=== RBS-v2R PHASE 3C2: FROZEN-PATH CANARY (gpt-oss:20b-cloud / ollama) ===")
    print(f"Uses LLMService.run_inference() — the exact campaign call chain")
    print(f"N={len(EVIDENCE_SET)} frozen-path calls (max_tokens=16384, timeout=180)\n")

    t_start = time.time()
    for i, (kind, scenario, evidence) in enumerate(EVIDENCE_SET, 1):
        combined_text = build_evidence_context(evidence)
        t0 = time.time()
        try:
            result = service.run_inference(
                observation_text=combined_text,
                source_evidence_ids=(f"ev-{i}",),
                run_id=f"canary-c2-{i}",
            )
            cls = classify(result)
            cls["latency"] = round(time.time() - t0, 2)
        except Exception as e:
            cls = {"class": "exception", "detail": str(e)[:150],
                   "latency": round(time.time() - t0, 2)}
        cls["prompt_kind"] = kind
        cls["scenario"] = scenario
        results.append(cls)
        print(f"  [{i:02d}] {kind:16s} class={cls['class']:16s} "
              f"lat={cls.get('latency','?'):>6}s cat={cls.get('category','-')} "
              f"fail={cls.get('failure_type','-')}")
        with open(OUT, "a") as f:
            f.write(json.dumps(cls) + "\n")

    # Aggregation
    classes = {}
    for r in results:
        classes[r["class"]] = classes.get(r["class"], 0) + 1
    success = classes.get("success", 0) + classes.get("success_degraded", 0)
    degraded = classes.get("success_degraded", 0)
    failures = classes.get("failure", 0)
    exceptions = classes.get("exception", 0)
    latencies = [r["latency"] for r in results if isinstance(r.get("latency"), (int, float))]
    rate = success / len(results) if results else 0.0
    deg_rate = degraded / success if success else 0.0

    print(f"\n=== CANARY C2 SUMMARY (frozen-path, gpt-oss:20b-cloud) ===")
    for k, v in sorted(classes.items()):
        print(f"  {k}: {v}")
    if latencies:
        latencies.sort()
        print(f"  mean latency: {sum(latencies)/len(latencies):.2f}s  "
              f"p95: {latencies[int(len(latencies)*0.95)-1]:.2f}s")
    printed_ok = classes.get("success", 0)
    print(f"  SemanticInferenceSuccess: {success}/{len(results)} = {rate:.1%}  (frozen success criterion)")
    print(f"  of which DEGRADED (category==unclear): {degraded} ({deg_rate:.1%} of successes)")
    print(f"  clean successes (real category): {printed_ok}")
    print(f"  failures: {failures}  exceptions: {exceptions}")

    summary = {
        "phase": 3, "revision": "C2", "model": "gpt-oss:20b-cloud",
        "provider": "ollama_cloud", "path": "LLMService.run_inference (frozen)",
        "max_tokens": 16384, "timeout_seconds": 180,
        "calls": len(results), "classes": classes,
        "success_rate": rate,
        "degraded_successes": degraded,
        "degradation_rate_of_successes": deg_rate,
        "gemma_reference_unclear_count": 0,
        "gate_success": rate >= 0.90,
        "verdict": "PROVIDER_RELIABLE" if rate >= 0.90 else "PROVIDER_NOT_RELIABLE",
        "note": "degradation (unclear fallback) counts against causal fidelity even though "
                "it passes the frozen 'produced' criterion; Gemma ref had 0 unclear",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (REPO / "evaluations" / "campaign" / "rbs_v2r_canary_C2_summary.json").write_text(
        json.dumps(summary, indent=2))

    print(f"\n  VERDICT: {summary['verdict']} (frozen success gate >= 90%)")
    print(f"  Degradation cluster: {degraded} unclear outputs (Gemma ref = 0) — flag to SENTINEL")
    print(f"  Telemetry: {OUT}")
    return 0 if rate >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())