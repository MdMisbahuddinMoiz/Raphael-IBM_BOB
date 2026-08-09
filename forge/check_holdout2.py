import json
data = [json.loads(l) for l in open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl')]
for d in data[:5]:
    print(json.dumps(d, indent=2)[:500])
    print('---')