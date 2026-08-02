import sys, os
sys.path.insert(0, '.')
os.environ['TESTING'] = 'true'
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'kinjo-ci-testing-secret-key-not-for-production-use-9x7z')
import main

print(f"app.routes count: {len(main.app.routes)}")
print(f"admin_router routes: {len(main.admin_router.routes)}")
print()

# Check if admin routes are in app.routes by looking for paths containing common admin patterns
admin_paths_in_app = []
for r in main.app.routes:
    p = getattr(r, 'path', None)
    if p:
        methods = getattr(r, 'methods', None)
        methods_str = str(sorted(methods)) if methods else '*'
        if any(x in p for x in ['/users', '/kindergartens', '/audit', '/dashboard', '/backup', '/alerts', '/classification', '/analytics']):
            admin_paths_in_app.append(f'{methods_str:30s} {p}')

print(f"Admin-looking paths in app.routes: {len(admin_paths_in_app)}")
for x in sorted(admin_paths_in_app)[:20]:
    print(f'  {x}')

# Also check app.include_router calls
print()
print("Router prefixes registered:")
for r in main.app.routes:
    p = getattr(r, 'path', None)
    if p:
        print(f'  {p}')
