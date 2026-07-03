from __future__ import annotations
import sys
from collections import Counter
from fastapi.routing import Mount

sys.path.insert(0, ".")
from main import app

routes = []
for r in app.routes:
    if isinstance(r, Mount):
        continue
    if hasattr(r, "path") and hasattr(r, "methods"):
        methods = tuple(sorted(r.methods)) if r.methods else ("WS",)
        routes.append((methods, r.path))

with open("D:/Final Version/route_dump_full.txt", "w", encoding="utf-8") as f:
    for methods, path in sorted(routes):
        f.write(f"{methods} {path}\n")

with open("D:/Final Version/route_duplicates.txt", "w", encoding="utf-8") as f:
    c = Counter(routes)
    dups = {(m, p): cnt for (m, p), cnt in c.items() if cnt > 1}
    for (m, p), cnt in dups.items():
        f.write(f"DUPLICATE: {m} {p} ({cnt}x)\n")
    if not dups:
        f.write("No duplicate (method, path) pairs found.\n")

with open("D:/Final Version/route_admin_namespace.txt", "w", encoding="utf-8") as f:
    prefixes = ("/api/admin", "/admin/users", "/admin/heat-map", "/admin/messages", "/admin/profile", "/admin/import", "/admin/charts", "/admin/dashboard", "/admin/analytics", "/admin/reports", "/admin/governance", "/admin/classification", "/admin/safety", "/admin/kpi", "/admin/observability", "/admin/audit", "/admin/alerts", "/admin/impersonate", "/admin/daily", "/admin/heat", "/admin/kg", "/admin/contact", "/admin/options", "/admin/performance", "/admin/kindergartens", "/admin/settings", "/admin/message")
    seen = set()
    for methods, path in sorted(routes):
        if path.startswith(prefixes) and path not in seen:
            seen.add(path)
            f.write(f"{methods} {path}\n")
