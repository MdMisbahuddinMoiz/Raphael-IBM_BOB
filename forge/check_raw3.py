#!/usr/bin/env python3
import json

arms = {}
with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for line in f:
        d = json.loads(line)
        arm = d.get('arm')
        arms[arm] = arms.get(arm, 0) + 1
        if arm == 'PROMPTED_AGENT':
            print(d.get('raw_response', '')[:300])
            print('---')

print("Arm counts:", arms)