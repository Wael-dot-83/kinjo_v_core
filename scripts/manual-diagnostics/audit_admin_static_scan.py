import re
from pathlib import Path

def run_audit():
    print("=== 1. SCANNING ADMIN TEMPLATES FOR FORMS WITHOUT CSRF ===")
    form_count = 0
    no_csrf_count = 0
    for p in Path("templates/admin").rglob("*.html"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "<form" in txt.lower():
            form_count += 1
            if "csrf_token" not in txt and "CSRF" not in txt:
                print(f"  [FORM WITHOUT CSRF] {p}")
                no_csrf_count += 1
    print(f"Total admin template forms: {form_count}, Missing CSRF: {no_csrf_count}")

    print("\n=== 2. SCANNING ADMIN JS FILES FOR RAW alert() CALLS ===")
    alert_count = 0
    for p in Path("static/js").rglob("*.js"):
        if "admin" in p.name.lower() or "audit" in p.name.lower():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(txt.splitlines()):
                if re.search(r"\balert\(", line) and "sweetalert" not in line.lower():
                    print(f"  [RAW ALERT] {p.name}:{i+1}: {line.strip()[:100]}")
                    alert_count += 1
    print(f"Total raw alert() calls found: {alert_count}")

    print("\n=== 3. SCANNING FOR MISSING ASSET REFERENCES IN ADMIN BASE & TEMPLATES ===")
    missing_assets = set()
    for p in [Path("templates/admin_base.html")] + list(Path("templates/admin").rglob("*.html")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        matches = re.findall(r'/static/[a-zA-Z0-9_\-/\.]+\.[a-zA-Z0-9]+', txt)
        for asset in matches:
            asset_clean = asset.split("?")[0]
            disk_path = Path(asset_clean.lstrip("/"))
            if not disk_path.exists():
                missing_assets.add(asset_clean)
                print(f"  [MISSING ASSET] {asset_clean} (referenced in {p.name})")

    print(f"Total missing static assets: {len(missing_assets)}")

if __name__ == "__main__":
    run_audit()
