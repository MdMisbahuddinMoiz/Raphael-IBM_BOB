import ast
import sys

try:
    with open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py', 'r') as f:
        content = f.read()
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    lines = content.splitlines()
    if e.lineno <= len(lines):
        print(f"  Line {e.lineno}: {lines[e.lineno-1].rstrip()}")
    if e.offset:
        print(f"  Offset: {e.offset}")
except Exception as e:
    print(f"Error: {e}")