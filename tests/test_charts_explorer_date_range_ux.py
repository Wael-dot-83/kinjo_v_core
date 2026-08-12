"""Date-range UX and chart accessibility on the charts explorer.

The page already shipped presets, a data-table fallback, breadcrumbs and a
progress indicator. These cover the gaps that remained: the two presets the
spec calls for, remembering the last range, stating the range in words, and
giving the chart region an accessible name.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_last_7_and_30_day_presets_exist():
    """"Last 30 days" is the documented default and neither preset existed."""
    html = _html()
    for preset in ("last_7", "last_30"):
        assert f'data-preset="{preset}"' in html
        assert f"applyDatePreset('{preset}')" in html
    body = html.split("function applyDatePreset", 1)[1]
    assert "case 'last_7':" in body
    assert "case 'last_30':" in body


def test_presets_are_bilingual():
    html = _html()
    assert "Last 7 Days" in html and "آخر 7 أيام" in html
    assert "Last 30 Days" in html and "آخر 30 يومًا" in html


def test_range_is_remembered_across_visits():
    html = _html()
    assert "kinjo.charts.dateRange" in html
    assert "function rememberDateRange" in html
    assert "function restoreDateRange" in html
    # Storage can throw in private mode; that must not break the page.
    restore = html.split("function restoreDateRange", 1)[1].split("\n  function ", 1)[0]
    assert "catch" in restore


def test_explicit_url_range_beats_remembered_one():
    """A shared link carries a deliberate range; storage must not overwrite it."""
    restore = _html().split("function restoreDateRange", 1)[1].split("\n  function ", 1)[0]
    assert "date_from" in restore and "date_to" in restore
    assert "return false" in restore


def test_default_is_last_30_days_when_nothing_saved():
    restore = _html().split("function restoreDateRange", 1)[1].split("\n  function ", 1)[0]
    assert "applyDatePreset('last_30')" in restore


def test_summary_states_the_range_in_words():
    html = _html()
    assert 'id="dateRangeSummary"' in html
    assert "function updateDateRangeSummary" in html
    summary = html.split("function updateDateRangeSummary", 1)[1].split("\n  function ", 1)[0]
    # Jordan's locale, never the Gulf's Hijri one. Comments are stripped because
    # the code documents the rejected 'ar-SA' value by name.
    code = "\n".join(
        line for line in summary.splitlines() if not line.strip().startswith("//")
    )
    assert "ar-JO" in code and "en-JO" in code
    assert "ar-SA" not in code
    assert "المعروض" in summary and "Showing" in summary


def test_summary_is_announced_to_screen_readers():
    html = _html()
    block = html.split('id="dateRangeSummary"', 1)[1][:200]
    assert 'aria-live="polite"' in block


def test_chart_region_has_an_accessible_name():
    """The rendered chart was an unnamed div; assistive tech announced nothing."""
    html = _html()
    block = html.split('id="chartOutput"', 1)[1][:300]
    assert 'role="img"' in block
    assert "aria-label" in block
    assert "function describeChartForScreenReaders" in html
    # The name must be refreshed once the chart's title is known.
    assert "describeChartForScreenReaders();" in html.split("function injectChart", 1)[1]


def test_manual_edit_clears_the_preset_highlight():
    """Typing a custom range must not keep a preset chip looking selected."""
    html = _html()
    assert "updatePresetHighlight('')" in html
