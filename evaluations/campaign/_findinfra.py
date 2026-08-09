import json, os
J="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl"
rows=[json.loads(l) for l in open(J) if l.strip()]
for r in rows:
    if "error" in r: continue
    pf=r.get("provider_failures") or 0
    inf=r.get("infra_failures") or []
    mf=r.get("model_failures") or 0
    if pf>0 or inf or mf>0:
        print("CELL:")
        for k in ["config","arm","template","seed","abs_seed","scenario_id","run_id",
                  "provider_failures","model_failures","infra_failures","adapter_error_events",
                  "envelope_failures","failure_class","final_provider_status",
                  "logical_llm_calls","provider_attempts","failover_count",
                  "final_key_alias","retries_by_key_alias","timestamp","elapsed_seconds"]:
            if k in r: print("   %s: %s" % (k, r[k]))