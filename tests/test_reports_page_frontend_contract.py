import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "reports.html"
REPORTS_JS = ROOT / "static" / "js" / "admin_reports.js"
ADMIN_DESIGN_SYSTEM_CSS = ROOT / "static" / "css" / "admin_design_system.css"


def test_glass_panel_and_hover_elevate_have_css_rules():
    """reports.html uses "glass-panel"/"hover-elevate" on every card on the
    page (stat cards, Report Builder, preview, history, both modals — 9
    occurrences) but neither class had a CSS rule anywhere, so every one of
    them silently fell back to plain Bootstrap .card styling instead of the
    intended glass/blur treatment. Verified live: computed backdrop-filter
    was "none" before the fix, "blur(10px)" after."""
    css = ADMIN_DESIGN_SYSTEM_CSS.read_text(encoding="utf-8")
    assert re.search(r"^\.glass-panel\s*\{", css, re.MULTILINE)
    assert re.search(r"^\.hover-elevate:hover\s*\{", css, re.MULTILINE)


def test_report_builder_form_uses_bootstrap_not_undefined_tailwind_classes():
    """Every <select>/<input> in the Report Builder form, both CTA buttons
    (Preview/Export), the two modal Cancel buttons, and the history table
    wrapper used Tailwind-syntax utility classes (w-full, bg-surface-container/50,
    text-on-surface, rounded-lg, appearance-none, etc.) — but Tailwind is
    never loaded anywhere on this page or in admin_base.html, so none of
    those classes did anything and every one of those controls rendered as
    an unstyled default browser widget."""
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    for dead_class in (
        "bg-surface-container",
        "border-white/10",
        "appearance-none",
        "shadow-[0_0_15px",
    ):
        assert dead_class not in html, f"undefined Tailwind-style class still present: {dead_class}"
    # "text-on-surface" itself is dead (Tailwind/Material token, never
    # loaded); "text-on-surface-variant" is a distinct, pre-existing class
    # this fix didn't touch, so check for the exact standalone class only.
    assert not re.search(r'class="[^"]*\btext-on-surface\b(?!-variant)[^"]*"', html)
    # Spot-check a few of the 16 filter selects were actually converted
    for select_id in ("reportLevel", "severityFilter", "sensitivityFilter"):
        assert f'class="form-select" id="{select_id}"' in html
    assert 'id="previewReportBtn"' in html and "btn-outline-primary" in html
    assert 'id="exportReportBtn"' in html


def test_stat_cards_do_not_have_mismatched_heading_tags():
    """Each of the 4 KPI stat cards opened <h3> but closed with a stray
    </h1></div> — the extra </div> forced an implied early close of
    card-body, pushing the trailing <small> caption out of its padded
    wrapper in all four cards."""
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    # The page's own <h1> title is legitimate; the bug was specifically a
    # stray, mismatched </h1> immediately after a stat card's "--" value.
    assert "--</h1>" not in html
    assert html.count('<h3 class="mb-0 fw-bold') == 4
    for stat_id in ("statReportsGenerated", "statScheduledReports", "statFailedExports", "statLastGenerated"):
        assert re.search(rf'id="{stat_id}">--</h3>', html), f"{stat_id} heading not properly closed"


def test_both_tables_have_caption_and_column_scope():
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    assert html.count('<caption class="visually-hidden">') == 2
    assert 'scope="col"' in html

    js = REPORTS_JS.read_text(encoding="utf-8")
    assert 'scope="col"' in js  # dynamically-generated preview table headers


def test_preview_table_pagination_markup_exists():
    """renderPreviewTable() (admin_reports.js) has always paginated sample
    data at 5 rows per page and referenced previewTablePagination/
    prevPreviewPageBtn/nextPreviewPageBtn/previewPaginationInfo — none of
    which existed anywhere in the template, so any preview with more than 5
    rows silently showed only the first 5 with zero indication more data
    existed. The click handlers were already correctly wired in the JS
    (using optional chaining, so they never errored) waiting for markup
    that was never added."""
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    for el_id in ("previewTablePagination", "prevPreviewPageBtn", "nextPreviewPageBtn", "previewPaginationInfo"):
        assert f'id="{el_id}"' in html, f"missing pagination element: {el_id}"


def test_sortable_preview_header_is_keyboard_accessible():
    """The sortable <th> in the preview table only responded to mouse click
    (no tabindex, no keydown, no aria-sort) — keyboard and screen-reader
    users could not sort this table or perceive its sort state at all."""
    js = REPORTS_JS.read_text(encoding="utf-8")
    assert 'tabindex="0"' in js
    assert 'aria-sort="${ariaSort}"' in js
    assert '"keydown"' in js


def test_refresh_history_button_has_accessible_name():
    """#refreshHistoryBtn was a fully icon-only button with no aria-label,
    no title, and no visible text — no accessible name at all."""
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r'id="refreshHistoryBtn"[^>]*', html)
    assert match
    assert "aria-label=" in match.group(0)


def test_history_row_actions_have_per_report_accessible_names():
    """Download/Regenerate/View-logs controls in the live loadRecentHistory()
    had identical generic titles across every row, despite the report name
    already being available at generation time."""
    js = REPORTS_JS.read_text(encoding="utf-8")
    assert "const reportLabel = escapeHtml(item.report_name || item.report_type);" in js
    assert "${reportsText(\"تنزيل\", \"Download\")} ${reportLabel}" in js
    assert "${reportsText(\"إعادة إنشاء\", \"Regenerate\")} ${reportLabel}" in js


def test_governorate_filter_does_not_have_two_labels_for_one_control():
    """The Report Builder panel's #filterGovContainer added a second
    <label for="governorateFilter"> pointing at the same control already
    correctly labeled by the date_range_filter macro in the toolbar above —
    two <label for> elements bound to one control from unrelated parts of
    the page."""
    html = REPORTS_TEMPLATE.read_text(encoding="utf-8")
    label_for_count = len(re.findall(r'<label[^>]*for="governorateFilter"', html))
    assert label_for_count == 1, f"expected exactly one <label for=\"governorateFilter\">, found {label_for_count}"
