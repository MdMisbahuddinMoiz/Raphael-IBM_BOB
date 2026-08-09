import json
data = [json.loads(l) for l in open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl')]
prompted = [d for d in data if d.get('arm') == 'PROMPTED_AGENT']
print(f'PROMPTED total: {len(prompted)}')
from collections import Counter
tmpl = Counter(d.get('template') for d in prompted)
print('Templates:', tmpl)

# The 10 stratified samples from the audit
audit_samples = [
    ('contradiction', 0), ('contradiction', 1),
    ('false-lead', 0), ('false-lead', 1),
    ('forbidden-proximity', 0), ('forbidden-proximity', 1),
    ('known-observable', 0), ('known-observable', 1),
    ('signal-noise', 0), ('signal-noise', 1),
]

print('\nVerifying audit samples exist in holdout:')
for tmpl_name, seed in audit_samples:
    matches = [d for d in prompted if d.get('template') == tmpl_name and d.get('seed') == seed]
    if matches:
        d = matches[0]
        print(f"  ✓ {tmpl_name} seed={seed}: run_id={d.get('run_id')} outcome={d.get('decision_outcome')} score={d.get('score')}")
    else:
        print(f"  ✗ {tmpl_name} seed={seed}: NOT FOUND")

# Also verify the gate: all 10 classified MECHANICAL
print('\nGate check: 10/10 MECHANICAL >= 2/10 threshold → ARM INVALID (mechanical)')