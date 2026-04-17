"""Analyze missing_endpoints.py structure - temporary script."""
import re
import collections

with open("missing_endpoints.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")

endpoints = []
for i, line in enumerate(lines, 1):
    m = re.match(r'@router\.(get|post|put|patch|delete)\s*\((.+)', line)
    if m:
        method = m.group(1).upper()
        rest = m.group(2)
        path_m = re.search(r'''["'](/[^"']*?)["']''', rest)
        tag_m = re.search(r'''tags\s*=\s*\[["']([^"']+)["']''', rest)
        path = path_m.group(1) if path_m else "?"
        tag = tag_m.group(1) if tag_m else "?"
        endpoints.append((i, method, path, tag))

by_tag = collections.defaultdict(list)
for line_no, method, path, tag in endpoints:
    by_tag[tag].append((line_no, method, path))

for tag in sorted(by_tag.keys()):
    eps = by_tag[tag]
    print(f"\n=== {tag} ({len(eps)} endpoints, lines {eps[0][0]}-{eps[-1][0]}) ===")
    for ln, m, p in eps:
        print(f"  L{ln:5d}  {m:6s} {p}")
