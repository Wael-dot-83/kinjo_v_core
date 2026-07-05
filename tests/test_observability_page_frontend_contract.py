from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "observability_dashboard.html"
JS = ROOT / "static" / "js" / "admin_observability.js"


def test_script_block_matches_a_real_parent_block():
    """The page used {% block extra_js %}, but admin_base.html only ever
    declares {% block extra_scripts %} -- Jinja silently discards a child
    block the parent doesn't declare, so admin_observability.js was NEVER
    emitted in the rendered HTML at all. Every tile, chart, and table on
    this dashboard was permanently stuck in its static loading/placeholder
    state with zero JS execution."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block extra_js %}" not in html
    assert "{% block extra_scripts %}" in html

    base = (ROOT / "templates" / "admin_base.html").read_text(encoding="utf-8")
    assert "{% block extra_scripts %}" in base


def test_no_fictitious_admin_text_classes():
    """admin-text-muted/primary/warning/success/info were used ~24 times
    across the page but never defined anywhere in static/css/*.css --
    every status label and colored status icon rendered unstyled."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "admin-text-" not in html
    assert 'class="text-muted' in html


def test_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 3


def test_js_fallback_table_has_caption_and_scope():
    js = JS.read_text(encoding="utf-8")
    assert "caption class='visually-hidden'" in js
    assert "th scope='col'" in js


def test_data_quality_badge_uses_explicit_status_list_not_substring_match():
    """The badge classifier checked whether row.value contained substrings
    like "good"/"unique"/"valid"/"consistent" -- but freshness.status is
    one of fresh/stale/warning/critical/no_data (none of which match), and
    completeness's value is a bare percentage string with no status word
    at all. Both rows were permanently misclassified as "Warning"
    regardless of their real, even perfect, status."""
    js = JS.read_text(encoding="utf-8")
    assert "GOOD_STATUSES" in js
    assert "isGoodStatus" in js
    assert 'indexOf("good") >= 0' not in js
