"""Static regression guards for the manager dashboard template.

These lock in three bugs that made /dashboard hang on "جارٍ تحميل لوحة التحكم…":

1. The inline loader lived in `{% block scripts %}` while manager_base.html only
   renders `{% block extra_scripts %}`, so Jinja silently dropped the script and
   the fetch never fired.
2. An earlier USWDS->Bootstrap migration corrupted card classes into
   non-existent `col-12__container/__body/...` tokens, so cards rendered
   unstyled.
3. The loading element carried `d-flex` (display:flex !important), which
   overrode the `hidden` attribute the JS toggles, so the spinner stayed
   visible even after the data loaded.
"""
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
MANAGER_TEMPLATES = sorted((TEMPLATES / "manager").glob("*.html"))


def test_no_inline_event_handlers_in_manager_templates():
    """F1 — no inline on* event handlers in manager templates. They are an XSS
    surface (user data interpolated into an executable attribute) and block CSP
    from dropping 'unsafe-inline'. Handlers must be delegated listeners bound to
    data-* attributes instead."""
    # match on<event>= as an HTML attribute, not substrings like "button="
    handler = re.compile(r'\son(click|change|input|submit|mouseover|mouseout|'
                         r'keyup|keydown|load|focus|blur|error)\s*=')
    offenders = []
    for t in MANAGER_TEMPLATES:
        for i, line in enumerate(t.read_text(encoding="utf-8").splitlines(), 1):
            if handler.search(line):
                offenders.append(f"{t.name}:{i}: {line.strip()[:80]}")
    assert not offenders, "inline event handlers found:\n" + "\n".join(offenders)


def test_no_localstorage_token_or_bearer_in_manager_templates():
    """F2 — manager pages must authenticate via the httpOnly session cookie, not
    a JWT read from localStorage/sessionStorage or injected as a Bearer header."""
    bad = re.compile(r"(localStorage|sessionStorage)\.getItem\(\s*['\"]kinjo_token"
                     r"|Authorization['\"]?\s*[:=].*Bearer|Bearer \$\{")
    offenders = []
    for t in MANAGER_TEMPLATES:
        for i, line in enumerate(t.read_text(encoding="utf-8").splitlines(), 1):
            if bad.search(line):
                offenders.append(f"{t.name}:{i}: {line.strip()[:80]}")
    assert not offenders, "localStorage/Bearer auth found in manager templates:\n" + "\n".join(offenders)


def test_dashboard_script_uses_block_rendered_by_base():
    base = (TEMPLATES / "manager_base.html").read_text(encoding="utf-8")
    dash = (TEMPLATES / "manager" / "dashboard.html").read_text(encoding="utf-8")
    # base must render the block the dashboard defines its script in
    assert "{% block extra_scripts %}" in base
    assert "{% block extra_scripts %}" in dash
    assert "loadDashboard" in dash
    # the old, silently-dropped block name must not come back
    assert "{% block scripts %}" not in dash


def test_manager_base_renders_both_script_blocks():
    """manager_base.html must render both `extra_scripts` and `extra_js` so a
    child page's inline JS is never silently dropped (the bug that made several
    manager pages non-functional)."""
    base = (TEMPLATES / "manager_base.html").read_text(encoding="utf-8")
    assert "{% block extra_scripts %}" in base
    assert "{% block extra_js %}" in base


def test_every_manager_child_script_block_is_rendered_by_base():
    """Every template extending manager_base.html must put its JS in a block the
    base actually renders — otherwise the script is discarded and the page can't
    fetch its data."""
    rendered = {"extra_scripts", "extra_js"}  # what manager_base.html emits
    offenders = []
    for t in MANAGER_TEMPLATES:
        text = t.read_text(encoding="utf-8")
        if "manager_base.html" not in text:
            continue
        used = set(re.findall(r"\{%\s*block\s+(scripts|extra_scripts|extra_js|js)\s*%\}", text))
        stray = used - rendered
        if stray:
            offenders.append(f"{t.name}: {sorted(stray)}")
    assert not offenders, f"manager pages using a non-rendered script block: {offenders}"


def test_no_corrupted_migration_card_classes():
    corrupted = re.compile(
        r"col-12__|bg-success-subtleer|bg-gold-lighter|border-gold-light|"
        r"text-gold-dark|alert alert-heading"
    )
    offenders = [t.name for t in MANAGER_TEMPLATES if corrupted.search(t.read_text(encoding="utf-8"))]
    assert not offenders, f"corrupted migration classes still present in: {offenders}"


def test_loading_element_has_no_display_utility():
    dash = (TEMPLATES / "manager" / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r'id="dashLoading"[^>]*class="([^"]*)"', dash)
    assert m, "dashLoading element not found"
    classes = m.group(1).split()
    # a d-* display utility would be `display:… !important` and override `hidden`
    bad = [c for c in classes if re.fullmatch(r"d-(flex|grid|inline|inline-block|block|table)", c)]
    assert not bad, f"dashLoading must not carry a display utility that overrides [hidden]: {bad}"
