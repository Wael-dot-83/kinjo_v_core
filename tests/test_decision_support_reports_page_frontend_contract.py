from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "reporting_dashboard.html"
JS_FILE = ROOT / "static" / "js" / "admin_reporting_dashboard.js"


def test_dead_breadcrumb_block_removed():
    """10th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_interactive_functions_are_exposed_globally():
    """admin_reporting_dashboard.js wraps its whole body in an IIFE, but
    the template wires loadAllReports()/onLevelChange() via global inline
    onclick/onchange handlers, and the shared date-range-filter macro's
    "Last Month"/"Clear Filters" buttons look for a global applyDateFilter()
    to trigger a reload. Without exposing these, every interactive control
    on this page threw a silent ReferenceError -- only the initial default
    (Jordan/this-month) view ever loaded; level switching, manual refresh,
    and date presets were all unreachable."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert "window.loadAllReports = loadAllReports;" in js
    assert "window.onLevelChange = onLevelChange;" in js
    assert "window.applyDateFilter = loadAllReports;" in js
    assert "window.exportReport = exportReport;" in js


def test_no_duplicate_refresh_button_id():
    """The date_range_filter(refresh_btn_id="refreshReportBtn", ...) macro
    call already renders a button with id="refreshReportBtn" -- the level-
    selector card also had its own, separate button with the exact same
    id, an invalid duplicate-ID situation. Replaced with the export
    controls the page was missing instead of keeping a redundant button."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count('id="refreshReportBtn"') == 1


def test_export_control_wired_to_real_get_endpoint():
    """show_export=True was passed to the shared date_range_filter macro,
    but export_modal_id was never supplied, so the macro's own Export
    button (which requires a Bootstrap modal target) never rendered at
    all -- a fully-working, require_admin-gated backend export endpoint
    (GET /api/admin/reports/export) was completely unreachable from the
    UI. That endpoint is a plain GET with query params (not the POST/
    modal-based flow the shared export-modal component expects), so a
    lightweight page-local report-type selector + button was added
    instead of trying to force it through the shared modal macro."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="exportReportType"' in html
    assert 'onclick="exportReport()"' in html

    js = JS_FILE.read_text(encoding="utf-8")
    assert "function exportReport()" in js
    export_fn_start = js.index("function exportReport()")
    export_fn_end = js.index("\n  }", export_fn_start)
    export_fn_body = js[export_fn_start:export_fn_end]
    assert "/api/admin/reports/export" in export_fn_body
    assert "getFilters()" in export_fn_body


def test_tables_have_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count("<caption") == 5
    assert html.count('<th scope="col">') == 43
    assert "<th>" not in html
