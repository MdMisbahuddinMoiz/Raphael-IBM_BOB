import json
templates = set()
with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for line in f:
        d = json.loads(line)
        templates.add(d.get('template'))
print("Unique templates in holdout:")
for t in sorted(templates):
    print(f"  {t}")