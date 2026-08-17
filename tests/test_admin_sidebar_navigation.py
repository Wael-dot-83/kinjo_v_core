import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
FRONTEND_MODULES = [
    ROOT / "scripts" / "compat" / "frontend_orig.py",
    ROOT / "daily_report_analytics.py",
    ROOT / "frontend_agency_reports.py",
]
ADMIN_CSS = ROOT / "static" / "css" / "admin_design_system.css"
TOP_MENU_CSS = ROOT / "static" / "css" / "top-menu.css"

EXPECTED_WORKSPACES_AR = [
    "مركز القيادة",
    "الحضانات والشبكة",
    "التحليلات والتقارير",
    "المستخدمون والصلاحيات",
    "الحوكمة والتدقيق",
]

EXPECTED_WORKSPACES_EN = [
    "Command Center",
    "Nurseries & Network",
    "Intelligence & Reporting",
    "Users & Access",
    "Governance & Audit",
]

EXPECTED_ARABIC_LABEL_ORDER = [
    # 1. Command Center
    "مركز القيادة", "لوحة التحكم الإدارية", "مراقبة النظام", "التنبيهات",
    # 2. Nurseries & Network
    "الحضانات والشبكة", "نظرة عامة على الحضانات", "سجل الحضانات", "التحليل الجغرافي",
    "بيانات الحضانات المستوردة", "استيراد الحضانات", "سجل الاستيراد",
    # 3. Intelligence & Reporting
    "التحليلات والتقارير", "نظرة عامة على التحليلات", "مؤشرات أداء الشبكة",
    "مستكشف الرسوم البيانية", "دعم القرار", "مركز التقارير",
    "تنظيم التقارير اليومية", "تحليلات التقارير اليومية", "تقارير الحوادث",
    "تحليلات الحوادث", "تقارير الجهات الرسمية", "التصنيف والمقارنات",
    # 4. Users & Access
    "المستخدمون والصلاحيات", "المستخدمون", "استيراد المستخدمين",
    "الدخول المقيّد بصفة مستخدم", "الرسائل", "إنشاء رسالة", "رسائل التواصل",
    # 5. Governance & Audit
    "الحوكمة والتدقيق", "حوكمة التقارير اليومية", "تذكيرات الالتزام",
    "سجل التدقيق", "الملف الشخصي للمسؤول", "إعدادات النظام", "مركز المساعدة",
]

EXPECTED_VISIBLE_HREFS = [
    "/admin/dashboard", "/admin/observability", "/admin/alerts",
    "/admin/kg-overview", "/admin/kindergartens", "/admin/heatmap",
    "/admin/imported-kindergartens", "/admin/import-kindergartens", "/admin/import-logs",
    "/admin/analytics", "/admin/kpi", "/admin/analytics/charts",
    "/admin/analytics/decision-support", "/admin/analytics/reports",
    "/admin/daily-reports-organization", "/reports/analytics",
    "/admin/reports/incidents", "/admin/safety-analytics",
    "/admin/agency-reports", "/admin/classification",
    "/admin/users", "/admin/users/import", "/admin/impersonate",
    "/admin/messages", "/admin/messages/compose", "/admin/contact-messages",
    "/admin/governance-reports", "/admin/governance/reminders",
    "/admin/audit-logs", "/admin/profile", "/admin/settings", "/admin/help",
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


def test_admin_navigation_five_primary_workspaces_defined():
    sidebar = _admin_sidebar_source()
    for ws_ar, ws_en in zip(EXPECTED_WORKSPACES_AR, EXPECTED_WORKSPACES_EN):
        assert f'"label_ar": "{ws_ar}"' in sidebar, f"Missing Arabic workspace: {ws_ar}"
        assert f'"label_en": "{ws_en}"' in sidebar, f"Missing English workspace: {ws_en}"


def test_admin_sidebar_arabic_structure_matches_required_order():
    sidebar = _admin_sidebar_source()
    positions = []
    for label in EXPECTED_ARABIC_LABEL_ORDER:
        marker = f'"label_ar": "{label}"'
        assert sidebar.count(marker) == 1, f"Expected 1 marker for {label}, found {sidebar.count(marker)}"
        positions.append(sidebar.index(marker))
    assert positions == sorted(positions), "Arabic label order does not match expected sequence"
    assert '"label_ar": "السياسات"' not in sidebar
    assert '"label_ar": "الامتثال"' not in sidebar


def test_admin_sidebar_visible_links_are_exact_unique_and_registered():
    sidebar = _admin_sidebar_source()
    visible_hrefs = re.findall(r'"href":\s*"([^"]+)"', sidebar)
    assert visible_hrefs == EXPECTED_VISIBLE_HREFS
    assert CONTEXTUAL_OR_ALIAS_HREFS.isdisjoint(visible_hrefs)
    assert len(visible_hrefs) == len(set(visible_hrefs))

    frontend_source = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND_MODULES)
    registered_get_routes = set(
        re.findall(r'@(?:frontend_)?router\.get\("([^"]+)"', frontend_source)
    )
    for href in visible_hrefs:
        assert href in registered_get_routes, f"Href {href} is not registered in frontend routers"


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


def test_admin_mobile_navigation_drawer_and_toggle_present():
    base_html = ADMIN_BASE.read_text(encoding="utf-8")
    assert 'id="adminMobileNavToggle"' in base_html
    assert 'id="adminMobileDrawer"' in base_html
    assert 'id="adminMobileBackdrop"' in base_html
    assert 'id="adminMobileDrawerClose"' in base_html
    assert 'aria-controls="adminMobileDrawer"' in base_html


def test_top_menu_css_has_mobile_drawer_and_logical_properties():
    css = TOP_MENU_CSS.read_text(encoding="utf-8")
    assert ".admin-top-nav" in css
    assert ".top-menu" in css
    assert ".mobile-nav-drawer" in css
    assert ".mobile-nav-backdrop" in css
    assert ".mobile-nav-toggle-btn" in css
    assert "inset-inline-start" in css
    assert '[dir="rtl"] .mobile-nav-drawer' in css
    assert '[dir="ltr"] .mobile-nav-drawer' in css
