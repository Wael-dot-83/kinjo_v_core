import re

with open('templates/communication/messages.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix inline handlers
content = content.replace('onclick="filterMsgs(\'all\', this)"', 'class="btn btn-outline-secondary js-filter-msgs active" data-filter="all"')
content = content.replace('onclick="filterMsgs(\'direct\', this)"', 'class="btn btn-outline-secondary js-filter-msgs" data-filter="direct"')
content = content.replace('onclick="filterMsgs(\'announcement\', this)"', 'class="btn btn-outline-secondary js-filter-msgs" data-filter="announcement"')

# Remove duplicated classes where we just injected `class=` into something that already had `class=`
content = re.sub(r'class="btn btn-outline-secondary(?: active)?"\s+class="btn btn-outline-secondary js-filter-msgs(?: active)?"', r'class="btn btn-outline-secondary js-filter-msgs\g<1>"', content)

# Fix JS listener
js_addition = """
        document.querySelectorAll('.js-filter-msgs').forEach(btn => {
            btn.addEventListener('click', e => {
                filterMsgs(e.currentTarget.dataset.filter, e.currentTarget);
            });
        });
"""
if 'document.addEventListener(\'DOMContentLoaded\', () => {' in content:
    content = content.replace('document.addEventListener(\'DOMContentLoaded\', () => {', 'document.addEventListener(\'DOMContentLoaded\', () => {' + js_addition)

# Replace alert(...) with showToast(..., 'error') or 'warning'
# Find alert(T(...))
content = re.sub(r'alert\((T\([^\)]+\))\)', r"showToast(\1, 'warning')", content)
content = re.sub(r'alert\((err\.error\?\.message \|\| err\.detail \|\| T\([^\)]+\))\)', r"showToast(\1, 'error')", content)

with open('templates/communication/messages.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
