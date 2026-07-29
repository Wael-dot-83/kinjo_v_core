import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
FRONTEND_MODULES = [
    ROOT / "scripts" / "compat" / "frontend_orig.py",
    ROOT / "daily_report_analytics.py",
    ROOT / "frontend_agency_reports.py",
    # Guided analytics registers its page on a dedicated `page_router`
    # (main.py includes it as analytics_explorer_page_router). Without this entry
    # the registration check below could not see /admin/analytics/explorer and
    # would have reported a live, reachable page as an unregistered dead link.
    ROOT / "analytics_explorer.py",
]
ADMIN_CSS = ROOT / "static" / "css" / "admin_design_system.css"

# Canonical Admin navigation, kept in the order the product decided on.
#
# Two deliberate changes landed in templates/admin_base.html after 7cd5f69 (the
# commit that last updated template and test together) and were never reflected
# here, which is why the order assertions below had drifted:
#
#   de5a00a "feat(admin): promote Geographic Analysis, widen logo, …" and
#   d0f1130 "feat(admin): move Geographic Analysis under the Overview menu"
#       moved التحليل الجغرافي (/admin/heatmap) out of العمليات والسلامة and up
#       into نظرة عامة.
#
#   8b4813a "feat(analytics): complete guided explorer — navigation, …"
#       added التحليلات الموجَّهة (/admin/analytics/explorer) under
#       التحليلات والتقارير. The page is live and returns 200.
#
# The lists are re-pinned to that intended order rather than the template being
# reordered back: the commit titles above are explicit product decisions. The
# assertions themselves are unchanged — exact order, exact membership, no
# duplicates, and every href a registered GET route.
EXPECTED_ARABIC_LABEL_ORDER = [
    "نظرة عامة", "لوحة التحكم الإدارية", "التحليل الجغرافي", "مراقبة النظام",
    "التنبيهات",
    "الأشخاص والجهات", "المستخدمون", "استيراد المستخدمين",
    "نظرة عامة على الحضانات", "سجل الحضانات", "التواصل والبيانات",
    "الرسائل", "إنشاء رسالة", "رسائل التواصل", "بيانات الحضانات المستوردة",
    "استيراد الحضانات", "سجل الاستيراد", "العمليات والسلامة",
    "تقارير الحوادث", "تحليلات الحوادث",
    "التحليلات والتقارير", "نظرة عامة على التحليلات", "مؤشرات أداء الشبكة",
    "مركز التقارير", "دعم القرار", "تنظيم التقارير اليومية",
    "تحليلات التقارير اليومية", "التحليلات الموجَّهة", "مستكشف الرسوم البيانية",
    "الحوكمة", "حوكمة التقارير اليومية",
    "تذكيرات الالتزام", "التصنيف والمقارنات", "تقارير الجهات الرسمية",
    "الأمان والحساب",
    "سجل التدقيق", "الدخول المقيّد بصفة مستخدم", "الملف الشخصي للمسؤول",
    "إعدادات النظام", "مركز المساعدة",
]

EXPECTED_VISIBLE_HREFS = [
    "/admin/dashboard", "/admin/heatmap", "/admin/observability", "/admin/alerts",
    "/admin/users", "/admin/users/import", "/admin/kg-overview",
    "/admin/kindergartens", "/admin/messages", "/admin/messages/compose",
    "/admin/contact-messages", "/admin/imported-kindergartens",
    "/admin/import-kindergartens", "/admin/import-logs",
    "/admin/reports/incidents", "/admin/safety-analytics",
    "/admin/analytics", "/admin/kpi", "/admin/analytics/reports",
    "/admin/analytics/decision-support", "/admin/daily-reports-organization",
    "/reports/analytics", "/admin/analytics/explorer", "/admin/analytics/charts",
    "/admin/governance-reports", "/admin/governance/reminders",
    "/admin/classification", "/admin/agency-reports",
    "/admin/audit-logs", "/admin/impersonate",
    "/admin/profile", "/admin/settings", "/admin/help",
]

CONTEXTUAL_OR_ALIAS_HREFS = {
    "/admin/users/create", "/admin/kindergartens/new",
    "/admin/reports/incidents/generate", "/admin/analytics/daily-reports",
    "/admin/heatmap#governorates",
}


def _admin_sidebar_source() -> str:
    source = ADMIN_BASE.read_text(encoding="utf-8")
    idx = source.index('id="admin-sidebar"')
    start = source.rindex("<aside", 0, idx)
    return source[start:source.index("</aside>", start)]


def test_admin_sidebar_arabic_structure_matches_required_order():
    sidebar = _admin_sidebar_source()
    positions = []
    for label in EXPECTED_ARABIC_LABEL_ORDER:
        marker = f'"label_ar": "{label}"'
        assert sidebar.count(marker) == 1, label
        positions.append(sidebar.index(marker))
    assert positions == sorted(positions)
    assert '"label_ar": "السياسات"' not in sidebar
    assert '"label_ar": "الامتثال"' not in sidebar


def test_admin_sidebar_visible_links_are_exact_unique_and_registered():
    sidebar = _admin_sidebar_source()
    visible_hrefs = re.findall(r'"href":\s*"([^"]+)"', sidebar)
    assert visible_hrefs == EXPECTED_VISIBLE_HREFS
    assert CONTEXTUAL_OR_ALIAS_HREFS.isdisjoint(visible_hrefs)
    assert len(visible_hrefs) == len(set(visible_hrefs))

    frontend_source = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND_MODULES)
    # `page_router` is included too: analytics_explorer.py registers its Admin page
    # on a dedicated router (main.py: analytics_explorer_page_router), so matching
    # only `router`/`frontend_router` would miss a route that genuinely exists.
    registered_get_routes = set(
        re.findall(r'@(?:frontend_|page_)?router\.get\("([^"]+)"', frontend_source)
    )
    for href in visible_hrefs:
        assert href in registered_get_routes, href


def test_exact_navigation_match_precedes_contextual_prefixes():
    sidebar = _admin_sidebar_source()
    assert re.search(r"nav_state\s*=\s*namespace\(\s*exact_match\s*=\s*false\s*\)", sidebar)
    assert re.search(r"current_path\s*==\s*item\.href", sidebar)
    assert re.search(r"not\s+nav_state\.exact_match\s+and\s+current_path\s+in\s+item\.active_paths", sidebar)


def test_admin_sidebar_markup_avoids_legacy_i18n_and_bad_link_roles():
    sidebar = _admin_sidebar_source()
    match = re.search(r"<nav\b[^>]*>.*?</nav>", sidebar, re.DOTALL)
    assert match, "nav element not found"
    nav = match.group(0)
    assert 'data-i18n="' not in nav
    assert not re.search(r'<a\b[^>]*\brole="listitem"', nav)
    assert 'aria-current="page"' in nav


def test_admin_sidebar_css_is_scoped_and_rtl_ready():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    assert "--admin-sidebar-width: 280px;" in css
    assert ".admin-sidebar .nav-link span" in css
    assert 'html[dir="rtl"] .admin-sidebar .nav-link.active' in css
    assert ".admin-sidebar .submenu .nav-link.active" in css
