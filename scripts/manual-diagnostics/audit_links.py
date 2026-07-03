import sys, re
sys.path.insert(0, ".")

# Load all valid routes
from main import app
from collections import defaultdict

valid_routes = set()
for r in app.routes:
    tname = type(r).__name__
    if tname == "_IncludedRouter":
        ctx = getattr(r, 'include_context', None)
        if ctx:
            router = getattr(ctx, 'included_router', None)
            prefix = getattr(ctx, 'prefix', '')
            if router and hasattr(router, 'routes'):
                for sub in router.routes:
                    if hasattr(sub, 'path') and hasattr(sub, 'methods') and sub.methods:
                        valid_routes.add(prefix + sub.path)
    elif hasattr(r, 'path') and hasattr(r, 'methods') and r.methods:
        valid_routes.add(r.path)

# Also add known frontend routes not in _IncludedRouter? They should be there via frontend_router.

# Find all internal links in templates
import os
template_dir = "D:/Final Version/templates"
patterns = [
    r'<a\s+[^>]*href=["\'](/admin[^"\']*)["\']',
    r'<a\s+[^>]*href=["\'](/api/admin[^"\']*)["\']',
]

issues = []
with open("D:/Final Version/link_audit.txt", "w", encoding="utf-8") as f:
    for root, dirs, files in os.walk(template_dir):
        for filename in files:
            if filename.endswith(".html"):
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, template_dir)
                with open(filepath, "r", encoding="utf-8") as tf:
                    content = tf.read()
                for pat in patterns:
                    matches = re.findall(pat, content, re.IGNORECASE)
                    for path in matches:
                        # Normalize: remove query strings and template vars
                        base = path.split('?')[0].split('#')[0]
                        if '$' in base or '{' in base:
                            continue  # template variables, skip check
                        if base not in valid_routes:
                            # Try with just prefix match
                            found = any(vr.startswith(base) or base.startswith(vr) for vr in valid_routes)
                            if not found:
                                line_num = content[:content.find(path)].count(chr(10)) + 1
                                msg = f"{relpath}:{line_num} => {base} (NOT FOUND in routes)"
                                issues.append(msg)
                                f.write(msg + chr(10))
    if not issues:
        f.write("All internal admin links appear to point to registered routes.\n")

print(f"Found {len(issues)} link issues")
