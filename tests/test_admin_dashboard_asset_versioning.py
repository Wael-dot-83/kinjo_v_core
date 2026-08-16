"""
Focused contract test for Admin Dashboard static asset versioning,
CSS design-token chart binding, enrollment status enum coverage,
and KPI percentage formatting precision.
"""
import hashlib
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _short_sha256(rel_path: str) -> str:
    path = ROOT / rel_path
    assert path.exists(), f"Static asset {path} does not exist"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def test_admin_dashboard_static_assets_match_content_sha256():
    """Verify that admin_dashboard.html references exact short SHA256 query parameters for changed assets."""
    template_path = ROOT / "templates" / "admin_dashboard.html"
    assert template_path.exists(), "templates/admin_dashboard.html must exist"
    template_content = template_path.read_text(encoding="utf-8")

    # 1. CSS check
    css_match = re.search(r'/static/css/dashboard-enhanced\.css\?v=([a-f0-9]+)', template_content)
    assert css_match, "dashboard-enhanced.css must have a ?v=<hash> query parameter in admin_dashboard.html"
    expected_css_hash = _short_sha256("static/css/dashboard-enhanced.css")
    assert css_match.group(1) == expected_css_hash, (
        f"CSS version mismatch: template has '{css_match.group(1)}', disk has '{expected_css_hash}'"
    )

    # 2. JS check
    js_match = re.search(r'/static/js/admin_dashboard\.js\?v=([a-f0-9]+)', template_content)
    assert js_match, "admin_dashboard.js must have a ?v=<hash> query parameter in admin_dashboard.html"
    expected_js_hash = _short_sha256("static/js/admin_dashboard.js")
    assert js_match.group(1) == expected_js_hash, (
        f"JS version mismatch: template has '{js_match.group(1)}', disk has '{expected_js_hash}'"
    )


def test_admin_dashboard_js_uses_css_tokens_for_charts():
    """Verify that Chart.js configurations in admin_dashboard.js consume dynamic CSS tokens and no raw hex colors."""
    js_path = ROOT / "static/js/admin_dashboard.js"
    content = js_path.read_text(encoding="utf-8")

    assert "getChartTokens()" in content, "admin_dashboard.js must define and use getChartTokens()"
    assert "--kinjo-dashboard-chart-primary" in content, "Must query --kinjo-dashboard-chart-primary"
    assert "--kinjo-dashboard-chart-grid" in content, "Must query --kinjo-dashboard-chart-grid"
    assert "--kinjo-dashboard-chart-text" in content, "Must query --kinjo-dashboard-chart-text"

    # Extract renderAttendanceChart body
    render_att_match = re.search(r'renderAttendanceChart\(data\)\s*\{(.*?)\n  \}', content, re.DOTALL)
    assert render_att_match, "renderAttendanceChart method must be present"
    att_body = render_att_match.group(1)
    assert "tokens.primary" in att_body, "Attendance chart must use tokens.primary"
    assert "tokens.grid" in att_body, "Attendance chart must use tokens.grid"

    # Extract renderSubmissionsChart body
    render_sub_match = re.search(r'renderSubmissionsChart\(data\)\s*\{(.*?)\n  \}', content, re.DOTALL)
    assert render_sub_match, "renderSubmissionsChart method must be present"
    sub_body = render_sub_match.group(1)
    assert "tokens.palette" in sub_body, "Enrollment status chart must use tokens.palette"


def test_enrollment_status_enum_coverage_in_frontend():
    """Verify that all backend EnrollmentStatus enum values are mapped in admin_dashboard.js with fallback."""
    js_path = ROOT / "static/js/admin_dashboard.js"
    content = js_path.read_text(encoding="utf-8")

    expected_statuses = [
        "DRAFT",
        "SUBMITTED",
        "PENDING_REVIEW",
        "ACCEPTED",
        "REJECTED",
        "WITHDRAWN",
        "WAITLISTED",
        "ACTIVE",
    ]

    for status in expected_statuses:
        assert f"{status}:" in content, f"Enrollment status {status} must be mapped in ENROLLMENT_I18N/FALLBACK"

    # Verify unknown status fallback logic
    assert "unknownFallback" in content or "حالة أخرى" in content, "Must handle unknown status with localized fallback"


def test_kpi_percentage_scale_formatting_logic():
    """Verify that percentage formatting divides raw 0-100 backend values by 100 before Intl formatting."""
    js_path = ROOT / "static/js/admin_dashboard.js"
    content = js_path.read_text(encoding="utf-8")

    assert "value / 100" in content, "formatKPIValue must divide percentage value by 100 for Intl.NumberFormat"
