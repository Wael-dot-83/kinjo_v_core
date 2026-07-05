from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "drilldown.html"
JS_FILE = ROOT / "static" / "js" / "admin_analytics_drilldown.js"


def test_dead_breadcrumb_block_removed():
    """12th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts. This one was more
    severe than the usual cosmetic loss: the dead block also contained
    #breadcrumbDimension, which updateBreadcrumbsAndTitle() set
    textContent on with NO null check -- since the element never existed,
    every single page load threw an uncaught TypeError that was caught by
    loadDrilldownData()'s outer catch and replaced the whole page with a
    generic "Unable to load data" error, regardless of dimension_type or
    dimension_id. This page never rendered any data at all before this fix."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_breadcrumb_dimension_element_access_is_null_safe():
    """Defense in depth for the crash above: even though the element is
    gone now, guard the lookup so a future template change can't
    reintroduce a full-page crash from one missing element."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert 'document.getElementById("breadcrumbDimension").textContent' not in js
    assert "const breadcrumbEl = document.getElementById(\"breadcrumbDimension\");" in js
    assert "if (breadcrumbEl) breadcrumbEl.textContent = displayName;" in js


def test_kindergarten_and_class_table_branches_implemented():
    """populateTable() only ever handled the GOVERNORATE branch; for
    KINDERGARTEN/CLASS it left headers/rows as empty strings with a
    comment "Add logic ... if needed later" -- the backend fully builds
    and returns class_list (for KINDERGARTEN) and a per-child attendance
    list (for CLASS), but that data was fetched and then thrown away,
    leaving the table permanently blank on drill-down."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert 'type.toUpperCase() === "KINDERGARTEN"' in js
    assert 'type.toUpperCase() === "CLASS"' in js
    assert "Add logic for KINDERGARTEN -> CLASS drilldown if needed later" not in js


def test_class_summary_cards_have_dedicated_branch():
    """The old code funneled every non-GOVERNORATE type into a single
    "KINDERGARTEN" else-branch reading metrics.attendance_rate/
    incident_rate/governance_score -- fields that don't exist on the
    CLASS dimension's real metrics shape ({capacity, children_count,
    age_group}), so a CLASS page (once reachable) would have silently
    shown 0.0%/0.00 placeholders instead of real data."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert 'else if (type.toUpperCase() === "CLASS")' in js
    assert "metrics.capacity" in js
    assert "metrics.age_group" in js


def test_apply_date_filter_alias_wired_for_shared_macro_presets():
    """The shared date-range-filter macro's "Last Month"/"Clear Filters"
    buttons look for a global applyDateFilter() to trigger a reload after
    updating the date inputs -- this page only ever defined
    loadDrilldownData (wired to the dedicated Refresh button via
    on_refresh), so the date-preset buttons silently updated the pickers
    with no visible reload effect."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert "window.applyDateFilter = loadDrilldownData;" in js


def test_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html

    js = JS_FILE.read_text(encoding="utf-8")
    assert '<th role="button">' not in js
    assert '<th class="text-center" role="button"' not in js
    assert js.count('<th scope="col"') == 12
