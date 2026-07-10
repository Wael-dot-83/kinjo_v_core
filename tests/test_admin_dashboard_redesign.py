"""Redesign contract tests for /admin/dashboard (section order, semantic
sections, accessibility, quick-action routes, RTL, no raw keys/mojibake)."""
import re

import pytest
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="dashredesign",
        email="dashredesign@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


VALID_QUICK_ACTION_ROUTES = {
    "/admin/users",
    "/admin/messages/compose",
    "/admin/analytics",
    "/admin/imported-kindergartens",
    "/admin/audit-logs",
    "/admin/kindergartens",
    "/admin/agency-reports",
}


@pytest.fixture
def admin_html(client, test_db):
    _create_admin(test_db)
    token = _token(client, "dashredesign")
    r = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.text


def test_dashboard_renders_for_admin(client, test_db):
    _create_admin(test_db)
    token = _token(client, "dashredesign")
    r = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_official_reports_section_before_operational_indicators(admin_html):
    assert admin_html.index("تقارير الجهات الرسمية") < admin_html.index("المؤشرات التشغيلية")


def test_required_sections_present(admin_html):
    for text in (
        "شريط حالة النظام",
        "الملخص التنفيذي",
        "التنبيهات الحرجة",
        "تقارير الجهات الرسمية",
        "المؤشرات التشغيلية",
        "نظرة عامة أمنية",
        "مسار الطلبات",
        "مركز جودة البيانات",
        "النشاطات الأخيرة",
        "الإجراءات السريعة",
    ):
        assert text in admin_html, f"missing section: {text}"


def test_sections_use_semantic_headings(admin_html):
    pairs = {
        "system-status-title": "شريط حالة النظام",
        "executive-summary-title": "الملخص التنفيذي",
        "critical-alerts-title": "التنبيهات الحرجة",
        "agency-reports-dashboard-title": "تقارير الجهات الرسمية",
        "operational-indicators-title": "المؤشرات التشغيلية",
        "security-overview-title": "نظرة عامة أمنية",
        "request-pipeline-title": "مسار الطلبات",
        "data-quality-title": "مركز جودة البيانات",
    }
    for hid, label in pairs.items():
        assert f'id="{hid}"' in admin_html, f"missing heading id {hid}"
        assert label in admin_html


def test_official_reports_section_has_container_and_header(admin_html):
    assert 'id="agency-reports-summary"' in admin_html
    assert 'aria-labelledby="agency-reports-dashboard-title"' in admin_html


def test_quick_actions_exist_and_link_valid_routes(admin_html):
    # Extract hrefs inside the quick-actions list.
    qa_block = admin_html.split('class="admin-quick-actions"', 1)[1]
    hrefs = re.findall(r'href="(/admin/[^"]+)"', qa_block)
    assert len(hrefs) >= 4, f"expected >=4 quick actions, got {hrefs}"
    for h in hrefs:
        assert h in VALID_QUICK_ACTION_ROUTES, f"quick action links to unknown route: {h}"


def test_rtl_shell_present(admin_html):
    assert 'dir="rtl"' in admin_html
    assert 'lang="ar"' in admin_html


def test_no_unrendered_template_tags(admin_html):
    assert "{{" not in admin_html
    assert "{%" not in admin_html


def test_no_mojibake(admin_html):
    assert "�" not in admin_html  # U+FFFD replacement char
    assert "â€" not in admin_html
    assert "ðŸ" not in admin_html


def test_generic_agency_logo_asset_exists():
    import os
    assert os.path.exists(os.path.join("static", "img", "official-agencies-logo.svg"))


def test_agency_logo_helper_script_loaded(admin_html):
    assert "/static/js/agency_logo.js" in admin_html
    assert "/static/js/admin_agency_reports_dashboard_summary.js" in admin_html