import re
content = open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py').read()
matches = list(re.finditer(r'"""', content))
print('Found', len(matches), 'triple quotes')
for i, m in enumerate(matches):
    # Show context around each triple quote
    start = max(0, m.start() - 30)
    end = min(len(content), m.end() + 30)
    context = content[start:m.start()] + '>>>' + content[m.start():m.end()] + '<<<' + content[m.end():end]
    print(f'{i}: Pos {m.start()} - Context: ...{context}...')