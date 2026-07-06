from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"
JS_FILE = ROOT / "static" / "js" / "admin_analytics.js"


def test_dead_breadcrumb_block_removed():
    """7th confirmed occurrence of the dead-{% block breadcrumb %} bug class
    across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_kinjo_lang_is_assigned_before_use():
    """The inline script reads window.KINJO_LANG in several places but
    nothing on this page ever set it, so it silently fell back to the
    'ar' default in every branch -- English mode never rendered its
    English-only inline JS strings correctly."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'window.KINJO_LANG = "{{ ui_lang }}"' in html
    assign_pos = html.index('window.KINJO_LANG = "{{ ui_lang }}"')
    first_use_pos = html.index("window.KINJO_LANG ||")
    assert assign_pos < first_use_pos


def test_export_modal_receives_real_report_types():
    """export_modal() is called with no report_types anywhere in the
    codebase except here -- the macro's <select id="exportReportType">
    is wrapped in {% if report_types %}, so it never rendered at all,
    leaving the export flow permanently stuck on 'select a report type'."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% set report_types = [" in html
    assert 'export_modal(report_types=report_types)' in html
    for value in ("attendance", "incidents", "compliance", "governorate", "full_audit"):
        assert f'"value": "{value}"' in html


def test_registration_table_header_count_matches_row_rendering():
    """The JS renders 9 <td> per row but the table only declared 7 <th>
    headers, and skeleton/empty rows used colspan=7 -- misaligned columns."""
    html = TEMPLATE.read_text(encoding="utf-8")
    start = html.index('id="registrationTable"')
    end = html.index("</thead>", start)
    header_block = html[start:end]
    assert header_block.count("<th scope=") == 9
    assert html.count('colspan="9"') == 3
    assert 'colspan="7"' not in html


def test_status_matrix_and_action_queue_are_separate_cards():
    """_renderStatusMatrix() targeted #regStatusMatrix, which used to BE the
    entire Actions Required card's body -- calling it wiped out the sibling
    #regActionsBadge/#regActionQueue elements right before
    _renderActionQueue() tried to populate them. Fixed by splitting into
    two independent az-card containers."""
    html = TEMPLATE.read_text(encoding="utf-8")
    action_card_start = html.index('id="regActionQueue"')
    status_card_start = html.index('id="regStatusMatrix"')
    assert action_card_start != status_card_start
    # The action queue's own card (header+badge+body) must not contain the
    # status matrix id, proving they are no longer nested in one wrapper.
    action_card_block = html[html.rindex('<div class="az-card', 0, action_card_start):action_card_start]
    assert "regStatusMatrix" not in action_card_block


def test_risk_view_all_toggle_is_wired():
    """The 'View All Risks' button toggled visibility via inline markup but
    had no click handler at all -- clicking it did nothing."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "_riskShowAll" in html
    assert "_lastRiskArr" in html
    assert "getElementById('riskViewAllBtn')?.addEventListener('click'" in html
    assert "const MAX = _riskShowAll ? riskArr.length : 5" in html


def test_tables_have_captions():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count('<caption class="visually-hidden">') == 2


def test_no_dead_css_classes_remain():
    """az-filter-bar (undefined) and a duplicate kpi-sparkline base class
    were dead weight with no matching CSS rule of their own beyond the
    *-v2 sibling class already doing the styling. Note: dq-info (also
    unstyled) is deliberately kept -- an existing contract test
    (test_dashboard_frontend_contract.py) already guards its presence on
    the Data Quality <details> element from a prior audit pass."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "az-filter-bar glass-filter-bar" not in html
    assert "kpi-sparkline kpi-sparkline-v2" not in html
    assert 'class="dq-info mt-2"' in html


def test_static_js_file_has_no_unrendered_jinja_syntax():
    """/static is mounted via plain StaticFiles (see main.py's
    app.mount('/static', UTF8StaticFiles(...))) -- it is never Jinja-
    processed, so any {% %} left inside a .js file renders as literal,
    browser-visible text instead of template output."""
    js = JS_FILE.read_text(encoding="utf-8")
    assert "{% if ui_lang" not in js
    assert "{% endif %}" not in js


def test_export_listener_uses_real_period_inputs_and_report_type_select():
    """The exportData listener read #startDate/#endDate (don't exist on this
    page -- the real inputs are #periodStart/#periodEnd) and
    input[name="reportType"]:checked (no such radio group exists -- the
    real control is the #exportReportType <select>). Both silently fell
    back to defaults, so the exported file never honored what an admin
    actually picked."""
    js = JS_FILE.read_text(encoding="utf-8")
    start = js.index("document.addEventListener('exportData'")
    end = js.index("\n});", start)
    block = js[start:end]
    assert 'getElementById("periodStart")' in block
    assert 'getElementById("periodEnd")' in block
    assert 'getElementById("startDate")' not in block
    assert 'getElementById("endDate")' not in block
    assert 'getElementById("exportReportType")' in block
    assert 'input[name="reportType"]:checked' not in block


def test_export_request_sets_json_content_type():
    """fetchWithAuth() passes options straight to fetch() with no default
    Content-Type header. A JSON.stringify()'d string body with no explicit
    Content-Type defaults to text/plain in the browser, and FastAPI/Pydantic
    rejects a text/plain body with a 422 ('Input should be a valid
    dictionary or object') even though the bytes are valid JSON -- the
    export button failed on every single click, regardless of report type
    or dates chosen. Confirmed directly: the same body sent with
    Content-Type: text/plain returns 422; with application/json it returns
    200."""
    js = JS_FILE.read_text(encoding="utf-8")
    start = js.index("document.addEventListener('exportData'")
    end = js.index("\n});", start)
    block = js[start:end]
    assert '"Content-Type": "application/json"' in block


def test_risk_heatmap_cells_wrapped_in_row_for_grid_layout():
    """updateRiskHeatmap() appended bare .col-6.col-md-4 <div>s directly into
    #riskHeatmap with no .row ancestor. Bootstrap's grid columns need a flex
    .row parent to actually sit side-by-side -- without one each "column"
    div is still a plain block element and takes its own full-width line,
    so all 12 governorates rendered as a single stack of full-width bars
    instead of a 3-4 column heatmap grid. Confirmed live via Playwright
    (screenshot showed one solid red column, not a grid)."""
    js = JS_FILE.read_text(encoding="utf-8")
    start = js.index("function updateRiskHeatmap")
    end = js.index("\nfunction ", start + 1)
    block = js[start:end]
    assert 'list.className = "row g-2 list-unstyled mb-0";' in block
    assert 'item.className = "col-6 col-md-4 col-lg-3";' in block


def test_risk_heatmap_cells_are_keyboard_accessible_buttons():
    """Cells were plain <div>s with only a mouse click listener -- no
    tabindex, no role, no keyboard handler, so a keyboard-only or
    screen-reader user could never reach or activate them (WCAG 2.1.1).
    A native <button> gets focus and Enter/Space activation for free."""
    js = JS_FILE.read_text(encoding="utf-8")
    start = js.index("function updateRiskHeatmap")
    end = js.index("\nfunction ", start + 1)
    block = js[start:end]
    assert 'btn.type = "button";' in block
    assert 'btn.className = `risk-cell' in block
    assert 'btn.setAttribute(\n      "aria-label",' in block


def test_risk_heatmap_sorted_highest_risk_first():
    """Governorates rendered in whatever order the API happened to return
    them, so the most at-risk governorates could be scrolled past unseen.
    Sorting ascending by governance_score surfaces the worst first."""
    js = JS_FILE.read_text(encoding="utf-8")
    start = js.index("function updateRiskHeatmap")
    end = js.index("\nfunction ", start + 1)
    block = js[start:end]
    assert "const sorted = rows.slice().sort((a, b) => {" in block
    assert "return scoreA - scoreB;" in block


def test_risk_heatmap_has_a_threshold_legend():
    """The red/amber/green cells encoded risk purely by color with no key
    explaining what the thresholds mean -- added a legend using the same
    gov-legend-dot classes already used by the Governance Distribution
    card on this same page, for visual consistency."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'class="d-flex flex-wrap gap-3 risk-legend"' in html
    assert "gov-legend-dot--red" in html
    assert "gov-legend-dot--amber" in html
    assert "gov-legend-dot--green" in html


def test_dead_advanced_metrics_container_removed():
    """#advancedMetricsContainer was a permanently d-none placeholder div
    with zero references anywhere in admin_analytics.js -- dead markup
    left over from a feature that was never wired up."""
    html = TEMPLATE.read_text(encoding="utf-8")
    js = JS_FILE.read_text(encoding="utf-8")
    assert "advancedMetricsContainer" not in html
    assert "advancedMetricsContainer" not in js
