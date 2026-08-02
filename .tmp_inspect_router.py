import sys, os
sys.path.insert(0, '.')
os.environ['TESTING'] = 'true'
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'kinjo-ci-testing-secret-key-not-for-production-use-9x7z')
import main

# Inspect _IncludedRouter objects
for r in main.app.routes:
    cls = type(r).__name__
    if cls == '_IncludedRouter':
        attrs = [a for a in dir(r) if not a.startswith('_') and not callable(getattr(r, a, None))]
        print(f'_IncludedRouter: path={getattr(r, "path", "?")}, attrs={attrs[:20]}')
        print(f'  repr: {repr(r)[:300]}')
        # Try to access routes
        routes = getattr(r, 'routes', None)
        print(f'  routes attr: {len(routes) if routes else "None"}')
        if routes:
            for sub in routes[:3]:
                print(f'    sub: {type(sub).__name__} path={getattr(sub, "path", "?")}')
        break

# Try building the app with TestClient
from fastapi.testclient import TestClient
client = TestClient(main.app)

# Check if admin routes are accessible
from starlette.routing import Route
try:
    # Build the routes table by accessing the app's router
    # In FastAPI, the routes are lazily resolved
    routes = list(main.app.routes)
    # Check all route types recursively
    def collect_routes(routes):
        result = []
        for r in routes:
            if hasattr(r, 'path') and hasattr(r, 'methods'):
                methods = r.methods or set()
                for m in methods:
                    result.append((m, r.path))
            if hasattr(r, 'routes'):
                result.extend(collect_routes(r.routes))
        return result

    all_routes = collect_routes(main.app.routes)
    admin_count = sum(1 for m, p in all_routes if 'admin' in p)
    print(f'\nAfter TestClient init - Total routes: {len(all_routes)}')
    print(f'After TestClient init - Admin routes: {admin_count}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
