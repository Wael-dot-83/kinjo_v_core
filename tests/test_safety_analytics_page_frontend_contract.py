from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "safety_analytics.html"


def test_tables_have_caption_and_column_scope():
    """Both data tables (Incidents by Kindergarten: 3 columns, Children
    with Repeated Incidents: 4 columns) had no <caption> and no
    scope="col" on any header cell."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count('<caption class="visually-hidden">') == 2
    assert html.count('scope="col"') == 7


def test_mini_bar_track_uses_defined_css_variable():
    """--kinjo-border was never defined anywhere in static/css/*.css (only
    --kinjo-border-color and --kinjo-border-light exist), so the mini-bar
    track background silently resolved to transparent."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "var(--kinjo-border)" not in html
    assert "var(--kinjo-border-color)" in html
