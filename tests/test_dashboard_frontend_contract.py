import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"
DASHBOARD_FILTERS_JS = ROOT / "static" / "js" / "dashboard_filters.js"
DECISION_SUPPORT_JS = ROOT / "static" / "js" / "decision_support.js"
ANALYTICS_V2_CSS = ROOT / "static" / "css" / "admin_analytics_v2.css"
ANALYTICS_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"
ADMIN_ANALYTICS_JS = ROOT / "static" / "js" / "admin_analytics.js"


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


def test_risk_intelligence_cards_use_real_backend_field_names():
    """get_high_risk_children() returns {child_name, kindergarten_name,
    risk_type, risk_value, description, kindergarten_id} — not the
    {name, kindergarten, reason, risk_score} shape both risk-card renderers
    used to read, which discarded every real entry and always showed "no
    risk alerts" regardless of actual data (confirmed via live investigation
    of /admin/analytics on 2026-07-04).
    """
    dashboard = ANALYTICS_TEMPLATE.read_text(encoding="utf-8")
    assert "r.child_name || r.kindergarten_name" in dashboard
    assert "window._classifyRisk" in dashboard
    assert "r.risk_score" not in dashboard

    admin_analytics = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    assert "item.child_name" in admin_analytics
    assert "item.kindergarten_name" in admin_analytics
    assert "item.risk_value" in admin_analytics
    # The stale shape must not reappear in updateRiskRadar's validation filter
    stale_filter_pattern = re.search(
        r"function updateRiskRadar.*?(?=\nfunction )", admin_analytics, re.S
    )
    assert stale_filter_pattern is not None
    stale_body = stale_filter_pattern.group(0)
    assert "item.risk_score" not in stale_body
    assert 'item.name === "string"' not in stale_body
