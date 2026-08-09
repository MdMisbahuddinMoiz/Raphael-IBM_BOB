import json, time
P="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/AMENDMENT_LEDGER.json"
d=json.load(open(P))

entry={
  "amendment_id": "AMENDMENT-HOLDOUT-LAUNCH-2026-08-07",
  "title": "Terminal holdout model identity + stale-artifact reconciliation",
  "authorizer": "SENTINEL (terminal authorization) + principal methodological ruling",
  "applied_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "reason": (
    "The 2026-08-07 SENTINEL terminal directive described the holdout model as gpt-oss:20b-cloud "
    "with 50k-token / 15-action budgets. That contradicts the FROZEN preregistration and "
    "AMENDMENT-A-2026-08-06 (treatment identity = nvidia/llama-3.3-nemotron-super-49b-v1, "
    "ACTION_CAP=5, ITERATION_BUDGET=5). Authorized methodological ruling: the requirement is "
    "MODEL PARITY (FULL_RAPHAEL == PROMPTED_AGENT on the exact same frozen provider), stability, "
    "and preregistration discipline (Rule/Freeze Discipline) - NOT gpt-oss specifically. Because "
    "the real terminal holdout had NOT started, the FROZEN Nemotron identity governs; a pre-start "
    "model switch to gpt-oss would be unjustified."
  ),
  "decisions": [
    "Holdout model = nvidia/llama-3.3-nemotron-super-49b-v1 @ https://integrate.api.nvidia.com/v1, "
    "temp 0.0, max_tokens 512, timeout 15 (frozen, AMENDMENT-A-2026-08-06). gpt-oss directive values "
    "(50k tokens / 15 actions) NOT adopted; ACTION_CAP=5 / ITERATION_BUDGET=5 remain frozen.",
    "Model parity for FULL_RAPHAEL == PROMPTED_AGENT on the same provider path: VERIFIED (parity probe PASS, "
    "all arms resolve to identical LLMProviderConfig).",
    "Frozen instrument verified byte-identical: all 9 SHA-256 source hashes in TERMINAL_VALIDATION_FREEZE.json PASS."
  ],
  "quarantine": (
    "evaluations/campaign/rbs_v4_holdout.jsonl (3,240 rows, Aug 5) is CONTAMINATED telemetry from a "
    "DISCONTINUED instrument: burned T1-T12 templates, 9 configs (NO PROMPTED_AGENT arm), "
    "gpt-oss:20b-cloud via ollama, seeds 1072-1101 (DEV range 1000-1999, NOT HOLDOUT 2000-9999). "
    "It does NOT represent a started frozen holdout. Moved to "
    "rbs_v4_holdout_STALE_T1T12_GPTOSS_QUARANTINE.jsonl; excluded from all analysis."
  ),
  "standards_scope": [
    "Frozen terminal campaign: 4 arms x 5 fresh families x 60 holdout seeds = 1,200 runs, "
    "HOLDOUT split (relative 0-59 -> absolute 2000-9999), Nemotron identity, ACTION_CAP=5.",
    "Collection-only: monitor experiment HEALTH only (completed/expected, infra failures, provider "
    "availability, manifest/hash integrity, duplicate run IDs, missing artifacts, budget enforcement). "
    "NO arm-level performance/success-rate inspection until collection closes and integrity verifies."
  ],
  "superseded_state": "None (append-only; reconciliation clarification of AMENDMENT-A-2026-08-06 against the 2026-08-07 SENTINEL gpt-oss directive).",
  "amended_state": "Terminal holdout model identity = nvidia/llama-3.3-nemotron-super-49b-v1 (frozen). gpt-oss directive not adopted.",
  "verification": [
    "model identity parity probe PASS (all 4 arms identical Nemotron LLMConfig)",
    "TERMINAL_VALIDATION_FREEZE.json source hashes 9/9 PASS"
  ]
}

d["entries"].append(entry)
json.dump(d, open(P,"w"), indent=2)
print("appended:", entry["amendment_id"], "| total entries:", len(d["entries"]))