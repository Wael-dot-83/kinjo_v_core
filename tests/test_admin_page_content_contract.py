"""Content and metric-definition contract for all live Admin views."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dependencies import get_current_user_or_redirect
from main import app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
CONTEXT = TEMPLATES / "components" / "admin_page_context.html"


EXPECTED_ADMIN_PATHS = {
    "/admin/dashboard", "/admin/users", "/admin/users/import",
    "/admin/users/create", "/admin/kg-overview", "/admin/kindergartens",
    "/admin/kindergartens/new", "/admin/messages", "/admin/messages/compose",
    "/admin/contact-messages", "/admin/import-kindergartens",
    "/admin/imported-kindergartens", "/admin/import-logs", "/admin/analytics",
    "/admin/analytics/reports", "/admin/analytics/decision-support",
    "/admin/daily-reports-organization", "/admin/analytics/charts", "/admin/kpi",
    "/admin/governance-reports", "/admin/governance/reminders",
    "/admin/classification", "/admin/reports/incidents/generate",
    "/admin/reports/incidents", "/admin/safety-analytics", "/admin/alerts",
    "/admin/heatmap", "/admin/agency-reports", "/admin/audit-logs",
    "/admin/impersonate", "/admin/profile", "/admin/settings", "/admin/help",
    "/admin/observability",
}

EXPECTED_DYNAMIC_PREFIXES = {
    "/admin/users/", "/admin/kindergartens/", "/admin/analytics/drilldown/",
    "/admin/reports/incidents/", "/admin/agency-reports/",
}


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_page_context_is_loaded_by_admin_shell_and_compiles():
    assert '{% include "components/admin_page_context.html" %}' in source("templates/admin_base.html")
    Environment(loader=FileSystemLoader(TEMPLATES)).get_template("admin_base.html")


def test_every_admin_route_family_has_bilingual_purpose_and_number_guidance():
    text = CONTEXT.read_text(encoding="utf-8")
    for path in EXPECTED_ADMIN_PATHS | EXPECTED_DYNAMIC_PREFIXES:
        assert f'"{path}"' in text, path
    assert text.count('"purpose_ar"') == text.count('"purpose_en"')
    assert text.count('"numbers_ar"') == text.count('"numbers_en"')
    assert text.count('"purpose_ar"') == text.count('"numbers_ar"') >= 34
    assert "Zero is a measured result" in text
    assert "الصفر نتيجة مقاسة" in text


def test_shared_daily_reports_analytics_explains_scope_and_does_not_fake_zero_loading():
    text = source("templates/reports/analytics_dashboard.html")
    assert "Results use the selected date range and kindergarten scope" in text
    assert "تستخدم النتائج الفترة والحضانة المحددتين" in text
    for element_id in ("kpiTotal", "kpiMealRate", "kpiNapAvg", "kpiSickCount"):
        assert f'id="{element_id}">—<' in text
    assert "Sleep rate" not in text
    assert "نسبة النوم" not in text
    assert "مرفوضة" in text


def test_known_misleading_page_claims_are_removed():
    settings = source("templates/admin/settings.html")
    imported = source("templates/admin/imported_kindergartens.html")
    impersonate = source("templates/admin/impersonate.html")
    profile = source("templates/admin/profile.html")
    assert "Manage global configuration" not in settings
    assert "هذه الصفحة للقراءة فقط" in settings
    assert "Manage all imported" not in imported
    assert "All Districts" in imported and "جميع الألوية" in imported
    assert "permanently recorded" not in impersonate
    assert "بشكل دائم" not in impersonate
    assert "Family &amp; Childhood Directorate" not in profile
    assert '<h1 class="profile-hero-name"' in profile


def test_profile_age_card_label_matches_what_it_computes():
    """The card shows (now - created_at).days — account age, not distinct
    active days.

    The label read "Days Active" / "أيام النشاط", which claims the admin was
    active on that many distinct days; the value is simply the account's age.
    An account created 100 days ago and used twice would read "100 Days
    Active". Same class as this branch's other fixes: a label naming a quantity
    the code does not compute. Pre-existing at origin/main, corrected here
    because it is pure content.
    """
    profile = source("templates/admin/profile.html")
    assert "Days Active" not in profile, "the card still claims distinct active days"
    assert "أيام النشاط" not in profile
    assert "Account Age (days)" in profile
    assert "عمر الحساب (بالأيام)" in profile

    # Bind the label to the computation: if the value ever becomes a genuine
    # distinct-active-days count, this guard should fail so the label is
    # revisited rather than left stale.
    frontend = source("scripts/compat/frontend_orig.py")
    assert "days_active = max(0, (now_jordan - created).days)" in frontend, (
        "days_active is no longer computed as account age; recheck the card label"
    )

    # The page-context row must describe the same thing, in both languages.
    ctx = source("templates/components/admin_page_context.html")
    assert "account age in days" in ctx
    assert "عمر الحساب بالأيام" in ctx
    assert "active days" not in ctx

    # No i18n catalogue may carry the old label as a VALUE. These four keys are
    # unconsumed (the card is Jinja-hardcoded), but four dead copies of the
    # corrected label is the half-fix pattern regardless of whether they render.
    import json as _json
    for cat in ("static/i18n/admin_en.json", "static/i18n/admin_ar.json",
                "static/i18n/en.json", "static/i18n/ar.json"):
        values = _json.dumps(_json.loads(source(cat)), ensure_ascii=False)
        assert "أيام النشاط" not in values, f"{cat} still carries the old Arabic label"
    # The English display value too (not the key, which stays as an identifier).
    assert '"stat_days_active": "Days Active"' not in source("static/i18n/admin_en.json")
    assert '"Days Active": "Days Active"' not in source("static/i18n/en.json")


def test_metric_names_match_implemented_behavior():
    assert "Average Staff-to-Child Ratio Compliance" in source("templates/admin/kpi.html")
    assert "Chart Suggestions" in source("templates/admin/analytics/charts_dashboard.html")
    heatmap = source("templates/admin/heatmap.html")
    assert "Covered Governorates" in heatmap
    # The average-risk card's wording is asserted in
    # tests/test_heatmap_partial_coverage_disclosure.py, which binds it to what
    # get_map_overview() computes (a mean over the SURVIVING governorates, since
    # failures are dropped) rather than to a string. Only the falsehood this
    # test once pinned is kept here:
    assert "Selected-scope Average Risk" not in heatmap
    dashboard_js = source("static/js/admin_dashboard.js")
    assert 'drilldown: "/admin/daily-reports-organization"' in dashboard_js
    assert 'improveLink.href = "/admin/daily-reports-organization"' in dashboard_js


def test_missing_analytics_values_render_unavailable_not_zero():
    drilldown = source("static/js/admin_analytics_drilldown.js")
    assert "function drilldownNumber" in drilldown
    assert "metrics.attendance_rate ?? 0" not in drilldown
    assert "metrics.incident_rate ?? 0" not in drilldown
    assert "metrics.governance_score ?? 0" not in drilldown


def test_kindergarten_occupancy_uses_one_population_and_preserves_unavailable():
    endpoint = source("api/kindergartens.py")
    frontend = source("static/js/admin_kindergartens.js")
    assert "active_children / total_capacity" in endpoint
    assert '"active_children": active_children' in endpoint
    assert 'd.avg_occupancy != null ? d.avg_occupancy + "%" : "—"' in frontend


def test_kindergarten_overview_has_a_visible_retryable_initial_error_state():
    template = source("templates/admin/kg_overview.html")
    script = source("static/js/kg_overview.js")
    assert 'id="ko-page-error"' in template
    assert 'id="ko-page-retry"' in template
    assert "#showLoadError(error)" in script
    assert "if (!response.ok) throw new Error" in script


def test_admin_shell_renders_route_specific_context_in_both_languages(client, admin_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        dashboard_ar = client.get("/admin/dashboard").text
        settings_en = client.get("/admin/settings?lang=en").text
    finally:
        app.dependency_overrides.clear()
    assert 'class="admin-page-context alert alert-light border mb-4"' in dashboard_ar
    assert "ملخص تنفيذي لحالة المنصة" in dashboard_ar
    assert "About this page" in settings_en
    assert "View session timeout and server-managed environment information" in settings_en


def test_manager_admin_shell_exposes_only_the_manager_available_user_link(client, manager_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
    try:
        response = client.get("/admin/users")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    page = response.text
    sidebar = page[page.index('<aside id="admin-sidebar">'):page.index("</aside>")]
    assert 'href="/admin/users"' in sidebar
    for unavailable in (
        "/admin/observability", "/admin/import-kindergartens", "/admin/impersonate",
        "/admin/governance-reports", "/admin/audit-logs", "/admin/settings",
    ):
        assert f'href="{unavailable}"' not in sidebar
