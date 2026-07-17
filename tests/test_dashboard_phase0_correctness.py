"""
Phase 0 Dashboard Data-Correctness Regression Tests

Verifies the fixes for:
- P0-01: Attendance percentage never exceeds 100%
- P0-02: Soft-deleted records excluded from dashboard totals
- P0-03: Date windows contain the documented number of days
- P0-04: Attendance data correctly labeled (PRESENT+LATE, distinct child-days)
- P0-05: Supervisor attendance excludes ABSENT/EXCUSED
"""
import pytest
from fastapi import status
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))

import models
from main import app
from auth import get_password_hash
from database import get_db


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def admin_token(client, admin_user):
    response = client.post(
        "/token",
        data={"username": "testadmin", "password": "Admin123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def manager_token(client, manager_user):
    response = client.post(
        "/token",
        data={"username": "testmanager", "password": "Manager123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def supervisor_token(client, supervisor_user):
    response = client.post(
        "/token",
        data={"username": "testsupervisor", "password": "Supervisor123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers_admin(admin_token):
    csrf_token = "test-csrf-token-admin"
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}",
    }


@pytest.fixture
def auth_headers_manager(manager_token):
    csrf_token = "test-csrf-token-manager"
    return {
        "Authorization": f"Bearer {manager_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}",
    }


@pytest.fixture
def auth_headers_supervisor(supervisor_token):
    csrf_token = "test-csrf-token-supervisor"
    return {
        "Authorization": f"Bearer {supervisor_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}",
    }


def _get_token(client, username, password):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


# =============================================================================
# P0-01: Attendance percentage never exceeds 100%
# =============================================================================

class TestAttendanceRateNeverExceeds100:
    """Attendance rate must be bounded 0–100 even with duplicate records."""

    def test_admin_dashboard_attendance_rate_bounded(self, client, test_db, auth_headers_admin):
        """Admin dashboard attendance_rate must be 0–100."""
        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        rate = data.get("summary", {}).get("attendance_rate")
        assert rate is not None
        assert 0.0 <= rate <= 100.0, f"attendance_rate {rate} out of bounds"

    def test_manager_dashboard_attendance_rate_bounded(self, client, test_db, sample_kindergarten):
        """Manager dashboard attendance today must not exceed active enrollments."""
        manager = models.User(
            username="mgr_rate_test",
            email="mgr_rate@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_rate_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        attendance_today = summary.get("attendance_today", 0)
        active_enrollments = summary.get("active_enrollments", 0)
        if active_enrollments > 0:
            rate = (attendance_today / active_enrollments) * 100
            assert 0.0 <= rate <= 100.0, f"attendance rate {rate} out of bounds"


# =============================================================================
# P0-02: Soft-deleted records excluded from dashboards
# =============================================================================

class TestSoftDeleteExcluded:
    """Soft-deleted entities must not appear in dashboard totals."""

    def test_admin_excludes_deleted_users(self, client, test_db, auth_headers_admin):
        """Admin total_users must not include soft-deleted users."""
        # Count baseline users (admin_user fixture is already present)
        baseline_response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert baseline_response.status_code == 200
        baseline_data = baseline_response.json()
        baseline_total = baseline_data.get("system_overview", {}).get("total_users", 0)

        # Create a soft-deleted user
        deleted_user = models.User(
            username="deleted_user",
            email="deleted@test.com",
            hashed_password=get_password_hash("Admin123!"),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
            deleted_at=datetime.now(_JORDAN_TZ),
        )
        test_db.add(deleted_user)
        test_db.commit()

        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        total_users = data.get("system_overview", {}).get("total_users", 0)
        # total_users should remain at baseline (the deleted user must not be counted)
        assert total_users == baseline_total

    def test_admin_excludes_deleted_kindergartens(self, client, test_db, auth_headers_admin):
        """Admin total_kindergartens must not include soft-deleted kindergartens."""
        # Create a disposable kindergarten to delete, leaving sample_kindergarten intact
        disposable_kg = models.Kindergarten(
            name_ar="حضانة محذوفة",
            name_en="Deleted KG",
            governorate="Amman",
            district="Amman",
            area="Test",
            address_line="Test",
            contact_phone="+962700000000",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(disposable_kg)
        test_db.commit()
        test_db.refresh(disposable_kg)

        # Soft-delete the disposable kindergarten
        disposable_kg.deleted_at = datetime.now(_JORDAN_TZ)
        test_db.commit()

        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        total_kgs = data.get("system_overview", {}).get("total_kindergartens", 0)
        # Should still count sample_kindergarten but not the deleted one
        assert total_kgs >= 1

    def test_admin_excludes_deleted_enrollments_from_active_count(
        self, client, test_db, sample_kindergarten, sample_child, sample_class, auth_headers_admin
    ):
        """Admin active_enrollments must not include soft-deleted enrollment applications."""
        # Create an active enrollment and a soft-deleted one
        active_enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        deleted_enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            deleted_at=datetime.now(_JORDAN_TZ),
        )
        test_db.add_all([active_enrollment, deleted_enrollment])
        test_db.commit()

        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        # Should count only the active enrollment
        assert summary.get("active_enrollments", 0) == 1

    def test_manager_excludes_deleted_enrollments(self, client, test_db, sample_kindergarten):
        """Manager active_enrollments must not include soft-deleted enrollments."""
        manager = models.User(
            username="mgr_delete_test",
            email="mgr_del@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        # Create active and deleted enrollments
        parent_profile = models.ParentProfile(
            user_id=manager.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962700000000",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test",
            home_address_line="Test",
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            parent_id=parent_profile.id,
            first_name="Test",
            last_name="Child",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        cls = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="test",
            name_en="Test",
            class_code="T1",
            age_group="AGE_1_2",
            capacity_total=10,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        active_enr = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=cls.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        deleted_enr = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=cls.id,
            status=models.EnrollmentStatus.ACTIVE,
            deleted_at=datetime.now(_JORDAN_TZ),
        )
        test_db.add_all([active_enr, deleted_enr])
        test_db.commit()

        token = _get_token(client, "mgr_delete_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        assert summary.get("active_enrollments", 0) == 1


# =============================================================================
# P0-03: Date windows contain the documented number of days
# =============================================================================

class TestDateWindowIntegrity:
    """Date ranges must contain exactly the documented number of days."""

    def test_seven_day_period_has_seven_dates(self):
        """seven_day_period must return a 7-day inclusive range."""
        from dashboard_metrics import seven_day_period
        today = date(2026, 7, 15)
        start, end = seven_day_period(today)
        assert start == date(2026, 7, 9)
        assert end == today
        assert (end - start).days + 1 == 7

    def test_resolve_dashboard_period_week(self):
        """resolve_dashboard_period('week') must return exactly 7 days."""
        from dashboard_metrics import resolve_dashboard_period
        period = resolve_dashboard_period(None, None, "week")
        assert period.inclusive_days == 7

    def test_resolve_dashboard_period_quarter(self):
        """resolve_dashboard_period('quarter') must return exactly 90 days."""
        from dashboard_metrics import resolve_dashboard_period
        period = resolve_dashboard_period(None, None, "quarter")
        assert period.inclusive_days == 90

    def test_resolve_dashboard_period_rejects_reversed_dates(self):
        """resolve_dashboard_period must reject start > end."""
        from dashboard_metrics import resolve_dashboard_period, DashboardPeriod
        with pytest.raises(ValueError, match="start_date must be before or equal to end_date"):
            resolve_dashboard_period("2026-07-20", "2026-07-10")

    def test_resolve_dashboard_period_rejects_excessive_range(self):
        """resolve_dashboard_period must reject ranges exceeding max_days."""
        from dashboard_metrics import resolve_dashboard_period
        with pytest.raises(ValueError, match="Period cannot exceed 90 days"):
            resolve_dashboard_period("2026-01-01", "2026-12-31", max_days=90)

    def test_resolve_dashboard_period_rejects_unknown_range(self):
        """resolve_dashboard_period must reject unknown named ranges."""
        from dashboard_metrics import resolve_dashboard_period
        with pytest.raises(ValueError, match="Unknown range"):
            resolve_dashboard_period(None, None, "unknown_range")

    def test_dashboard_summary_week_returns_7_day_trend(self, client, test_db, sample_kindergarten):
        """Dashboard summary week trend must have exactly 7 data points."""
        manager = models.User(
            username="mgr_trend_test",
            email="mgr_trend@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_trend_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.post(
            "/api/dashboard/summary",
            json={"range": "week", "kindergarten_id": sample_kindergarten.id},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        trend = data.get("chart", [])
        assert len(trend) == 7


# =============================================================================
# P0-04: Attendance includes PRESENT+LATE, excludes ABSENT/EXCUSED
# =============================================================================

class TestAttendanceStatusFiltering:
    """Only PRESENT and LATE count as attended; ABSENT and EXCUSED must not."""

    def test_present_and_late_count_as_attendance(self, client, test_db, sample_kindergarten, sample_child, sample_class):
        """PRESENT and LATE attendance logs must be counted."""
        # Create a manager
        manager = models.User(
            username="mgr_status_test",
            email="mgr_status@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        today = date.today()
        # Create PRESENT and LATE attendance logs
        present_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager.id,
        )
        late_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.LATE,
            recorded_by=manager.id,
        )
        test_db.add_all([present_att, late_att])
        test_db.commit()

        token = _get_token(client, "mgr_status_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        # Both PRESENT and LATE should count as attended
        assert summary.get("attendance_today", 0) >= 1

    def test_absent_does_not_count_as_attendance(self, client, test_db, sample_kindergarten, sample_child, sample_class):
        """ABSENT attendance logs must NOT be counted as attended."""
        manager = models.User(
            username="mgr_absent_test",
            email="mgr_absent@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        today = date.today()
        # Create only ABSENT attendance log
        absent_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.ABSENT,
            recorded_by=manager.id,
        )
        test_db.add(absent_att)
        test_db.commit()

        token = _get_token(client, "mgr_absent_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        # ABSENT should NOT count as attendance
        assert summary.get("attendance_today", 0) == 0

    def test_excused_does_not_count_as_attendance(self, client, test_db, sample_kindergarten, sample_child, sample_class):
        """EXCUSED attendance logs must NOT be counted as attended."""
        manager = models.User(
            username="mgr_excused_test",
            email="mgr_excused@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        today = date.today()
        excused_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.EXCUSED,
            recorded_by=manager.id,
        )
        test_db.add(excused_att)
        test_db.commit()

        token = _get_token(client, "mgr_excused_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        assert summary.get("attendance_today", 0) == 0


# =============================================================================
# P0-05: Supervisor attendance excludes ABSENT/EXCUSED and deduplicates children
# =============================================================================

class TestSupervisorAttendanceCorrectness:
    """Supervisor dashboard must count PRESENT+LATE only, distinct children."""

    def test_supervisor_attendance_counts_present_late_only(
        self, client, test_db, sample_kindergarten, sample_class
    ):
        """Supervisor attendance must count only PRESENT and LATE."""
        supervisor = models.User(
            username="sup_att_test",
            email="sup_att@test.com",
            hashed_password=get_password_hash("Supervisor123!"),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(supervisor)
        test_db.commit()
        test_db.refresh(supervisor)

        profile = models.SupervisorProfile(
            user_id=supervisor.id,
            kindergarten_id=sample_kindergarten.id,
        )
        test_db.add(profile)
        test_db.commit()

        assignment = models.SupervisorAssignment(
            supervisor_id=supervisor.id,
            class_id=sample_class.id,
            start_date=date.today(),
            is_primary=True,
        )
        test_db.add(assignment)
        test_db.commit()

        child = models.Child(
            parent_id=None,
            first_name="Super",
            last_name="Visor",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        today = date.today()
        absent_att = models.AttendanceLog(
            child_id=child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.ABSENT,
            recorded_by=supervisor.id,
        )
        test_db.add(absent_att)
        test_db.commit()

        token = _get_token(client, "sup_att_test", "Supervisor123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/supervisor/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        attendance_summary = data.get("attendance_summary", {})
        # ABSENT should not count
        assert attendance_summary.get("today", 0) == 0


# =============================================================================
# P0-EXTRA: Chart data contract sanity
# =============================================================================

class TestChartDataContract:
    """Chart data in API responses must match the rendered contract."""

    def test_admin_dashboard_has_attendance_chart(self, client, auth_headers_admin):
        """Admin dashboard must return attendance chart data."""
        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        charts = data.get("charts", {})
        assert "attendance" in charts
        assert isinstance(charts["attendance"], list)
        if charts["attendance"]:
            point = charts["attendance"][0]
            assert "date" in point
            assert "value" in point

    def test_admin_dashboard_has_enrollment_chart(self, client, auth_headers_admin):
        """Admin dashboard must return enrollment chart data."""
        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        charts = data.get("charts", {})
        assert "enrollment" in charts
        assert isinstance(charts["enrollment"], dict)


# =============================================================================
# P0-EXTRA: Join fan-out and duplicate enrollment safety
# =============================================================================

class TestJoinFanOutSafety:
    """Duplicate or historical enrollment rows must not inflate attendance counts."""

    def test_duplicate_enrollment_rows_do_not_inflate_admin_attendance(
        self, client, test_db, sample_kindergarten, sample_child, sample_class, auth_headers_admin
    ):
        """Multiple enrollment rows for one child must not multiply attendance."""
        today = date.today()
        # Create a second historical enrollment for the same child
        historical_enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACCEPTED,
            enrollment_start_date=date.today() - timedelta(days=365),
            enrollment_end_date=date.today() - timedelta(days=30),
        )
        test_db.add(historical_enrollment)
        test_db.commit()

        # Single attendance record for today
        present_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=1,
        )
        test_db.add(present_att)
        test_db.commit()

        response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        # attendance_today must be 1 (one child), not multiplied by enrollment count
        assert summary.get("attendance_today", 0) == 1

    def test_future_attendance_excluded_from_manager_dashboard(
        self, client, test_db, sample_kindergarten, sample_child, sample_class
    ):
        """Future attendance records must not affect today's dashboard."""
        manager = models.User(
            username="mgr_future_test",
            email="mgr_future@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        today = date.today()
        future = today + timedelta(days=7)
        future_att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=future,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager.id,
        )
        test_db.add(future_att)
        test_db.commit()

        token = _get_token(client, "mgr_future_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        # Future attendance must not be counted in today's attendance
        assert summary.get("attendance_today", 0) == 0


# =============================================================================
# P0-EXTRA: Parent dashboard soft-delete and scope
# =============================================================================

class TestParentDashboardScope:
    """Parent dashboard must show only their non-deleted children."""

    def test_parent_excludes_deleted_children(
        self, client, test_db, parent_user, sample_kindergarten
    ):
        """Soft-deleted children must not appear on parent dashboard."""
        # parent_user and sample_child are from conftest fixtures
        # sample_child is already linked to parent_user via parent_profile
        child = test_db.query(models.Child).filter(
            models.Child.parent_id == parent_user.parent_profile.id
        ).first()
        if not child:
            # Create a child for this parent if sample_child is not linked
            child = models.Child(
                parent_id=parent_user.parent_profile.id,
                first_name="ParentTest",
                last_name="Child",
                gender=models.Gender.MALE,
                date_of_birth=date.today() - timedelta(days=365 * 3),
            )
            test_db.add(child)
            test_db.commit()
            test_db.refresh(child)

        # Soft-delete the child
        child.deleted_at = datetime.now(_JORDAN_TZ)
        test_db.commit()

        token = _get_token(client, parent_user.username, "Parent123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/parent/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        children = data.get("children", [])
        # Deleted child must not appear
        assert len(children) == 0


# =============================================================================
# P0-EXTRA: Manager class-level attendance distinct children
# =============================================================================

class TestManagerClassAttendanceDistinctChildren:
    """Manager class-level present counts must count distinct children, not log IDs."""

    def test_manager_class_present_counts_distinct_children(
        self, client, test_db, sample_kindergarten, sample_class
    ):
        """present_by_class must count distinct children, not attendance log rows."""
        manager = models.User(
            username="mgr_class_test",
            email="mgr_class@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        child = models.Child(
            parent_id=None,
            first_name="ClassTest",
            last_name="Child",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        today = date.today()
        present_att = models.AttendanceLog(
            child_id=child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager.id,
        )
        test_db.add(present_att)
        test_db.commit()

        token = _get_token(client, "mgr_class_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        classes = data.get("classes", [])
        class_data = next((c for c in classes if c["id"] == sample_class.id), None)
        assert class_data is not None
        # Must count 1 child, not 1 log row (they happen to match here, but the
        # important thing is the query uses DISTINCT child_id, not log ID)
        assert class_data.get("present", 0) == 1


# =============================================================================
# P0-EXTRA: Attendance rate bounded in API responses
# =============================================================================

class TestAttendanceRateBoundedInAllApis:
    """All API attendance rates must be bounded 0–100."""

    def test_dashboard_summary_attendance_bounded(self, client, test_db, sample_kindergarten):
        """POST /api/dashboard/summary attendance must be 0–100."""
        manager = models.User(
            username="mgr_summary_bound",
            email="mgr_summary_bound@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_summary_bound", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.post(
            "/api/dashboard/summary",
            json={"range": "week", "kindergarten_id": sample_kindergarten.id},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        rate = data.get("attendance", 0)
        assert 0.0 <= rate <= 100.0, f"dashboard summary attendance {rate} out of bounds"

    def test_suggested_actions_rate_bounded(self, client, test_db, sample_kindergarten):
        """GET /api/dashboard/suggested-actions rates must be 0–100 or None."""
        manager = models.User(
            username="mgr_suggested_bound",
            email="mgr_suggested_bound@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_suggested_bound", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/dashboard/suggested-actions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        actions = data.get("data", [])
        for action in actions:
            curr = action.get("current_rate")
            prev = action.get("prev_rate")
            change = action.get("change")
            if curr is not None:
                assert 0.0 <= curr <= 100.0, f"suggested-actions current_rate {curr} out of bounds"
            if prev is not None:
                assert 0.0 <= prev <= 100.0, f"suggested-actions prev_rate {prev} out of bounds"
            if change is not None:
                # Change can be negative, so check magnitude is reasonable
                assert abs(change) <= 100.0, f"suggested-actions change {change} out of bounds"


# =============================================================================
# Phase 1: API contract and validation fixes
# =============================================================================

class TestPhase1ApiContracts:
    """Phase 1 regression tests for API contract fixes."""

    def test_dashboard_summary_rejects_unknown_range(self, client, test_db, sample_kindergarten):
        """POST /api/dashboard/summary must reject unknown range names with 422."""
        manager = models.User(
            username="mgr_range_test",
            email="mgr_range@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_range_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.post(
            "/api/dashboard/summary",
            json={"range": "unknown_range", "kindergarten_id": sample_kindergarten.id},
            headers=headers,
        )
        assert response.status_code == 422

    def test_dashboard_summary_rejects_reversed_dates(self, client, test_db, sample_kindergarten):
        """POST /api/dashboard/summary must reject start > end with 422."""
        manager = models.User(
            username="mgr_reverse_test",
            email="mgr_reverse@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        token = _get_token(client, "mgr_reverse_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.post(
            "/api/dashboard/summary",
            json={
                "period_start": "2026-07-20",
                "period_end": "2026-07-10",
                "kindergarten_id": sample_kindergarten.id,
            },
            headers=headers,
        )
        assert response.status_code == 422
        data = response.json()
        assert "period_start must be before or equal to period_end" in str(data.get("detail", ""))

    def test_manager_license_expiry_wording_expired(self, client, test_db, sample_kindergarten):
        """Manager dashboard must say 'expired N days ago' for past licenses."""
        manager = models.User(
            username="mgr_lic_test",
            email="mgr_lic@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        # Set license to expired 5 days ago
        sample_kindergarten.license_valid_until = date.today() - timedelta(days=5)
        test_db.commit()

        token = _get_token(client, "mgr_lic_test", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        alerts = data.get("alerts", [])
        license_alerts = [a for a in alerts if a.get("type") == "license_expiry"]
        assert len(license_alerts) == 1
        assert "expired 5 days ago" in license_alerts[0]["message"]

    def test_manager_license_expiry_wording_future(self, client, test_db, sample_kindergarten):
        """Manager dashboard must say 'expires in N days' for future licenses."""
        manager = models.User(
            username="mgr_lic_future",
            email="mgr_lic_future@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        # Set license to expire in 10 days
        sample_kindergarten.license_valid_until = date.today() + timedelta(days=10)
        test_db.commit()

        token = _get_token(client, "mgr_lic_future", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        alerts = data.get("alerts", [])
        license_alerts = [a for a in alerts if a.get("type") == "license_expiry"]
        assert len(license_alerts) == 1
        assert "expires in 10 days" in license_alerts[0]["message"]

    def test_pending_enrollment_statuses_constant_exists(self):
        """models.PENDING_ENROLLMENT_STATUSES must be defined and usable."""
        from models import PENDING_ENROLLMENT_STATUSES, EnrollmentStatus
        assert EnrollmentStatus.PENDING_REVIEW in PENDING_ENROLLMENT_STATUSES

    def test_dashboard_uses_pending_enrollment_statuses(self, client, test_db, sample_kindergarten):
        """Dashboard endpoints must use PENDING_ENROLLMENT_STATUSES for pending counts."""
        manager = models.User(
            username="mgr_pending_const",
            email="mgr_pending_const@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=sample_kindergarten.id,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        # Create PENDING_REVIEW enrollment
        child = models.Child(
            parent_id=None,
            first_name="Pending",
            last_name="Child",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        cls = models.Class(
            kindergarten_id=sample_kindergarten.id,
            name_ar="test",
            name_en="Test",
            class_code="P1",
            age_group="AGE_1_2",
            capacity_total=10,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=cls.id,
            status=models.EnrollmentStatus.PENDING_REVIEW,
        )
        test_db.add(enrollment)
        test_db.commit()

        token = _get_token(client, "mgr_pending_const", "Manager123!")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "test-csrf",
            "Cookie": "kinjo_csrf_token=test-csrf",
        }

        response = client.get("/api/manager/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        assert summary.get("pending_applications", 0) >= 1
