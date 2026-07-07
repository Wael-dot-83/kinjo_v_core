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


def test_dashboard_script_uses_block_rendered_by_base():
    base = (TEMPLATES / "manager_base.html").read_text(encoding="utf-8")
    dash = (TEMPLATES / "manager" / "dashboard.html").read_text(encoding="utf-8")
    # base must render the block the dashboard defines its script in
    assert "{% block extra_scripts %}" in base
    assert "{% block extra_scripts %}" in dash
    assert "loadDashboard" in dash
    # the old, silently-dropped block name must not come back
    assert "{% block scripts %}" not in dash


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
