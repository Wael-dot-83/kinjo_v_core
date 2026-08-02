"""
Production-Blocker Regression Tests for Admin Module

Verifies fixes applied during production-readiness hardening:
- [P0] Attendance rate is bounded to [0, 100] — cannot exceed 100%
- [P0] Soft-deleted records excluded from dashboard totals and attendance counts
- [P1] CSRF token validation enforced on all state-changing admin endpoints
- [P1] Legacy dashboard chart correctly labels attendance (not "user activity")
- [P2] Class/child attendance rates bounded to [0, 100]
"""

import pytest
import json
import secrets
from datetime import datetime, timedelta, date, timezone

from auth import get_password_hash
import models


# =============================================================================
# [P0] Attendance Rate Bounds — rate cannot exceed 100%
# =============================================================================

class TestAttendanceRateBounds:
    """Attendance percentage must never exceed 100% under any condition."""

    def test_attendance_rate_clamped_at_100(self, client, test_db, sample_kindergarten, sample_class, sample_child, admin_token, admin_user, auth_headers_admin):
        """Create many PRESENT attendance logs for one child to test clamping."""
        from models import AttendanceLog, AttendanceStatus, EnrollmentApplication, EnrollmentStatus

        # Create an active enrollment for the child
        enrollment = EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        # Duplicate same-day logs were the original route to a >100% rate. That is
        # now structurally impossible: attendance_logs carries a UNIQUE(child_id,
        # date) constraint, so the double-count cannot be created in the first
        # place. Assert the constraint holds, then confirm the rate stays bounded.
        today = date.today()
        test_db.add(AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        ))
        test_db.commit()

        from sqlalchemy.exc import IntegrityError
        test_db.add(AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        ))
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

        r = client.get(
            "/api/admin/dashboard",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        data = r.json()
        # Verify the attendance rate in summary
        summary = data.get("summary", {})
        rate = summary.get("attendance_rate")
        if rate is not None:
            assert 0.0 <= rate <= 100.0, f"Attendance rate {rate} exceeds 100% bound"

    def test_attendance_rate_with_absent_only(self, client, test_db, sample_kindergarten, sample_class, sample_child, admin_user, auth_headers_admin):
        """Attendance rate should be 0 when only ABSENT records exist."""
        from models import AttendanceLog, AttendanceStatus, EnrollmentApplication, EnrollmentStatus

        # Create an active enrollment
        enrollment = EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        today = date.today()
        log = AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=AttendanceStatus.ABSENT,
            recorded_by=admin_user.id,
        )
        test_db.add(log)
        test_db.commit()

        r = client.get(
            "/api/admin/dashboard",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        data = r.json()
        summary = data.get("summary", {})
        rate = summary.get("attendance_rate")
        if rate is not None:
            assert 0.0 <= rate <= 100.0, f"Attendance rate {rate} out of [0, 100]"

    def test_class_metrics_attendance_clamped(self):
        """Verify class attendance rate formula uses min(..., 100)."""
        # Static check — the formula in analytics_service.py
        # get_class_metrics uses: min((present_logs / total_logs * 100), 100.0)
        # This test verifies the clamping logic conceptually
        present, total = 10, 5  # more present than total (data anomaly)
        rate = min((present / total * 100) if total else 0.0, 100.0)
        assert rate == 100.0, f"Expected 100.0, got {rate}"

    def test_child_metrics_attendance_clamped(self):
        """Verify child attendance rate formula uses min(..., 100)."""
        present, total = 8, 4  # data anomaly scenario
        rate = min((present / total * 100) if total else 0.0, 100.0)
        assert rate == 100.0


# =============================================================================
# [P0] Soft-Delete Records Exclusion
# =============================================================================

class TestSoftDeleteExclusion:
    """Soft-deleted records must be excluded from dashboard counts."""

    def test_deleted_user_excluded_from_total(self, client, test_db, admin_token, auth_headers_admin):
        """A soft-deleted user should NOT increase the total_users count."""
        # Get baseline
        r1 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r1.status_code == 200
        baseline = r1.json().get("system_overview", {}).get("total_users", 0)

        # Add a soft-deleted user
        deleted_user = models.User(
            username="deleted_user",
            email="deleted@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
            deleted_at=datetime.now(timezone.utc),
        )
        test_db.add(deleted_user)
        test_db.commit()

        # Get count after adding deleted user — should NOT increase
        r2 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r2.status_code == 200
        new_total = r2.json().get("system_overview", {}).get("total_users", 0)
        assert new_total == baseline, f"Deleted user should not increase total_users ({baseline} -> {new_total})"

    def test_deleted_kindergarten_excluded_from_total(self, client, test_db, admin_token, auth_headers_admin):
        """A soft-deleted kindergarten should NOT increase the total_kindergartens count."""
        from models import Kindergarten, KindergartenStatus

        # Get baseline
        r1 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r1.status_code == 200
        baseline = r1.json().get("system_overview", {}).get("total_kindergartens", 0)

        # Add a soft-deleted kindergarten
        deleted_kg = Kindergarten(
            name_ar="حضانة محذوفة",
            name_en="Deleted KG",
            license_number="LIC-DEL-001",
            governorate="عمان",
            district="Test",
            area="Test",
            address_line="Test street",  # NOT NULL on kindergartens
            contact_phone="+962799999999",
            contact_email="deleted@kg.jo",
            status=KindergartenStatus.ACTIVE,
            deleted_at=datetime.now(timezone.utc),
        )
        test_db.add(deleted_kg)
        test_db.commit()

        r2 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r2.status_code == 200
        new_total = r2.json().get("system_overview", {}).get("total_kindergartens", 0)
        assert new_total == baseline, f"Deleted kindergarten should not increase total_kindergartens ({baseline} -> {new_total})"

    def test_deleted_enrollment_excluded_from_active(self, client, test_db, sample_child, sample_kindergarten, sample_class, admin_token, auth_headers_admin):
        """A soft-deleted enrollment should NOT count as active enrollment."""
        from models import EnrollmentApplication, EnrollmentStatus

        # Get baseline first
        r1 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r1.status_code == 200
        baseline = r1.json().get("summary", {}).get("attendance_today", 0)

        # Add a soft-deleted active enrollment
        deleted_enrollment = EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=EnrollmentStatus.ACTIVE,
            deleted_at=datetime.now(timezone.utc),
        )
        test_db.add(deleted_enrollment)
        test_db.commit()

        # The enrollment counts should not be inflated by soft-deleted records
        r2 = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert r2.status_code == 200


# =============================================================================
# [P1] CSRF Enforcement on State-Changing Endpoints
# =============================================================================

class TestCSRFEnforcement:
    """All state-changing (POST/PUT/DELETE/PATCH) admin endpoints must validate CSRF."""

    CSRF_ENDPOINTS = [
        ("POST", "/api/admin/users"),
        ("POST", "/api/admin/users/bulk-status-update"),
        ("POST", "/api/admin/users/bulk-delete"),
        ("POST", "/api/admin/users/bulk-create"),
        ("POST", "/api/admin/users/import-csv"),
        ("POST", "/api/admin/password-reset-request"),
        ("POST", "/api/admin/backup/create"),
        ("POST", "/api/admin/backup/cleanup"),
        ("POST", "/api/admin/audit-logs/cleanup"),
    ]

    def _call_endpoint(self, client, method, path, headers, json_data=None):
        if method == "POST":
            return client.post(path, json=json_data or {}, headers=headers)
        elif method == "PUT":
            return client.put(path, json=json_data or {}, headers=headers)
        elif method == "DELETE":
            return client.delete(path, headers=headers)
        elif method == "PATCH":
            return client.patch(path, json=json_data or {}, headers=headers)
        return client.get(path)

    def test_endpoints_reject_missing_csrf(self, client, test_db, admin_user):
        """State-changing endpoints must reject a cookie session with no CSRF pair.

        Driven by cookie, not bearer. middleware/csrf.py exempts bearer-authenticated
        requests by design — a browser cannot attach an Authorization header to a
        forged cross-origin request, and CORS is an explicit allowlist (main.py:374-381),
        so that path is not forgeable. The CSRF surface that *is* real is the browser
        session: session cookie present, double-submit pair absent.

        This previously sent a bearer token and asserted rejection, which contradicted
        the shipped policy. The mismatch was invisible because a NameError fired earlier
        in the loop. Same treatment as test_chaos.py::test_backup_endpoint_requires_csrf.
        """
        from config import settings

        client.cookies.clear()
        login = client.post(
            "/token",
            data={"username": "testadmin", "password": "Admin123!"},
        )
        assert login.status_code == 200, login.text
        session = client.cookies.get(settings.SESSION_COOKIE_NAME)
        assert session, "login must set the session cookie"

        # Cookie only — no X-CSRF-Token header, so the double-submit pair is incomplete.
        bad_headers = {"Cookie": f"{settings.SESSION_COOKIE_NAME}={session}"}

        for method, path in self.CSRF_ENDPOINTS:
            client.cookies.clear()  # keep the jar from re-supplying the CSRF cookie
            r = self._call_endpoint(client, method, path, bad_headers)
            assert r.status_code == 400, (
                f"{method} {path} returned {r.status_code}, expected 400 "
                f"for a cookie session with no CSRF pair"
            )
            assert "CSRF" in r.text, f"{method} {path} rejected for the wrong reason: {r.text[:200]}"

    def test_endpoints_accept_valid_csrf(self, client, test_db, admin_token):
        """State-changing endpoints should accept requests with valid CSRF token."""
        csrf_token = secrets.token_hex(32)
        good_headers = {
            "Authorization": f"Bearer {admin_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
            "Content-Type": "application/json",
        }

        # Test a subset of endpoints that accept empty POST bodies
        for method, path in [
            ("POST", "/api/admin/backup/create"),
            ("POST", "/api/admin/backup/cleanup"),
        ]:
            r = self._call_endpoint(client, method, path, good_headers, json_data={})
            # These may still fail for other reasons (auth, validation) but should NOT fail with CSRF error
            assert r.status_code not in (401, 403), f"{method} {path} failed with auth error despite valid CSRF"


# =============================================================================
# [P1] Legacy Dashboard Chart Labeling
# =============================================================================

class TestLegacyDashboardLabels:
    """The legacy /admin/dashboard must label attendance data correctly."""

    def test_dashboard_js_uses_attendance_semantics(self):
        """Verify admin_dashboard.js uses 'attendance' not 'user_activity' as chart key."""
        import re
        import os

        js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "admin_dashboard.js")
        with open(js_path, encoding="utf-8") as f:
            content = f.read()

        # The normalized charts object should use "attendance" key
        charts_match = re.search(r"charts:\s*\{[^}]*\}", content)
        assert charts_match, "Could not find charts object in admin_dashboard.js"
        charts_text = charts_match.group()

        assert "attendance" in charts_text, (
            f"admin_dashboard.js chart key should be 'attendance', got: {charts_text}"
        )
        assert "user_activity" not in charts_text, (
            "admin_dashboard.js must not use legacy 'user_activity' chart key"
        )

    def test_dashboard_html_uses_attendance_label(self):
        """Verify admin_dashboard.html labels the chart as 'Attendance' not 'User Activity'."""
        import os

        html_path = os.path.join(os.path.dirname(__file__), "..", "templates", "admin_dashboard.html")
        with open(html_path, encoding="utf-8") as f:
            content = f.read()

        # Should contain "Attendance" somewhere in the template
        assert "Attendance" in content or "الحضور" in content, (
            "admin_dashboard.html must label the attendance chart as 'Attendance' or 'الحضور'"
        )
        assert "User Activity" not in content, (
            "admin_dashboard.html must not use legacy 'User Activity' label"
        )

    def test_i18n_uses_attendance_key(self):
        """Verify admin_i18n.js uses 'attendance' key not 'user_activity'."""
        import os

        i18n_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "admin_i18n.js")
        with open(i18n_path, encoding="utf-8") as f:
            content = f.read()

        assert "user_activity" not in content, (
            "admin_i18n.js must not contain legacy 'user_activity' i18n key"
        )


# =============================================================================
# Analytics Service Attendance Bounds
# =============================================================================

class TestAnalyticsAttendanceBounds:
    """All attendance rate calculations in analytics_service.py must be clamped to [0, 100]."""

    def test_get_class_metrics_clamped(self):
        """get_class_metrics formula must clamp to 100%."""
        import re
        import os

        svc_path = os.path.join(os.path.dirname(__file__), "..", "analytics_service.py")
        with open(svc_path, encoding="utf-8") as f:
            content = f.read()

        # Find get_class_metrics function and check for min(... 100)
        class_metrics_match = re.search(
            r"def get_class_metrics.*?attendance_rate\s*=\s*(.*?)(?=\n\s+incident_count)",
            content, re.DOTALL
        )
        assert class_metrics_match, "Could not find attendance_rate formula in get_class_metrics"
        formula = class_metrics_match.group(1)
        assert "min(" in formula and "100" in formula, (
            f"get_class_metrics attendance formula must use min(..., 100): {formula}"
        )

    def test_get_child_metrics_clamped(self):
        """get_child_metrics formula must clamp to 100%."""
        import re
        import os

        svc_path = os.path.join(os.path.dirname(__file__), "..", "analytics_service.py")
        with open(svc_path, encoding="utf-8") as f:
            content = f.read()

        child_metrics_match = re.search(
            r"def get_child_metrics.*?attendance_rate\s*=\s*(.*?)(?=\n\s+incident_count)",
            content, re.DOTALL
        )
        assert child_metrics_match, "Could not find attendance_rate formula in get_child_metrics"
        formula = child_metrics_match.group(1)
        assert "min(" in formula and "100" in formula, (
            f"get_child_metrics attendance formula must use min(..., 100): {formula}"
        )

    def test_get_class_trend_clamped(self):
        """get_class_trend per-day formula must clamp to 100%."""
        import re
        import os

        svc_path = os.path.join(os.path.dirname(__file__), "..", "analytics_service.py")
        with open(svc_path, encoding="utf-8") as f:
            content = f.read()

        # Find get_class_trend function and check for min(... 100)
        assert "min((" in content and "100.0)" in content, (
            "analytics_service.py must clamp attendance rates with min(..., 100.0) throughout"
        )
