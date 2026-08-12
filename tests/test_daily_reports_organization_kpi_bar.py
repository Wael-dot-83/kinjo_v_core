"""Page-level totals on the daily reports organization page.

Per-kindergarten status chips already existed, but nothing answered "how much
is missing across everything I am looking at" without scrolling the whole list.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "daily_reports_organization.html"
JS = ROOT / "static" / "js" / "admin_daily_reports_organization.js"


def test_kpi_bar_exists_and_is_labelled():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="dailyReportsKpiBar"' in html
    block = html.split('id="dailyReportsKpiBar"', 1)[1][:400]
    assert "aria-label" in block
    # Hidden until there is something to total, so an empty result does not
    # show a row of zeroes.
    assert "hidden" in block


def test_kpi_bar_is_bilingual():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "Report totals" in html
    assert "إجماليات التقارير" in html


def test_totals_reflect_the_filtered_view():
    """Totals are computed from the groups actually rendered, so they agree
    with what is on screen rather than the unfiltered response."""
    js = JS.read_text(encoding="utf-8")
    assert "renderKpiBar(groups);" in js
    order = js.index("applyClientFilters"), js.index("renderKpiBar(groups);")
    assert order[0] < order[1]


def test_totals_reuse_the_shared_status_config():
    """A status must keep the same colour and label as its per-kindergarten
    chip."""
    body = JS.read_text(encoding="utf-8").split("function renderKpiBar", 1)[1].split("\n  function ", 1)[0]
    assert "STATUS_UI_CONFIG" in body
    assert "getStatusDisplay(key)" in body
    assert "cfg.bgClass" in body


def test_empty_result_hides_the_bar():
    body = JS.read_text(encoding="utf-8").split("function renderKpiBar", 1)[1].split("\n  function ", 1)[0]
    assert "groups.length === 0" in body
    assert "bar.hidden = true" in body


def test_share_does_not_divide_by_zero():
    body = JS.read_text(encoding="utf-8").split("function renderKpiBar", 1)[1].split("\n  function ", 1)[0]
    assert "grand > 0" in body


def test_values_are_escaped_and_bidi_isolated():
    """Numbers sit inside Arabic text; without <bdi> the digits reorder."""
    body = JS.read_text(encoding="utf-8").split("function renderKpiBar", 1)[1].split("\n  function ", 1)[0]
    assert "escapeHtml(cfg.label)" in body
    assert "<bdi>" in body


def test_asset_is_cache_busted():
    """Production serves static assets immutable for a year; this script had no
    version at all, so any change to it would never reach a returning user."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'admin_daily_reports_organization.js?v=' in html
    assert 'src="/static/js/admin_daily_reports_organization.js"' not in html
