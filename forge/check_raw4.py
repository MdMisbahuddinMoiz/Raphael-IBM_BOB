#!/usr/bin/env python3
import json

with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for line in f:
        d = json.loads(line)
        if d.get('arm') == 'PROMPTED_AGENT':
            print("Keys:", list(d.keys()))
            print("Full entry:", json.dumps(d, indent=2)[:2000])
            break