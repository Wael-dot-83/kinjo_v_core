import sys, re
sys.path.insert(0, ".")
from admin_endpoints import router

routes = []
for r in router.routes:
    if hasattr(r, 'path') and hasattr(r, 'methods') and r.methods:
        methods = tuple(sorted(r.methods))
        path = r.path
        routes.append((methods, path))

from collections import Counter
c = Counter(routes)

with open("D:/Final Version/admin_endpoint_routes.txt", "w", encoding="utf-8") as f:
    f.write(f"Total routes on admin_endpoints.router: {len(routes)}\n")
    dups = {k: v for k, v in c.items() if v > 1}
    if dups:
        f.write(f"\nDuplicates:\n")
        for (m, p), cnt in sorted(dups.items()):
            f.write(f"  {cnt}x {m} {p}\n")
    else:
        f.write("\nNo duplicates.\n")
    f.write(f"\nAll routes:\n")
    for m, p in sorted(routes):
        f.write(f"  {m} {p}\n")
