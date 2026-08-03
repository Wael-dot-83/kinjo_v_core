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


def test_admin_dashboard_allows_slow_but_valid_responses():
    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert "const timeoutId = setTimeout(() => controller.abort(), 30000);" in source


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
    assert source.count('showCanvasFallback(chartEl, dsText("ds.no_data"));') >= 4


def test_analytics_filter_bar_sticks_to_scrollport_top():
    """The analytics filter bar must pin flush to the top of .admin-content.

    .admin-content is the real scroll container (the header sits outside it).
    `top: 0` pins the bar at the scroller's content edge — i.e. flush with the
    visible top, since the scroller's own padding is above it. The earlier
    `top: calc(-1 * var(--kinjo-spacing-6))` offset made the bar stick only
    after scrolling past the container top, so it appeared to never pin.
    """
    css = ANALYTICS_V2_CSS.read_text(encoding="utf-8")
    match = re.search(r"\.glass-filter-bar\s*\{(?P<body>[^}]+)\}", css)
    assert match is not None
    body = match.group("body")
    assert re.search(r"position\s*:\s*sticky", body)
    assert re.search(r"top\s*:\s*0\b", body)
    assert not re.search(r"top\s*:\s*calc\(-1", body)
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
    stale_filter_pattern = re.search(r"function updateRiskRadar.*?(?=\nfunction )", admin_analytics, re.S)
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
    # 3 in the trend chart + 1 in the scenarios chart (Phase 4). What matters is
    # that every padding array goes through the Math.max(0, …) guard above, never
    # the raw dataSeries.length - 1.
    assert source.count("new Array(paddingLength)") == 4


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
    # Phase 4 split these into two idle-scheduled parallel batches
    # (loadSecondaryWidgets + loadTertiaryWidgets), each dispatched via
    # Promise.allSettled. The parallel-not-sequential guarantee is unchanged —
    # assert the union of every allSettled batch still contains all 9 widgets.
    bodies = re.findall(r"Promise\.allSettled\(\[(.*?)\]\);", source, re.S)
    assert bodies, "secondary widget loaders must be dispatched via Promise.allSettled"
    combined = "\n".join(bodies)
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
        assert call in combined, f"missing from parallel batches: {call}"

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
    assert (
        'localStorage.setItem(\n        "autoRefreshEnabled"' in source
        or 'localStorage.setItem("autoRefreshEnabled"' in source
    )
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
    /admin/dashboard: the 7 KPI cards and the 4 Quick Action cards."""
    template = ADMIN_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r'<ul\s+class="[^"]*\badmin-dashboard-cards\b[^"]*"\s+id="kpi-cards"[^>]*role="list"', template)
    assert re.search(r'<ul\s+class="[^"]*\badmin-quick-actions\b[^"]*"\s+role="list"', template)
    # Each quick-action <a> must be wrapped in its own <li>
    assert template.count("<li><a") >= 4

    source = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'const card = document.createElement("li");' in source
    assert 'const titleEl = document.createElement("h3");' in source
    # The old role="region"/aria-label duplicate-of-heading pattern must not
    # come back once the card has a real heading providing its accessible name.
    assert 'card.setAttribute("role", "region")' not in source


def test_admin_dashboard_has_scoped_uswds_redesign_shell_without_losing_hooks():
    """The USWDS-inspired dashboard shell must stay scoped and preserve JS hooks."""
    template = ADMIN_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")

    assert "/static/vendor/uswds/css/uswds.min.css" in template
    assert "admin-uswds-dashboard usa-section" in template
    assert "agency-reports-dashboard-section usa-summary-box" in template
    assert "admin-page-header usa-prose" in template
    assert "admin-dashboard-cards usa-card-group" in template
    assert "admin-quick-actions usa-card-group" in template
    for hook in (
        'id="admin-dashboard"',
        'id="dashboard-loading"',
        'id="dashboard-error"',
        'id="dashboard-content"',
        'id="kpi-cards"',
        'id="activity-feed"',
        'id="refresh-dashboard"',
    ):
        assert hook in template


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
        ".admin-alert-item",
        ".admin-alert-critical",
        ".admin-alert-error",
        ".admin-alert-warning",
        ".admin-alert-info",
        ".admin-alert-success",
        ".admin-alert-icon",
        ".admin-alert-content",
        ".admin-alert-message",
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


def test_kpi_count_up_respects_reduced_motion():
    """The requestAnimationFrame KPI count-up must not run for users who
    requested reduced motion (WCAG 2.3.3) — the CSS fade-up is guarded, so the
    JS animation must be too."""
    js = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    match = re.search(r"animateCountUp\([^)]*\)\s*\{(?P<body>.*?)\n  \}", js, re.S)
    assert match, "animateCountUp not found"
    body = match.group("body")
    assert "prefers-reduced-motion: reduce" in body
    assert "matchMedia" in body


def test_dashboard_chart_aria_labels_are_bilingual():
    """Chart canvas accessible names must be localized — an Arabic-primary app
    must not announce English-only aria-labels to screen readers.

    The accessible name must also describe the data the chart actually plots.
    This test previously pinned "User activity chart showing active users over
    time" for the `attendance-chart` canvas, but that series is
    `AttendanceLog` rows with status PRESENT grouped by date
    (admin_endpoints.py, `attendance_chart`) — no user or login data is
    involved. The old name announced attendance figures to screen-reader users
    as user activity, i.e. it was sighted-user-invisible misinformation.
    """
    js = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    # English kept, Arabic added for both charts.
    assert "Daily attendance chart showing recorded attendance by date" in js
    assert "مخطط الحضور اليومي" in js
    assert "Enrollment status chart showing distribution of application statuses" in js
    assert "مخطط حالة التسجيل" in js


def test_component_guide_falls_back_to_a_real_anchor():
    """Kilo's injected 'About this dashboard' guide anchored only on
    .admin-dashboard-guide, which the template does not ship — so it silently
    never rendered. It must fall back to #kpi-cards so the feature works."""
    js = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    match = re.search(r"renderComponentGuide\(\)\s*\{(?P<body>.*?)\n  \}", js, re.S)
    assert match, "renderComponentGuide not found"
    body = match.group("body")
    assert 'getElementById("kpi-cards")' in body
    assert "beforebegin" in body


def test_relative_time_uses_intl_and_adaptive_cadence():
    """The 'updated X ago' timestamp must use Intl.RelativeTimeFormat (correct
    Arabic dual/plural + Arabic-Indic numerals) and an adaptive ticker cadence
    so the seconds reading is not stuck at a coarse 30s interval."""
    js = ADMIN_DASHBOARD_JS.read_text(encoding="utf-8")
    assert "Intl.RelativeTimeFormat" in js
    # No hardcoded singular Arabic unit interpolation remains.
    assert "${sec} ثانية" not in js.replace("`قبل ${sec} ثانية`", "")  # only the catch fallback
    # Adaptive cadence (not a fixed 30000 interval).
    assert "setInterval(() => this._renderRelativeTime(), 30000)" not in js
    assert "sec < 60 ? 5000" in js
