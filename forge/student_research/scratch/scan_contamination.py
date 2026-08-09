import json, os, glob
from collections import Counter

def keys_of(path):
    keys = Counter()
    try:
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if 'episode_id' in d:
                    keys[d.get('episode_id')] += 1
                elif 'event_id' in d:
                    keys[d.get('event_id')] += 1
    except Exception as e:
        return None
    return keys

contaminated = []
scanned = 0
for d in sorted(glob.glob('evaluations/campaign/dev_runs/raw/*')):
    for fn in ('episodes.jsonl', 'events.jsonl'):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            scanned += 1
            k = keys_of(p)
            if k is None:
                continue
            dups = {kk: v for kk, v in k.items() if v > 1}
            if dups:
                contaminated.append((d, fn, len(k), len(dups)))

print('dirs scanned:', len(glob.glob('evaluations/campaign/dev_runs/raw/*')))
print('jsonl files scanned:', scanned)
print('contaminated files:', len(contaminated))
for c in contaminated:
    print(c)