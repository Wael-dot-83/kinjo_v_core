"""Pagination on the daily reports organization page.

The page rendered every matching kindergarten in one accordion, so a national
view meant scrolling hundreds of sections.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "daily_reports_organization.html"
JS = ROOT / "static" / "js" / "admin_daily_reports_organization.js"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    return _js().split(f"function {name}", 1)[1].split("\n  function ", 1)[0]


def test_controls_exist_and_are_labelled():
    html = _html()
    assert 'id="dailyReportsPagination"' in html
    assert 'id="dailyReportsPager"' in html
    assert 'id="dailyReportsPerPage"' in html
    block = html.split('id="dailyReportsPagination"', 1)[1][:400]
    assert "aria-label" in block
    assert "<nav" in html.split('id="dailyReportsPagination"', 1)[0][-80:]


def test_controls_are_bilingual():
    html = _html()
    assert "Per page" in html and "لكل صفحة" in html
    js = _js()
    assert '"السابق", "Previous"' in js
    assert '"التالي", "Next"' in js


def test_pagination_runs_after_filtering_not_before():
    """Status, child/teacher search and sorting are applied client-side, so
    slicing before them would let a filter see only one page."""
    js = _js()
    assert js.index("applyClientFilters") < js.index("paginate(groups)")
    assert "const pageGroups = paginate(groups);" in js
    # The list renders the page, not the whole filtered set.
    assert "container.innerHTML = pageGroups" in js


def test_totals_stay_across_the_whole_filtered_set():
    """"12 missing" is only meaningful for everything the filters match, not
    for whichever 20 rows happen to be visible."""
    js = _js()
    assert js.index("renderKpiBar(groups);") < js.index("const pageGroups")


def test_page_is_clamped_when_filters_shrink_the_list():
    body = _fn("paginate")
    assert "state.page > pages" in body
    assert "state.page < 1" in body


def test_filters_reset_to_the_first_page():
    """Staying on page 7 after a filter that yields two pages shows nothing."""
    js = _js()
    assert js.count("state.page = 1;") >= 3      # status/sort, search, per-page


def test_range_is_announced():
    html = _html()
    block = html.split('id="dailyReportsRange"', 1)[1][:160]
    assert 'aria-live="polite"' in block
    body = _fn("renderPagination")
    assert "Showing" in body and "عرض" in body


def test_pager_is_hidden_when_there_is_nothing_to_page():
    body = _fn("renderPagination")
    assert "total === 0" in body
    assert "nav.hidden = true" in body


def test_single_page_keeps_the_range_but_drops_the_numbers():
    body = _fn("renderPagination")
    assert "pages <= 1" in body


def test_page_window_keeps_the_control_usable_at_scale():
    """Rendering 400 numbered buttons is its own usability problem."""
    body = _fn("renderPagination")
    assert "state.page - 2" in body and "state.page + 2" in body
    assert "…" in body


def test_current_page_is_exposed_to_assistive_tech():
    body = _fn("renderPagination")
    assert 'aria-current", "page"' in body
    assert "btn.disabled" in body


def test_direction_is_worded_not_chevroned():
    """A < glyph reverses meaning in RTL; the words do not."""
    body = _fn("renderPagination")
    for glyph in ("‹", "›", "«", "»", "&laquo;", "&raquo;"):
        assert glyph not in body
    assert '"السابق", "Previous"' in body


def test_page_change_respects_reduced_motion():
    body = _fn("goToPage")
    assert "prefers-reduced-motion" in body


def test_asset_version_bumped_for_the_change():
    html = _html()
    assert "admin_daily_reports_organization.js?v=1.2" in html
    assert "?v=1.1" not in html
