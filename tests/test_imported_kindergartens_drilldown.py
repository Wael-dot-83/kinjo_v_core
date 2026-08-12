"""Drill-down fixes for the Imported Kindergartens admin page.

Covers the two backend correctness bugs (unstable pagination, contradictory
district filter) and the frontend gaps found alongside them.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "imported_kindergartens.html"
SERVICE = ROOT / "kindergarten_import_service.py"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_pagination_is_deterministically_ordered():
    """`offset().limit()` ran with no ORDER BY, so Postgres was free to return
    rows in any order -- the same row could repeat on page 2 and be skipped on
    page 3."""
    source = SERVICE.read_text(encoding="utf-8")
    body = source.split("def get_imported_kindergartens", 1)[1].split("\n    def ", 1)[0]
    assert "order_by(" in body
    # Take everything from order_by up to the paginating call rather than the
    # first ")", which lands inside the nested .desc().
    order_clause = body.split("order_by(", 1)[1].split(".offset(", 1)[0]
    assert "created_at" in order_clause
    # A tiebreaker is required: created_at alone is not unique.
    assert "ImportedKindergarten.id" in order_clause


def test_district_options_are_scoped_to_the_selected_governorate():
    """The district dropdown listed every district in the country regardless of
    governorate, so a user could select a pair that matches nothing."""
    source = SERVICE.read_text(encoding="utf-8")
    body = source.split("def get_imported_kindergartens", 1)[1].split("def ", 1)[0]
    assert "district_query" in body
    filtered = body.split("district_query", 1)[1]
    assert "if governorate:" in filtered


def test_dates_use_the_jordan_locale_not_the_gulf_one():
    """'ar-SA' renders the Hijri calendar and Gulf month names (يوليو) where
    Jordan writes تموز, and ignored English mode entirely."""
    # Ignore comment lines: the fix documents the old 'ar-SA' value by name.
    code = "\n".join(
        line for line in _template().splitlines()
        if not line.lstrip().startswith("//")
    )
    assert "ar-SA" not in code
    assert "ar-JO" in code
    assert "en-JO" in code


def test_filters_are_deep_linkable():
    """Filter state lived only in memory, so a filtered view could not be
    bookmarked, shared, or restored with Back."""
    html = _template()
    assert "history.replaceState" in html
    assert "function readUrl" in html
    for key in ("search", "governorate", "district", "page"):
        assert f"qs.set('{key}'" in html or f"qs.get('{key}')" in html


def test_results_info_reports_an_absolute_range():
    """"Showing 50 of 500" read identically on every page."""
    html = _template()
    assert "data.per_page" in html
    assert "first" in html and "last" in html


def test_failed_load_offers_a_retry():
    html = _template()
    assert "data-retry-page" in html
    assert "function showError" in html


def test_csv_export_is_utf8_bom_encoded_for_excel():
    """Arabic names open as mojibake in Excel without a BOM."""
    html = _template()
    assert "function exportCsv" in html
    assert "﻿" in html


def test_changing_governorate_clears_the_stale_district():
    html = _template()
    assert "governorate !== currentFilters.governorate" in html


def test_district_list_is_not_frozen_after_first_load():
    """The old `filterOptionsPopulated` guard froze the first district list in
    place, which defeats server-side scoping."""
    html = _template()
    assert "filterOptionsPopulated" not in html
    assert "governoratesPopulated" in html
