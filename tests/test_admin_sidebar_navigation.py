import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
FRONTEND = ROOT / "frontend.py"
ADMIN_CSS = ROOT / "static" / "css" / "admin_design_system.css"

EXPECTED_ARABIC_LABEL_ORDER = [
    "لوحة التحكم",
    "المساعدة",
    "إدارة النظام",
    "المستخدمون",
    "التواصل",
    "الحضانات",
    "البيانات",
    "العمليات",
    "سجل الحوادث",
    "تقارير الحوادث",
    "التقارير والتحليل",
    "نظرة عامة على التحليلات",
    "التقارير المفصلة",
    "تقارير الدعم القرارى",
    "التقارير اليومية",
    "جدولة التقارير",
    "نظرة عامة على الخريطة",
    "تحليل المحافظات",
    "الحوكمة",
    "السياسات",
    "الامتثال",
    "الإعدادات",
    "إعدادات النظام",
    "السجلات",
]

EXPECTED_VISIBLE_HREFS = [
    "/admin/dashboard",
    "/admin/help",
    "/admin/users",
    "/admin/messages",
    "/admin/kg-overview",
    "/admin/imported-kindergartens",
    "/admin/reports/incidents",
    "/admin/reports/incidents/generate",
    "/admin/analytics",
    "/admin/analytics/reports",
    "/admin/analytics/decision-support",
    "/admin/analytics/daily-reports",
    "/admin/daily-reports-organization",
    "/admin/heatmap",
    "/admin/heatmap#governorates",
    "/admin/governance-reports",
    "/admin/classification",
    "/admin/settings",
    "/admin/audit-logs",
]

REMOVED_VISIBLE_HREFS = {
    "/admin/users/create",
    "/admin/users/import",
    "/admin/messages/compose",
    "/admin/contact-messages",
    "/admin/import-kindergartens",
    "/admin/import-logs",
    "/admin/governance/reminders",
    "/admin/alerts",
    "/admin/safety-analytics",
    "/admin/impersonate",
    "/admin/observability",
}


def _admin_sidebar_source() -> str:
    source = ADMIN_BASE.read_text(encoding="utf-8")
    # Locate the admin sidebar by its stable id attribute (class name may vary).
    idx = source.index('id="admin-sidebar"')
    start = source.rindex("<aside", 0, idx)
    return source[start : source.index("</aside>", start)]


def test_admin_sidebar_arabic_structure_matches_required_order():
    sidebar = _admin_sidebar_source()
    positions = []

    for label in EXPECTED_ARABIC_LABEL_ORDER:
        marker = f'"label_ar": "{label}"'
        assert sidebar.count(marker) == 1, label
        positions.append(sidebar.index(marker))

    assert positions == sorted(positions)
    assert '"label_ar": "لوحة التحكم العامة"' not in sidebar
    assert '"label_ar": "نظرة عامة"' not in sidebar


def test_admin_sidebar_visible_links_are_exact_and_registered():
    sidebar = _admin_sidebar_source()
    visible_hrefs = re.findall(r'"href":\s*"([^"]+)"', sidebar)

    assert visible_hrefs == EXPECTED_VISIBLE_HREFS
    assert REMOVED_VISIBLE_HREFS.isdisjoint(visible_hrefs)

    frontend_source = FRONTEND.read_text(encoding="utf-8")
    registered_get_routes = set(re.findall(r'@router\.get\("([^"]+)"', frontend_source))

    for href in visible_hrefs:
        route_path = href.split("#", 1)[0]
        assert route_path in registered_get_routes, route_path


def test_admin_sidebar_markup_avoids_legacy_i18n_and_bad_link_roles():
    sidebar = _admin_sidebar_source()
    nav = sidebar[sidebar.index("<nav ") : sidebar.index("</nav>")]

    assert 'data-i18n="' not in nav
    assert not re.search(r"<a\b[^>]*\brole=\"listitem\"", nav)
    assert 'aria-current="page"' in nav


def test_admin_sidebar_css_is_scoped_and_rtl_ready():
    css = ADMIN_CSS.read_text(encoding="utf-8")

    assert "--admin-sidebar-width: 280px;" in css
    assert ".admin-sidebar .nav-link span" in css
    assert 'html[dir="rtl"] .admin-sidebar .nav-link.active' in css
    assert ".admin-sidebar .submenu .nav-link.active" in css
