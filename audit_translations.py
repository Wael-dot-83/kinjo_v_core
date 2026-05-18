import re
from pathlib import Path

english_pattern = re.compile(r'[a-zA-Z]{4,}')
jinja_var = re.compile(r'\{\{.*?\}\}', re.DOTALL)
jinja_tag = re.compile(r'\{%.*?%\}', re.DOTALL)
html_tag  = re.compile(r'<[^>]+>')
css_js    = re.compile(r'[{}:;@#]|\bfunction\b|\bvar\b|\bconst\b|\blet\b|://|\.js|\.css')

results = {}
for path in Path('templates').rglob('*.html'):
    text = path.read_text(encoding='utf-8')
    cleaned = jinja_var.sub('', text)
    cleaned = jinja_tag.sub('', cleaned)
    cleaned = html_tag.sub(' ', cleaned)
    lines = cleaned.split('\n')
    found = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if css_js.search(s):
            continue
        if english_pattern.search(s):
            found.append(f'  L{i+1}: {s[:120]}')
    if found:
        results[path.name] = found

for fname, lines in sorted(results.items()):
    print(f'\n=== {fname} ===')
    for l in lines[:20]:
        print(l)
