"""
Focused contract test for Admin Dashboard static asset versioning,
CSS design-token chart binding, enrollment status enum coverage,
and KPI percentage formatting precision.
"""
import hashlib
import re
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _short_sha256(rel_path: str) -> str:
    path = ROOT / rel_path
    assert path.exists(), f"Static asset {path} does not exist"
    # Canonical (committed) bytes -- see test_design_system_budgets.canonical_asset_hash.
    return hashlib.sha256(
        path.read_bytes().replace(bytes([13, 10]), bytes([10]))
    ).hexdigest()[:12]


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
    assert "--kinjo-dashboard-chart-tooltip-bg" in content, "Must query --kinjo-dashboard-chart-tooltip-bg"
    assert "--kinjo-dashboard-chart-tooltip-text" in content, "Must query --kinjo-dashboard-chart-tooltip-text"
    assert "--kinjo-dashboard-chart-point-border" in content, "Must query --kinjo-dashboard-chart-point-border"

    # Extract renderAttendanceChart body
    render_att_match = re.search(r'renderAttendanceChart\(data\)\s*\{(.*?)\n  \}', content, re.DOTALL)
    assert render_att_match, "renderAttendanceChart method must be present"
    att_body = render_att_match.group(1)
    assert "tokens.primary" in att_body, "Attendance chart must use tokens.primary"
    assert "tokens.grid" in att_body, "Attendance chart must use tokens.grid"
    assert "tokens.tooltipBackground" in att_body, "Attendance chart tooltip must use tokens.tooltipBackground"
    assert "tokens.tooltipText" in att_body, "Attendance chart tooltip must use tokens.tooltipText"
    assert "tokens.pointBorder" in att_body, "Attendance chart points must use tokens.pointBorder"
    assert "tokens.gradientFade" in att_body, "Attendance chart gradient must use tokens.gradientFade"

    # Extract renderSubmissionsChart body
    render_sub_match = re.search(r'renderSubmissionsChart\(data\)\s*\{(.*?)\n  \}', content, re.DOTALL)
    assert render_sub_match, "renderSubmissionsChart method must be present"
    sub_body = render_sub_match.group(1)
    assert "tokens.palette" in sub_body, "Enrollment status chart must use tokens.palette"
    assert "tokens.tooltipBackground" in sub_body, "Enrollment chart tooltip must use tokens.tooltipBackground"
    assert "tokens.tooltipText" in sub_body, "Enrollment chart tooltip must use tokens.tooltipText"

    # No raw hex/rgb/rgba color literals in Chart.js config objects
    # (getChartTokens fallbacks are excluded — they follow the existing pattern)
    chart_config_sections = att_body + sub_body
    raw_color_pattern = re.compile(r'"(#[0-9a-fA-F]{3,8}|rgba?\()')
    raw_matches = raw_color_pattern.findall(chart_config_sections)
    assert not raw_matches, (
        f"Raw color literals found in chart configs: {raw_matches}. "
        "All Chart.js colors must come from getChartTokens()."
    )


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


def test_admin_dashboard_css_has_tooltip_tokens():
    """Verify that dashboard-enhanced.css defines tooltip custom properties."""
    css_path = ROOT / "static/css/dashboard-enhanced.css"
    content = css_path.read_text(encoding="utf-8")

    assert "--kinjo-dashboard-chart-tooltip-bg" in content, "Missing tooltip background token"
    assert "--kinjo-dashboard-chart-tooltip-text" in content, "Missing tooltip text token"
    assert "--kinjo-dashboard-chart-point-border" in content, "Missing point border token"


def test_admin_dashboard_js_no_undefined_sanitizehtml():
    """Verify that sanitizeHTML is not called in admin_dashboard.js (it was never defined)."""
    js_path = ROOT / "static/js/admin_dashboard.js"
    content = js_path.read_text(encoding="utf-8")

    assert "sanitizeHTML" not in content, "sanitizeHTML is not defined and must not be called"


def test_unknown_enrollment_status_runtime():
    """Execute the real JS normalizePayload path with an unknown enrollment status.

    This test runs a Node.js script that loads admin_dashboard.js and calls
    normalizePayload with MANUAL_REVIEW_REQUIRED as an unknown status.
    It must pass after the correction and fail before it (ReferenceError on sanitizeHTML).
    """
    test_script = ROOT / "tests" / "runtime" / "js_unknown_enrollment_status.test.js"
    assert test_script.exists(), f"Runtime test script not found: {test_script}"

    result = subprocess.run(
        ["node", str(test_script)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )

    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        pytest.fail(f"Runtime JS test failed with exit code {result.returncode}")

    assert "PASS" in result.stdout, f"Runtime test did not pass. Output: {result.stdout}"
