import re

with open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py', 'r') as f:
    content = f.read()

# Find the _parse_structured_conclusion function
start = content.find('def _parse_structured_conclusion')
if start >= 0:
    # Find the next class definition or function definition after this
    end = content.find('\nclass ', start + 1)
    if end < 0:
        end = content.find('\ndef ', start + 1)
    if end < 0:
        end = len(content)
    func_content = content[start:end]
    
    # Find return statements in this function
    lines = func_content.split('\n')
    for i, line in enumerate(lines):
        if line.strip() == 'return claims':
            print(f'Line in function: {i}')
            print(f'Context: {lines[max(0,i-2):i+2]}')