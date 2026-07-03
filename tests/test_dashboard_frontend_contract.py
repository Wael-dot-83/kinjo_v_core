import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"
DASHBOARD_FILTERS_JS = ROOT / "static" / "js" / "dashboard_filters.js"
DECISION_SUPPORT_JS = ROOT / "static" / "js" / "decision_support.js"
ANALYTICS_V2_CSS = ROOT / "static" / "css" / "admin_analytics_v2.css"
ANALYTICS_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"


def test_kpi_cards_expose_status_attribute_used_by_filter_layer():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'data-status="${kpi.band}"' in source
    assert 'data-kpi-status="${kpi.band}"' in source

    filters = DASHBOARD_FILTERS_JS.read_text(encoding="utf-8")
    assert 'document.querySelectorAll("[data-kpi-status]")' in filters


def test_dashboard_summary_uses_csrf_aware_fetch_when_available():
    source = DASHBOARD_FILTERS_JS.read_text(encoding="utf-8")
    assert 'typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch' in source
    assert 'credentials: "same-origin"' in source
    assert 'fetch("/api/dashboard/summary"' not in source


def test_decision_support_charts_have_fallback_paths():
    source = DECISION_SUPPORT_JS.read_text(encoding="utf-8")
    for helper in (
        "function canRenderChart()",
        "function showCanvasFallback(",
        "function prepareCanvas(",
        "function renderDecisionSupportFallback()",
    ):
        assert helper in source

    assert re.search(r"catch\s*\(err\)\s*\{[^}]*renderDecisionSupportFallback\(\)", source, re.S)
    assert source.count("showCanvasFallback(chartEl, dsText(\"ds.no_data\"));") >= 4


def test_analytics_filter_bar_sticks_to_scrollport_top():
    """The analytics filter bar must pin flush to the top of .admin-content.

    .admin-content is the real scroll container (the header sits outside it),
    so the sticky offset must cancel the scroller's own padding — a positive
    header-height offset leaves the bar floating mid-page.
    """
    css = ANALYTICS_V2_CSS.read_text(encoding="utf-8")
    match = re.search(r"\.glass-filter-bar\s*\{(?P<body>[^}]+)\}", css)
    assert match is not None
    body = match.group("body")
    assert re.search(r"position\s*:\s*sticky", body)
    assert re.search(r"top\s*:\s*calc\(-1 \* var\(--kinjo-spacing-6", body)
    assert re.search(r"z-index\s*:\s*1000", body)
    assert ".glass-filter-bar.is-stuck" in css

    template = ANALYTICS_TEMPLATE.read_text(encoding="utf-8")
    assert "classList.toggle('is-stuck'" in template
    assert re.search(r"scroller\.addEventListener\('scroll'", template)
