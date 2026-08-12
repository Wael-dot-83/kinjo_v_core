"""Status pills and fuzzy autocomplete on the daily reports organization page."""

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


# --- pills ------------------------------------------------------------------

def test_dropdown_is_replaced_by_a_pill_group():
    html = _html()
    assert 'id="statusPills"' in html
    assert 'role="group"' in html
    # The <select> is gone, but the id survives as a hidden input so the
    # existing filter code keeps working untouched.
    assert '<select id="statusFilter"' not in html
    assert '<input type="hidden" id="statusFilter"' in html


def test_pill_group_is_labelled():
    html = _html()
    assert 'aria-labelledby="statusPillsLabel"' in html
    assert 'id="statusPillsLabel"' in html


def test_pills_carry_counts_from_the_shared_source():
    """A pill and the totals bar must never disagree."""
    body = _fn("renderStatusPills")
    assert "statusTotals(groups)" in body
    assert "pill-count" in body
    assert "STATUS_UI_CONFIG" in _fn("statusTotals")
    assert "status_counts" in _fn("statusTotals")


def test_pill_state_is_exposed_not_just_coloured():
    body = _fn("renderStatusPills")
    assert 'aria-pressed' in body


def test_active_pill_toggles_off():
    """Undoing a filter must not require hunting for an "all" option."""
    body = _fn("renderStatusPills")
    assert 'hidden.value === opt.key ? "" : opt.key' in body


def test_choosing_a_pill_returns_to_page_one():
    body = _fn("renderStatusPills")
    assert "state.page = 1;" in body


def test_pills_count_the_unfiltered_set():
    """Counting after the status filter would leave every inactive pill at
    zero."""
    js = _js()
    assert js.index("renderStatusPills(response.kindergartens") < js.index("applyClientFilters(response")


# --- autocomplete -----------------------------------------------------------

def test_inputs_have_combobox_semantics():
    html = _html()
    for field in ("child", "teacher"):
        assert f'id="{field}Suggestions"' in html
        assert f'aria-controls="{field}Suggestions"' in html
    assert 'role="combobox"' in html
    assert 'aria-autocomplete="list"' in html
    assert 'role="listbox"' in html


def test_suggestions_need_two_characters():
    body = _fn("renderSuggestions")
    assert "term.length < 2" in body


def test_matching_tolerates_typos_but_keeps_order():
    """Subsequence matching: every character must appear, in order, so "ahd"
    finds "Ahmed" while "zzz" finds nothing."""
    body = _fn("fuzzyScore")
    assert "i === n.length ? score : -1" in body
    # An exact substring must still outrank a scattered fuzzy hit.
    assert "1000 - direct" in body


def test_keyboard_navigation_is_complete():
    body = _fn("wireAutocomplete")
    for key in ("ArrowDown", "ArrowUp", "Enter", "Escape"):
        assert key in body


def test_active_option_is_announced():
    body = _fn("moveSuggestion")
    assert 'aria-selected' in body
    assert "aria-activedescendant" in body


def test_arrow_navigation_wraps():
    body = _fn("moveSuggestion")
    assert "index = items.length - 1" in body
    assert "index = 0" in body


def test_click_selection_survives_blur():
    """A click handler fires after blur has already closed the list."""
    body = _fn("wireAutocomplete")
    assert '"mousedown"' in body
    assert "event.preventDefault();" in body


def test_names_are_escaped_and_bidi_isolated():
    body = _fn("renderSuggestions")
    assert "escapeHtml(entry.name)" in body
    assert "<bdi>" in body


def test_suggestion_pool_is_deduplicated():
    """The same child appears under every matching kindergarten."""
    assert "new Set(names)" in _fn("suggestionPool")


def test_no_uninstallable_dependency_was_added():
    """This project has no bundler and blocks external CDNs, so Fuse.js could
    not be imported; the matcher is local."""
    js = _js()
    assert "import " not in js.split("function fuzzyScore", 1)[0][-2000:]
    assert "cdn." not in js
