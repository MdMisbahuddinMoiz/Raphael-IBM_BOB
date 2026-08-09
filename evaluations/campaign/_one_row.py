import json

jsonl = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl"
with open(jsonl) as fh:
    for line in fh:
        r = json.loads(line)
        if r.get("run_id") == "abl_PROMPTED_AGENT_known-observable_s0000_holdout":
            print(json.dumps(r, indent=1))
            break