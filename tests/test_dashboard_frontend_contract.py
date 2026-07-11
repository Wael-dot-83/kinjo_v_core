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
ADMIN_DESIGN_SYSTEM_CSS = ROOT / "static" / "css" / "admin_design_system.css"
COMPONENTS_CSS = ROOT / "static" / "css" / "components.css"


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


def test_secondary_widgets_load_in_parallel_not_sequentially():
    """The 9 independent secondary widgets (comparative analysis, predictive
    insights, anomalies, alerts, data quality, targets, benchmarks,
    recommendations, registration analytics) were previously awaited one at
    a time in loadAdminAnalytics, so a single slow call anywhere in the
    chain (e.g. the leaderboard scan inside loadComparativeAnalysis, or the
    uncached kpi/alerts scan) gated every widget queued behind it — even
    ones that resolve in milliseconds once reached. Confirmed live: before
    this fix, widgets settled 13-90s after page load; after, 8 of 9 settle
    within ~2.6s regardless of how slow the remaining one (the still-uncached
    leaderboard, deferred separately) is.
    """
    source = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    match = re.search(
        r"await Promise\.allSettled\(\[(?P<body>.*?)\]\);", source, re.S
    )
    assert match is not None, "secondary widget loaders must be dispatched via Promise.allSettled"
    body = match.group("body")
    for call in (
        "loadComparativeAnalysis(start, end)",
        "loadPredictiveInsights(start, end, scopeType, scopeId)",
        "loadAnomalies(start, end, scopeType, scopeId)",
        "loadAlerts()",
        "loadDataQuality()",
        "loadTargets()",
        "loadBenchmarks()",
        "loadRecommendations()",
        "loadRegistrationAnalytics()",
    ):
        assert call in body, f"missing from parallel batch: {call}"

    # The old sequential form must not reappear elsewhere in the file.
    for stale in (
        "await loadComparativeAnalysis(start, end);\n",
        "await loadAlerts();\n    await loadDataQuality();",
    ):
        assert stale not in source


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
    """ActivityFilterBar delegates its loading/error markup to the shared
    AdminComponents.renderAsyncState helper (see test_shared_async_state_helper),
    passing an onRetry callback rather than wiring a fixed button id itself."""
    source = ADMIN_ACTIVITY_FILTERS_JS.read_text(encoding="utf-8")
    assert "جاري تحميل النشاطات" in source
    assert "تعذر تحميل النشاطات" in source
    assert 'renderAsyncState(feed, "loading"' in source
    assert 'renderAsyncState(feed, "error"' in source
    assert "onRetry: () => this.load()" in source


def test_shared_async_state_helper_exists_and_is_reused():
    """ROOT-006 follow-up: Alerts, Activity Feed, and Risk Intelligence each
    used to hand-roll their own loading/empty/error markup. Consolidated
    into AdminComponents.renderAsyncState (admin_components.js), loaded on
    every admin page before any page-specific script (see admin_base.html),
    so widgets share one implementation and one visual language."""
    components_source = (ROOT / "static" / "js" / "admin_components.js").read_text(encoding="utf-8")
    assert "renderAsyncState(container, state, options = {})" in components_source
    for branch in ('state === "loading"', 'state === "empty"', 'state === "error"'):
        assert branch in components_source

    admin_analytics = ADMIN_ANALYTICS_JS.read_text(encoding="utf-8")
    assert 'window.AdminComponents.renderAsyncState(alertList, "empty"' in admin_analytics

    activity_filters = ADMIN_ACTIVITY_FILTERS_JS.read_text(encoding="utf-8")
    assert "window.AdminComponents.renderAsyncState(feed," in activity_filters


def test_auto_refresh_toggle_present_and_wired():
    template = ADMIN_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="autoRefreshCheck"' in template

    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert "isAutoRefreshEnabled()" in source
    assert 'localStorage.getItem("autoRefreshEnabled")' in source
    assert 'localStorage.setItem("autoRefreshEnabled"' in source
    # Must not unconditionally auto-start regardless of saved preference
    assert "if (this.isAutoRefreshEnabled()) this.startAutoRefresh();" in source


def test_failed_login_is_not_relabeled_as_successful_authentication():
    """createActivityItem used to rewrite any activity whose message contained
    "login"/"تسجيل دخول" to "Successful Authentication"/"دخول ناجح" — a
    substring check broad enough to also match LOGIN_FAILED's own message
    ("Failed login attempt" / "محاولة تسجيل دخول فاشلة"), so a failed login
    rendered with a success-sounding title next to a "Failed" status badge.
    The rewrite must be gated on activity.status === "success", which the
    backend already computes correctly from _FAILURE_ACTIONS."""
    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    match = re.search(
        r'if\s*\(\s*(.*?)\s*\)\s*\{\s*message = lang === "en" \? "Successful Authentication"',
        source,
        re.DOTALL,
    )
    assert match, "could not find the login-message elevation guard in admin_dashboard.js"
    condition = match.group(1)
    assert 'activity.status === "success"' in condition


def test_activity_filter_bar_is_sole_owner_of_activity_feed_when_present():
    """AdminDashboard.renderDashboard() and ActivityFilterBar.load() both used
    to render into the same #activity-feed container independently — on
    admin_dashboard.html (which has an #activity-filter-bar), the unfiltered/
    unpaginated top-10 payload from /api/admin/dashboard would win the race on
    every load AND on every 5-minute auto-refresh, silently discarding any
    filter or page the user had applied while the pagination footer (which
    only ActivityFilterBar updates) kept claiming the filtered view was still
    active. AdminDashboard must defer to ActivityFilterBar whenever it's
    present on the page."""
    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'if (!document.getElementById("activity-filter-bar")) {' in source
    guard_index = source.index('if (!document.getElementById("activity-filter-bar")) {')
    call_index = source.index("this.renderActivityFeed(normalized.recent_activity);")
    assert guard_index < call_index < guard_index + 200


def test_dashboard_card_collections_are_enumerable_lists_with_real_headings():
    """USWDS card component rules: repeated/similar cards must be grouped in
    a <ul> with each card as an <li> so screen readers can enumerate the
    collection, and each card needs a real heading in logical outline order
    (not a plain <div> standing in for one). Covers both card collections on
    /admin/dashboard: the Mission KPI cards and the 4+ Quick Action cards."""
    template = ADMIN_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r'<ul\s+class="[^"]*admin-mission-kpi-grid[^"]*"\s+id="mission-kpi-cards"[^>]*role="list"', template), \
        "mission KPI cards must be an enumerable list"
    assert re.search(r'<ul\s+class="admin-quick-actions"\s+role="list"', template)
    # Each quick-action <a> must be wrapped in its own <li>
    assert template.count("<li><a") >= 4

    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'const card = document.createElement("li");' in source
    assert 'const titleEl = document.createElement("h3");' in source
    # The old role="region"/aria-label duplicate-of-heading pattern must not
    # come back once the card has a real heading providing its accessible name.
    assert 'card.setAttribute("role", "region")' not in source


def test_system_alerts_css_classes_match_what_the_js_actually_renders():
    """admin_dashboard.js's createAlertItem/_createFeedItem has always
    emitted admin-alert-item/admin-alert-{severity}/admin-alert-icon/
    admin-alert-content/admin-alert-message/admin-alert-time, but
    admin_design_system.css defined a bare .alert-item/.alert-{severity}/
    .alert-icon/.alert-content/.alert-message/.alert-time block that never
    matched anything — every System Alerts card rendered with a fully
    transparent background and zero padding regardless of severity
    (verified live: computed background was rgba(0,0,0,0)). Also covers the
    "error" severity gap: get_admin_dashboard emits severity="error" for
    expired licenses and high incident counts, but neither the old nor a
    naively-renamed mapping had an admin-alert-error rule or icon at all."""
    css = ADMIN_DESIGN_SYSTEM_CSS.read_text(encoding="utf-8")
    for cls in (
        ".admin-alert-item", ".admin-alert-critical", ".admin-alert-error",
        ".admin-alert-warning", ".admin-alert-info", ".admin-alert-success",
        ".admin-alert-icon", ".admin-alert-content", ".admin-alert-message",
        ".admin-alert-time",
    ):
        assert cls in css, f"missing CSS rule for {cls}"
    # The stale bare-prefix rules must not silently come back as dead weight.
    assert not re.search(r"(?<!-)\.alert-item\b", css)

    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert '"bi bi-exclamation-triangle-fill"' in source
    match = re.search(r"getAlertIcon\(severity\)\s*\{(?P<body>.*?)\n  \}", source, re.DOTALL)
    assert match, "could not find getAlertIcon()"
    assert "error:" in match.group("body"), "getAlertIcon must handle severity='error'"


def test_failed_status_badge_has_a_color_rule():
    """activity-status-badge.badge-failed had no CSS rule at all (only
    badge-success/-warning/-danger/-info existed), even though
    _activity_item_from_log sets status="failed" (not "danger") for
    LOGIN_FAILED/ACCESS_DENIED/etc. Verified live: a failed-login badge
    computed to a fully transparent background — no color coding at all
    next to a correctly-styled green "success" badge."""
    css = COMPONENTS_CSS.read_text(encoding="utf-8")
    assert ".activity-status-badge.badge-failed" in css


def test_kpi_warning_icon_meets_non_text_contrast_minimum():
    """--color-warning (#F59E0B) gives a white icon glyph only 2.15:1
    contrast, failing WCAG 1.4.11 non-text contrast (3:1 minimum) for the
    KPI card that uses color: "warning". --color-warning-dark (#B45309)
    gives 5.02:1."""
    css = ADMIN_DESIGN_SYSTEM_CSS.read_text(encoding="utf-8")
    match = re.search(r"\.admin-kpi-card-warning\s*\{(?P<body>[^}]+)\}", css)
    assert match
    assert "var(--color-warning-dark)" in match.group("body")


def test_activity_search_placeholder_meets_contrast_minimum():
    """Chrome/Edge's default placeholder gray (#757575) computed to only
    4.4:1 against .admin-activity-filter-input's background (#F8FAFC),
    just under the 4.5:1 WCAG AA minimum for normal text — verified live via
    getComputedStyle(el, '::placeholder'). --color-gray-500 gives 4.62:1."""
    css = ADMIN_DESIGN_SYSTEM_CSS.read_text(encoding="utf-8")
    match = re.search(r"\.admin-activity-filter-input::placeholder\s*\{(?P<body>[^}]+)\}", css)
    assert match, "no explicit ::placeholder rule for .admin-activity-filter-input"
    assert "var(--color-gray-500)" in match.group("body")
