import sys, os
sys.path.insert(0, '.')
os.environ['TESTING'] = 'true'
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
import main

admin_routes = []
all_paths = []
for r in main.app.routes:
    p = getattr(r, 'path', None)
    if p:
        all_paths.append(p)
        if '/admin' in p:
            m = getattr(r, 'methods', None)
            admin_routes.append((str(m), p))

print(f'Routes containing /admin: {len(admin_routes)}')
for m, p in sorted(admin_routes):
    print(f'  {m:8s} {p}')
print(f'Total routable paths: {len(all_paths)}')
api_paths = [p for p in all_paths if p.startswith('/api')]
print(f'Paths starting with /api: {len(api_paths)}')
