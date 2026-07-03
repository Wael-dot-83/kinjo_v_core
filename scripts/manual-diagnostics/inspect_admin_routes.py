import sys
sys.path.insert(0, ".")
from main import app
from fastapi.routing import Mount

print("Total app.routes:", len(app.routes))

with open("D:/Final Version/all_routes.txt", "w", encoding="utf-8") as f:
    f.write(f"Total app.routes: {len(app.routes)}\n\n")
    for r in app.routes:
        if isinstance(r, Mount):
            f.write(f"MOUNT {r.path} ({len(r.routes) if hasattr(r, 'routes') else 0} routes)\n")
            for sub in r.routes:
                if hasattr(sub, 'path') and hasattr(sub, 'methods'):
                    methods = tuple(sorted(sub.methods)) if sub.methods else ('WS',)
                    f.write(f"  {methods} {r.path}{sub.path}\n")
        elif hasattr(r, 'path'):
            methods = tuple(sorted(r.methods)) if hasattr(r, 'methods') and r.methods else ('?',)
            f.write(f"{methods} {r.path}\n")

with open("D:/Final Version/admin_routes.txt", "w", encoding="utf-8") as f:
    f.write("Admin-related routes:\n\n")
    for r in app.routes:
        if isinstance(r, Mount):
            for sub in r.routes:
                if hasattr(sub, 'path') and '/admin' in sub.path:
                    methods = tuple(sorted(sub.methods)) if hasattr(sub, 'methods') and sub.methods else ('WS',)
                    f.write(f"{methods} {r.path}{sub.path}\n")
        elif hasattr(r, 'path') and '/admin' in r.path:
            methods = tuple(sorted(r.methods)) if hasattr(r, 'methods') and r.methods else ('?',)
            f.write(f"{methods} {r.path}\n")
