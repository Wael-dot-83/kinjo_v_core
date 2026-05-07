import re
from pathlib import Path

results = []
for path in Path('templates').rglob('*.html'):
    text = path.read_text(encoding='utf-8')
    matches = re.findall(r'''_\(["']([^"']+)["']\)''', text)
    for m in matches:
        results.append(m)

unique = sorted(set(results))
for s in unique:
    print(s)
print(f'--- Total unique: {len(unique)}')
