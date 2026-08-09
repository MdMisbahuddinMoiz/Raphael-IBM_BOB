import re

with open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py', 'r') as f:
    lines = f.readlines()

in_function = False
function_start = -1
brace_count = 0

for i, line in enumerate(lines, 1):
    if 'def _parse_structured_conclusion' in line:
        in_function = True
        function_start = i
        brace_count = 0
    elif in_function:
        if 'def ' in line and 'def _parse_structured_conclusion' not in line:
            # Check if this is a new function definition at the same indent level
            if line.startswith('def ') or line.startswith('class '):
                print(f"Function ends at line {i}")
                break
        if 'return claims' in line and 'def ' not in line and 'if' not in line and 'except' not in line:
            print(f"Found 'return claims' at line {i}: {line.strip()}")

if function_start >= 0:
    print(f"Function starts at line {function_start}")