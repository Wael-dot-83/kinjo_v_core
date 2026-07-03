import sys
sys.path.insert(0, ".")
from main import app

print(f"Total app.routes: {len(app.routes)}")

with open("D:/Final Version/all_routes_full.txt", "w", encoding="utf-8") as f:
    def dump_route(prefix, r, indent=""):
        if hasattr(r, 'path') and hasattr(r, 'methods'):
            methods = tuple(sorted(r.methods)) if r.methods else ("WS",)
            f.write(f"{indent}{methods} {prefix}{r.path}\n")
        if hasattr(r, 'routes'):
            for sub in r.routes:
                dump_route(prefix + r.path if hasattr(r, 'path') else prefix, sub, indent + "  ")
    
    for r in app.routes:
        if hasattr(r, 'path'):
            dump_route("", r)
        elif hasattr(r, 'routes'):
            for sub in r.routes:
                dump_route("", sub)

print("Admin routes:")
with open("D:/Final Version/admin_namespace_routes.txt", "w", encoding="utf-8") as f:
    admin_paths = []
    def collect_admin(prefix, r):
        if hasattr(r, 'path') and hasattr(r, 'methods'):
            path = prefix + r.path
            if '/admin' in path:
                methods = tuple(sorted(r.methods)) if r.methods else ("WS",)
                admin_paths.append((methods, path))
                f.write(f"{methods} {path}\n")
        if hasattr(r, 'routes'):
            for sub in r.routes:
                collect_admin(prefix + r.path if hasattr(r, 'path') else prefix, sub)
    
    for r in app.routes:
        if hasattr(r, 'routes'):
            for sub in r.routes:
                collect_admin("", sub)
    
    print(f"Found {len(admin_paths)} admin routes")

print("Done")
