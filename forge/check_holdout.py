import json
data = [json.loads(l) for l in open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl')]
print('Total rows:', len(data))
arms = set(d.get('arm') for d in data)
print('Arms:', arms)
families = set(d.get('family') for d in data)
print('Families:', families)
prompted = [d for d in data if d.get('arm') == 'PROMPTED_AGENT']
print('PROMPTED rows:', len(prompted))
seeds = set(d.get('seed') for d in prompted)
print('Unique seeds:', len(seeds))
from collections import Counter
fam_counts = Counter(d.get('family') for d in prompted)
print('Per family:', fam_counts)

# Show sample of PROMPTED runs
print('\nSample PROMPTED runs (first 3):')
for d in prompted[:3]:
    print(f"  family={d.get('family')} seed={d.get('seed')} outcome={d.get('decision_outcome')} score={d.get('score')}")