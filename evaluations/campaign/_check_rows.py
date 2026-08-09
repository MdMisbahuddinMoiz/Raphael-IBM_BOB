import json, os
P="/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl"
rows=[json.loads(l) for l in open(P) if l.strip()]
print("rows:", len(rows))
for r in rows:
    print("  config=%s family=%s seed=%s abs_seed=%s sid=%s model=%s provider=%s tag=%s"
          % (r["config"], r["template"], r["seed"], r["abs_seed"], r["scenario_id"],
             r["model_id"], r["provider"], r["instrument_tag"]))
    assert r["phase"]=="holdout"
    assert 2000 <= r["abs_seed"] < 10000, "BAD ABS SEED"
    assert r["campaign"]=="rbs-v4-holdout"
    assert r["model_id"]=="nvidia/llama-3.3-nemotron-super-49b-v1"
print("SCHEMA CHECK: PASS")