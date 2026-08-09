import json
with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for i, line in enumerate(f):
        if i >= 5:
            break
        d = json.loads(line)
        print(d.get('template'))