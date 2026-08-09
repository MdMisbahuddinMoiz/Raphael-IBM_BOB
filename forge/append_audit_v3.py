"""Append audit section 12 cleanly (strip any prior mangled append)."""
import re

path = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/PROMPTED_AGENT_ANOMALY_AUDIT.md"
text = open(path, encoding="utf-8").read()

# Remove any previously-appended section 12 (mangled by shell heredoc)
marker = "\n## 12. Re-Audit v4"
if marker in text:
    text = text[: text.index(marker)]
    text = text.rstrip() + "\n"

section = """

---

## 12. Re-Audit v4 — D13 Patches + Live LLM (2026-08-09) — GATE PASSED

**Status: RESOLVED.** SENTINEL authorized Fix 1 (parser phrasing alignment),
Fix 2 (prompt tightening), and the EOL model ruling
(AMENDMENT-MODEL-EOL-2026-08-09) on 2026-08-09. All applied via
`forge/apply_d13_fixes.py` + `forge/apply_d13_blocks.py` (backups
`.forge_backup.d13`); tracked suite 127/127 PASS; unit tests extended and
passing (`forge/verify_l028_fix.py`).

### What changed
- **EOL:** frozen `deepseek-ai/deepseek-v4-flash` (HTTP 410 since 2026-08-07) ->
  live `deepseek-ai/deepseek-v4-flash-0731`; hardcoded key removed, keys now
  resolved via `_resolve_nvidia_api_key()` (env + .env).
- **Fix 1 (FALLBACK 5):** second pattern `(?:runs? an? [\\w-]+ service )?on port (\\d+)`
  + svc_type map (apache/nginx/tomcat -> http).
- **Fix 1 extension (FALLBACK 6):** SERVICE_TYPE extraction for port-less
  phrasings (`runs an HTTP service on Linux`, `with MySQL service`,
  `runs HTTP and SSH services`) — accumulate across patterns, dedupe, never
  invents ports.
- **Fix 2 (prompt):** duplicated rules removed; `{}` escape hatch replaced with
  mandatory predicate population (has_service/service_type for identified
  services, version/CVE when in evidence), "never invent" guard preserved.

### Final gate (10 stratified samples, live model, key rotation A/B)
| metric | result |
|---|---|
| fallback-sourced typed predicates | **9/10** (gate >= 8/10) |
| MECHANICAL (zero claims) | **0/10** (stop >= 2/10) |
| model_inference evidence | 10/10 samples (4-5 each) |
| provider failures | 0 in 8/10; 1 transient 503 in 2/10 (still produced predicates) |
| INFRA_FAILURE runs | 0/10 |
| best outcome | known-observable s=1: **score 1.0 CORRECT** (first in campaign) |

**VERDICT: GATE PASSED** (9/10 >= 8/10; 0/10 MECHANICAL). Per SENTINEL Option A
directive, authorized to proceed to the 1,200-row holdout.

### Remaining known limitation (out of scope, Fix 3 deferred)
Initial evidence fed to the LLM never contains version/CVE strings
(syn_scan returns bare `open apache`; `method="all"` not used), so
version/CVE predicates are unextractable in the llm_only arm regardless of
parser quality. SENTINEL deferred Fix 3 (candidate syn_scan method="all")
until after the gate; the contradiction template's "identify true version"
evaluator check therefore remains unreachable in this arm.

*Artifacts: `evaluations/campaign/L028_VERIFICATION.json` (v4, gate verdict
recorded), `evaluations/campaign/AMENDMENT_LEDGER.json`
(AMENDMENT-MODEL-EOL-2026-08-09), `src/arena/manifests/D13_L028_PARSER_ALIGNMENT_SPEC.json`*
"""

with open(path, "w", encoding="utf-8") as f:
    f.write(text + section)
print("section 12 appended cleanly")
