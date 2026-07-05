from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "imported_kindergartens.html"


def test_no_dead_inline_onclick_handlers():
    """applyFilters/clearFilters/loadKindergartens were declared inside an
    IIFE and never attached to `window`, but the Search button, Clear
    button, and every pagination link invoked them via inline onclick=""
    attributes -- which only resolve names in the global scope. All three
    controls threw "X is not defined" and did nothing. Fixed by binding
    via addEventListener/event delegation instead."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'onclick="applyFilters()"' not in html
    assert 'onclick="clearFilters()"' not in html
    assert "onclick=\"loadKindergartens(" not in html
    assert 'id="searchBtn"' in html
    assert 'id="clearFiltersBtn"' in html
    assert "data-page=" in html


def test_table_has_caption_and_column_scope():
    """The 8-column results table had no <caption> and no scope="col" on
    any header cell."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 8


def test_filter_selects_are_populated_from_api_response():
    """The Governorate and City <select> elements only ever rendered a
    single static "All ___" option -- nothing populated real values, so
    users could never actually filter by governorate or district."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "populateFilterOptions" in html
    assert "data.governorates" in html
    assert "data.districts" in html


def test_filter_selects_no_longer_have_conflicting_aria_label():
    """Both selects had a <label> reading "Governorate"/"City" but also a
    conflicting aria-label="All Governorates"/"All Cities" -- since
    aria-label wins for accessible-name computation, screen readers
    announced the placeholder text instead of the field's actual label."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'aria-label="{% if ui_lang == \'en\' %}All Governorates' not in html
    assert 'aria-label="{% if ui_lang == \'en\' %}All Cities' not in html


def test_search_input_is_debounced():
    """The search input fired a full fetch on every keystroke with no
    debounce."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "searchDebounce" in html
