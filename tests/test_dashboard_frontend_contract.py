import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"
DASHBOARD_FILTERS_JS = ROOT / "static" / "js" / "dashboard_filters.js"
DECISION_SUPPORT_JS = ROOT / "static" / "js" / "decision_support.js"
ANALYTICS_V2_CSS = ROOT / "static" / "css" / "admin_analytics_v2.css"
ANALYTICS_TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"
ADMIN_ANALYTICS_JS = ROOT / "static" / "js" / "admin_analytics.js"
ADMIN_DASHBOARD_TEMPLATE = ROOT / "templates" / "admin_dashboard.html"
ADMIN_DASHBOARD_JS = ROOT / "static" / "js" / "admin_dashboard.js"
ADMIN_ACTIVITY_FILTERS_JS = ROOT / "static" / "js" / "admin_activity_filters.js"


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


def test_trend_chart_padding_guards_against_negative_array_length():
    """new Array(dataSeries.length - 1) throws RangeError when dataSeries is
    empty (length 0 -> -1), which is a real, reachable case (any date range
    with no attendance/incident data), not just a test artifact. This
    silently aborted every widget still queued after updateTrendCharts() in
    loadAdminAnalytics's shared try block — alerts, data quality, targets,
    benchmarks, recommendations, registration analytics, and the
    risk-radar/executive-banner event never ran. Confirmed via live
    investigation on 2026-07-04.
    """
    source = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    assert "const paddingLength = Math.max(0, dataSeries.length - 1);" in source
    assert "new Array(dataSeries.length - 1)" not in source
    assert source.count("new Array(paddingLength)") == 3


def test_alerts_card_has_empty_state():
    """loadAlerts() previously left #alertList blank (just cleared innerHTML)
    when combinedAlerts was empty instead of showing a message, unlike the
    Risk Intelligence card's #noRiskData fallback."""
    source = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    assert "لا توجد تنبيهات نشطة حالياً" in source
    assert re.search(r"if \(combinedAlerts\.length === 0\) \{", source)


def test_data_quality_card_has_helper_text_and_wired_bars():
    """The three health bars (Completeness/Accuracy/Freshness) were rendered
    with hardcoded template defaults and never actually updated by
    loadDataQuality(); only the headline score/badge were wired. Also checks
    the explanatory <details> element required for the Data Quality card."""
    template = ANALYTICS_TEMPLATE.read_text(encoding="utf-8")
    assert 'class="dq-info' in template
    assert "معلومات عن مؤشر جودة البيانات" in template

    source = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    assert 'setBar("dqCompBar", "dqCompVal", data.completeness_percent);' in source
    assert 'setBar("dqAccBar", "dqAccVal", data.accuracy_score);' in source
    assert 'setBar("dqFreshBar", "dqFreshVal", data.timeliness_score);' in source


def test_data_quality_ring_wrapper_does_not_double_fetch():
    """dashboard.html used to wrap window.loadDataQuality in a patch that
    called the (async, void-returning) original function a second time via
    .then(pct => ...), silently doing nothing useful (loadDataQuality never
    returns a value, and already updates the ring itself) while doubling the
    /api/analytics/data-quality request cost on every call."""
    template = ANALYTICS_TEMPLATE.read_text(encoding="utf-8")
    assert "const origDQ = window.loadDataQuality;" not in template
    assert "origDQ.apply(this, arguments).then" not in template


def test_activity_feed_has_loading_and_error_states():
    source = ADMIN_ACTIVITY_FILTERS_JS.read_text(encoding="utf-8")
    assert "جاري تحميل النشاطات" in source
    assert "تعذر تحميل النشاطات" in source
    assert "activityRetryBtn" in source
    assert "spinner-border" in source


def test_auto_refresh_toggle_present_and_wired():
    template = ADMIN_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="autoRefreshCheck"' in template

    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert "isAutoRefreshEnabled()" in source
    assert 'localStorage.getItem("autoRefreshEnabled")' in source
    assert 'localStorage.setItem("autoRefreshEnabled"' in source
    # Must not unconditionally auto-start regardless of saved preference
    assert "if (this.isAutoRefreshEnabled()) this.startAutoRefresh();" in source
