import sys, os
sys.path.insert(0, '.')
os.environ['TESTING'] = 'true'
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'kinjo-ci-testing-secret-key-not-for-production-use-9x7z')
import main

all_flat = []

def walk(routes, prefix=''):
    for r in routes:
        cls = type(r).__name__
        p = getattr(r, 'path', None)
        methods = getattr(r, 'methods', None)
        if cls == 'APIRoute' or (hasattr(r, 'methods') and methods):
            full = prefix + (p or '')
            for m in (methods or []):
                all_flat.append((m, full))
        elif cls == '_IncludedRouter':
            # It's a Mount-like — recurse into .routes
            sub_prefix = prefix + (p or '')
            walk(getattr(r, 'routes', []), sub_prefix)
        elif hasattr(r, 'routes'):
            sub_prefix = prefix + (p or '')
            walk(r.routes, sub_prefix)

walk(main.app.routes)
print(f"Total flattened routes: {len(all_flat)}")
admin_routes = [r for r in all_flat if '/admin' in r[1]]
print(f"Admin routes found: {len(admin_routes)}")
for m, p in sorted(admin_routes)[:20]:
    print(f"  {m:6s} {p}")
non_admin = [r for r in all_flat if '/admin' not in r[1]]
print(f"Non-admin routes: {len(non_admin)}")
for m, p in sorted(non_admin)[:20]:
    print(f"  {m:6s} {p}")

# Check for duplicates
from collections import Counter
counts = Counter(all_flat)
dups = {k: v for k, v in counts.items() if v > 1}
print(f"\nDuplicate (method,path) pairs: {len(dups)}")
for (m, p), c in sorted(dups.items()):
    print(f"  {m:6s} {p}  ({c}x)")
