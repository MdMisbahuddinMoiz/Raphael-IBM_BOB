#!/usr/bin/env python3
import json

with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for i, line in enumerate(f):
        if i >= 3:
            break
        d = json.loads(line)
        if d.get('arm') == 'PROMPTED_AGENT':
            print(d.get('raw_response', '')[:300])
            print('---')