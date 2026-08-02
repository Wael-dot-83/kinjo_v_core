import sys, os
sys.path.insert(0, '.')
os.environ['TESTING'] = 'true'
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'kinjo-ci-testing-secret-key-not-for-production-use-9x7z')
import main

# Print all route types
from collections import Counter
type_counts = Counter()
for r in main.app.routes:
    type_counts[type(r).__name__] += 1
print("Route types in app.routes:")
for t, c in type_counts.items():
    print(f"  {t}: {c}")

# Try to find an admin route by URL path
print()
print("Searching for /api/admin/ prefix in app.routes...")
for r in main.app.routes:
    p = getattr(r, 'path', None)
    if p and 'admin' in p.lower():
        print(f"  FOUND: {type(r).__name__} path={p}")
    # Also check nested routes in Mount objects
    if hasattr(r, 'routes'):
        for sub in r.routes:
            sp = getattr(sub, 'path', None)
            if sp:
                full_path = p + sp if p else sp
                if 'admin' in full_path.lower():
                    print(f"  FOUND (nested): {type(r).__name__} -> {type(sub).__name__} path={full_path}")

# Check app.url_path_for
print()
try:
    url = main.app.url_path_for("read_users")
    print(f"url_path_for('read_users'): {url}")
except Exception as e:
    print(f"url_path_for('read_users') failed: {e}")

# Check what's in the router itself
print()
print("Admin router route names:")
for r in main.admin_router.routes[:5]:
    print(f"  {type(r).__name__}: path={getattr(r, 'path', None)} name={getattr(r, 'name', None)}")
