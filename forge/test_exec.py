import sys
try:
    exec(open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py').read())
    print("Exec OK")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    lines = open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py').readlines()
    if e.lineno <= len(lines):
        print(f"  Line {e.lineno}: {lines[e.lineno-1].rstrip()}")
    if e.offset:
        print(f"  Offset: {e.offset}")