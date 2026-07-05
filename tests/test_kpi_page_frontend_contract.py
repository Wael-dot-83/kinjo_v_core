from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KPI_TEMPLATE = ROOT / "templates" / "admin" / "kpi.html"
KG_OVERVIEW_JS = ROOT / "static" / "js" / "kg_overview.js"
KPI_SERVICE = ROOT / "kpi_service.py"


def test_table_has_caption_and_column_scope():
    """The per-kindergarten KPI table had no <caption> and no scope="col"
    on any of its 7 <th> elements."""
    html = KPI_TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 7


def test_progress_bars_have_aria_range_semantics():
    """The three network-summary progress bars had no role/aria-value*
    attributes at all -- screen readers announced nothing about them."""
    html = KPI_TEMPLATE.read_text(encoding="utf-8")
    for bar_id in ("netAttBar", "netRatioBar", "netGqiBar"):
        segment = html[html.index(f'id="{bar_id}"'):html.index(f'id="{bar_id}"') + 250]
        assert 'role="progressbar"' in segment
        assert 'aria-valuemin="0"' in segment
        assert 'aria-valuemax="100"' in segment
        assert "aria-valuenow" in segment
    assert "setAttribute('aria-valuenow'" in html


def test_kg_overview_deep_link_opens_matching_panel():
    """The KPI table linked each row to /admin/kg-overview?id=<id>, but
    kg_overview.js never read the `id` query param anywhere -- the link
    landed on the generic unfiltered page every time."""
    js = KG_OVERVIEW_JS.read_text(encoding="utf-8")
    assert "openDeepLinkedKG" in js
    assert "URLSearchParams(window.location.search).get('id')" in js


def test_network_summary_returns_name_and_governorate():
    """kpi_service.py's per-kindergarten entries omitted kindergarten_name
    and governorate entirely, even though kpi.html's table cells, chart
    labels, and search box all read r.kindergarten_name / r.governorate --
    every row rendered blank and the search box matched nothing."""
    content = KPI_SERVICE.read_text(encoding="utf-8")
    assert '"kindergarten_name": kg.name_ar or kg.name_en' in content
    assert '"governorate": kg.governorate' in content


def test_network_summary_endpoint_accepts_governorate_param():
    import inspect
    import kpi_service

    sig = inspect.signature(kpi_service.get_kpi_network_summary)
    assert "governorate" in sig.parameters


def test_no_duplicated_governance_band_thresholds():
    """kpi_service.py's network-summary handler used to duplicate
    compute_governance_score's band thresholds inline (GREEN>=70,
    AMBER>=40) as an "else" fallback that could never execute (the function
    always returns a tuple) but hardcoded numbers that didn't even match
    the authoritative thresholds (GREEN>=80, AMBER>=60) used elsewhere in
    this file -- a landmine if the tuple-returning contract ever changed.
    Per CLAUDE.md, KPI band logic must live only in compute_governance_score,
    not be re-derived in an endpoint."""
    content = KPI_SERVICE.read_text(encoding="utf-8")
    handler_start = content.index("def get_kpi_network_summary")
    handler_body = content[handler_start:handler_start + 2000]
    assert "gs >= 70" not in handler_body
    assert "gs >= 40" not in handler_body
    assert "gs, band = KPIService.compute_governance_score" in handler_body
