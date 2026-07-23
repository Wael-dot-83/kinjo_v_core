import re
from pathlib import Path

def add_csrf():
    count = 0
    for p in Path("templates/admin").rglob("*.html"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "<form" in txt.lower() and 'name="csrf_token"' not in txt and "name='csrf_token'" not in txt:
            new_txt = re.sub(
                r'(<form[^>]*>)',
                r'\1\n  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">',
                txt,
                count=1,
                flags=re.IGNORECASE
            )
            p.write_text(new_txt, encoding="utf-8")
            print(f"Added CSRF token input to: {p}")
            count += 1
    print(f"Total admin templates updated: {count}")

if __name__ == "__main__":
    add_csrf()
