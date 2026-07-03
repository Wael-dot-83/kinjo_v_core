import sys, os, re
sys.path.insert(0, ".")

template_dir = "D:/Final Version/templates"
static_dir = "D:/Final Version/static"

# Check admin templates for fetch without CSRF
issues = []

with open("D:/Final Version/csrf_audit.txt", "w", encoding="utf-8") as f:
    for root, dirs, files in os.walk(template_dir):
        for filename in files:
            if filename.endswith(".html"):
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, template_dir)
                if not relpath.startswith("admin/") and relpath not in ("admin_base.html", "admin_base_premium.html", "admin_dashboard.html"):
                    continue
                with open(filepath, "r", encoding="utf-8") as tf:
                    content = tf.read()
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    if 'fetch(' in line or 'XMLHttpRequest' in line or '.ajax(' in line:
                        has_csrf = 'csrf' in line.lower() or 'CSRF' in line or 'X-CSRF-Token' in line or 'X-Requested-With' in line
                        has_meta = 'meta[name="csrf-token"]' in line
                        if not has_csrf and not has_meta and 'method:' in line.lower():
                            issues.append(f"{relpath}:{i} => fetch/XMLHttpRequest without visible CSRF: {line.strip()[:120]}")
    
    # Check JS files
    for root, dirs, files in os.walk(static_dir):
        for filename in files:
            if filename.endswith(".js"):
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, static_dir)
                if not relpath.startswith("js/admin_"):
                    continue
                with open(filepath, "r", encoding="utf-8") as tf:
                    content = tf.read()
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    if ('fetch(' in line or 'XMLHttpRequest' in line or '.ajax(' in line) and 'method:' in line.lower():
                        has_csrf = 'csrf' in line.lower() or 'CSRF' in line or 'X-CSRF-Token' in line or 'X-Requested-With' in line
                        if not has_csrf:
                            issues.append(f"static/{relpath}:{i} => fetch without visible CSRF: {line.strip()[:120]}")
    
    for issue in issues:
        f.write(issue + chr(10))
    if not issues:
        f.write("No obvious missing CSRF tokens found on state-changing fetch calls.\n")

print(f"Found {len(issues)} CSRF audit items")
