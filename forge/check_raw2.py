#!/usr/bin/env python3
import json

with open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl') as f:
    for i, line in enumerate(f):
        if i >= 10:
            break
        d = json.loads(line)
        print(f"Arm: {d.get('arm')}, Template: {d.get('template')}, Seed: {d.get('seed')}")
        if d.get('arm') == 'PROMPTED_AGENT':
            print(f"  Raw response: {d.get('raw_response', '')[:300]}")
            print('---')