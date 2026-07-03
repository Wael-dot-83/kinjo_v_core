import sys
sys.path.insert(0, ".")

with open("D:/Final Version/templates/admin_base.html", "r", encoding="utf-8") as f:
    content = f.read()

with open("D:/Final Version/base_includes_audit.txt", "w", encoding="utf-8") as out:
    out.write("=== CSS INCLUDES ===\n")
    import re
    css = re.findall(r'<link[^>]+href="([^"]+\.css[^"]*)"[^>]*>', content)
    for c in css:
        out.write(f"  {c}\n")
    
    out.write("\n=== JS INCLUDES ===\n")
    js = re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"[^>]*>', content)
    for j in js:
        out.write(f"  {j}\n")
    
    out.write("\n=== DUPLICATE CHECK ===\n")
    from collections import Counter
    cc = Counter(css)
    jj = Counter(js)
    dup = False
    for item, cnt in cc.items():
        if cnt > 1:
            out.write(f"DUPLICATE CSS: {item} ({cnt}x)\n")
            dup = True
    for item, cnt in jj.items():
        if cnt > 1:
            out.write(f"DUPLICATE JS: {item} ({cnt}x)\n")
            dup = True
    if not dup:
        out.write("No duplicate CSS or JS includes found in admin_base.html\n")
