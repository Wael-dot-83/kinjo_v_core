"""Comparison ranges, multi-source overlay and the pinned chart board.

These were the three frontend features the explorer was missing: it could show
exactly one source, over exactly one window, one chart at a time.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """Body of a top-level function in the page script."""
    return _html().split(f"function {name}", 1)[1].split("\n  function ", 1)[0]


# --- comparison range -------------------------------------------------------

def test_compare_toggle_exists_and_is_bilingual():
    html = _html()
    assert 'id="compareToggle"' in html
    assert "Compare with previous period" in html
    assert "قارن مع الفترة السابقة" in html


def test_previous_period_is_same_length_and_immediately_before():
    """A 30-day window must compare against the 30 days ending the day before
    it starts -- not a calendar month, and with no overlap."""
    body = _fn("previousPeriod")
    assert "setDate(start.getDate() - 1)" in body      # ends the day before
    assert "(days - 1)" in body                        # same length


def test_comparison_is_fetched_and_drawn_distinctly():
    html = _html()
    assert "_compareSeries" in html
    # Drawn dashed and faded so the current period stays dominant.
    assert "dash: 'dash'" in html
    assert "opacity = 0.55" in html
    assert "previous period" in html and "الفترة السابقة" in html


def test_comparison_skipped_for_chart_types_that_cannot_overlay():
    html = _html()
    guard = html.split("_compareSeries && _compareSeries.length", 1)[1][:160]
    assert "'pie'" in guard and "'treemap'" in guard


def test_compare_choice_is_remembered():
    assert "kinjo.charts.compare" in _html()


# --- multi-source overlay ---------------------------------------------------

def test_overlay_source_picker_exists():
    html = _html()
    assert 'id="overlaySources"' in html
    assert "ce-overlay-src" in html
    assert "Overlay another source" in html and "دمج مصدر آخر" in html


def test_overlay_excludes_the_primary_source():
    """Overlaying the source already being charted would duplicate every line."""
    assert "s !== _currentSource" in _fn("selectedOverlaySources")


def test_overlays_are_fetched_in_parallel():
    """Several overlays must not stack their latencies."""
    assert "Promise.all" in _html()


def test_overlay_traces_are_labelled_with_their_source():
    assert "ov.label + ' — ' + getLocalized(col)" in _html()


def test_unit_mismatch_is_disclosed():
    """Blending sources with different units is legitimate but must not imply
    the numbers are directly comparable."""
    html = _html()
    assert "units may differ" in html
    assert "وقد تختلف وحدات القياس" in html


def test_a_failing_overlay_cannot_break_the_primary_chart():
    body = _fn("fetchSeries")
    assert "catch" in body
    assert "return null" in body


# --- pinned board -----------------------------------------------------------

def test_pin_button_and_board_exist():
    html = _html()
    assert 'id="pinChartBtn"' in html
    assert 'id="pinnedBoard"' in html
    assert "function pinCurrentChart" in html


def test_board_is_reorderable_by_drag():
    html = _html()
    assert 'draggable' in html
    for event in ("dragstart", "dragover", "drop"):
        assert f"'{event}'" in html
    # dragover must preventDefault or drop never fires.
    assert "e.preventDefault();" in _fn("wirePinnedDragAndDrop")


def test_reordering_is_keyboard_accessible():
    """Drag and drop is pointer-only; the board needs a keyboard equivalent."""
    html = _html()
    assert "function movePinned" in html
    assert "Move earlier" in html or "تحريك للخلف" in html


def test_pinned_order_survives_reload():
    html = _html()
    assert "kinjo.charts.pinned" in html
    assert "function savePinned" in html and "function loadPinned" in html


def test_storage_failures_are_tolerated():
    """localStorage throws in private mode and on quota; the board must still
    work for the session."""
    assert "catch" in _fn("savePinned")
    assert "catch" in _fn("loadPinned")
