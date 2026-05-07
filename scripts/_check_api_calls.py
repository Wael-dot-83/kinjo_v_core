import re, os

api_calls = set()
template_dir = 'templates'

for root, dirs, files in os.walk(template_dir):
    for fn in files:
        if not fn.endswith('.html'):
            continue
        path = os.path.join(root, fn)
        content = open(path, encoding='utf-8', errors='ignore').read()
        for line in content.splitlines():
            if 'fetch(' not in line:
                continue
            for m in re.findall(r'(/api/[a-zA-Z0-9_/\-{}]+)', line):
                api_calls.add(m)

for c in sorted(api_calls):
    print(c)
