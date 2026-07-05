from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_TEMPLATE = ROOT / "templates" / "admin" / "incident_reports_list.html"
GENERATE_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "incident_reports_generate.html"
DETAIL_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "incident_report_detail.html"


def test_generate_page_has_no_js_syntax_error():
    """`const cyberlume-card = ...` is not a legal JS identifier (hyphens
    aren't allowed in const declarations) -- this was a hard parse error
    that killed the ENTIRE inline <script> block, so loadScopes() never
    populated the scope picker and generateReport() was never defined at
    all, silently falling back to native browser form submission."""
    import re
    import shutil
    import subprocess
    import pytest

    html = GENERATE_TEMPLATE.read_text(encoding="utf-8")
    assert "cyberlume-card" not in html
    assert "const scopeCard" in html

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to verify JS syntax")
    script = re.search(r"<script>([\s\S]*?)</script>", html).group(1)
    result = subprocess.run(
        [node, "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"],
        input=script, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"JS syntax error in generate page: {result.stderr}"


def test_no_fictitious_cyberlume_classes_on_any_incident_report_page():
    for template in (LIST_TEMPLATE, GENERATE_TEMPLATE, DETAIL_TEMPLATE):
        html = template.read_text(encoding="utf-8")
        assert "cyberlume" not in html, f"cyberlume residue in {template.name}"


def test_detail_page_dead_breadcrumb_block_removed():
    """6th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = DETAIL_TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_list_page_reads_real_backend_field_names_for_report_detail():
    """The "View Report" modal read report.metrics_json (real key:
    metrics), report.creator?.username (real key: created_by), and
    report.governorate / report.kindergarten?.name_ar (real key:
    scope_name) -- none of those read fields exist on the actual
    GET /api/admin/reports/incidents/{id} response, so the modal always
    showed zeroed metrics, blank scope, and "Unknown" creator."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "report.metrics_json" not in html
    assert "report.metrics" in html
    assert "report.creator?.username" not in html
    assert "report.created_by" in html
    assert "report.kindergarten?.name_ar" not in html
    assert "getScopeDisplayName(report.scope_type, report.scope_name)" in html


def test_standalone_detail_page_reads_real_backend_field_names():
    html = DETAIL_TEMPLATE.read_text(encoding="utf-8")
    assert "reportData.creator_name" not in html
    assert "reportData.created_by" in html
    assert "reportData.kindergarten_name" not in html
    assert "reportData.governorate" not in html
    assert "reportData.scope_name" in html


def test_annual_report_year_field_is_sent_and_accepted():
    """The Year <select> was sent as a `year` form field the backend
    endpoint's signature never declared -- silently discarded, so the
    server always generated the current year's report regardless of what
    year the admin selected."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "year: year || ''" in html

    import inspect
    import admin_endpoints
    sig = inspect.signature(admin_endpoints.generate_incident_report)
    assert "year" in sig.parameters


def test_tables_have_caption_and_column_scope():
    list_html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert list_html.count('<caption class="visually-hidden">') == 2
    assert list_html.count('scope="col"') == 9  # 7-col main table + 2-col per-kg table


def test_list_query_batches_kindergarten_and_creator_lookups():
    """list_incident_reports() accessed report.kindergarten.name_ar and
    report.creator.username per row with no eager-loading option -- an
    N+1 query pattern (up to 2 extra queries per row, up to per_page=100
    rows)."""
    import admin_endpoints
    import inspect
    source = inspect.getsource(admin_endpoints.list_incident_reports)
    assert "selectinload(models.Report.kindergarten)" in source
    assert "selectinload(models.Report.creator)" in source


def test_pagination_ui_exists_with_delegated_clicks():
    """The backend already returned a pagination object, but the template
    rendered no pagination controls at all -- reports beyond the first
    page (per_page=20 default) were permanently unreachable."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="reportsPaginationNav"' in html
    assert 'id="reportsPagination"' in html
    assert "renderReportsPagination" in html
    assert "data-page" in html


def test_governorate_dropdown_has_bilingual_labels():
    """loadGovernorates() hardcoded Arabic-only governorate names for both
    filter and modal selects -- switching to English left this one
    dropdown showing Arabic regardless of ui_lang."""
    html = LIST_TEMPLATE.read_text(encoding="utf-8")
    assert "GOV_LABEL_EN" in html
    assert "IS_EN ? GOV_LABEL_EN[gov] : gov" in html
