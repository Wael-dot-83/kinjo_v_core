import sys
sys.path.insert(0, ".")
from main import app
from fastapi.routing import Mount

print("Total app.routes:", len(app.routes))
mounts = [r for r in app.routes if isinstance(r, Mount)]
print("Mount count:", len(mounts))
for m in mounts:
    print(f"  Mount path={m.path} routes={len(m.routes) if hasattr(m, 'routes') else '?'}")

other = [r for r in app.routes if not isinstance(r, Mount)]
print("Non-Mount count:", len(other))
for r in other:
    if hasattr(r, 'path'):
        print(f"  {r.path} methods={getattr(r, 'methods', '?')}")
