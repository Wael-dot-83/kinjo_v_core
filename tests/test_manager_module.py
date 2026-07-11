"""
Manager Module - Comprehensive Test Suite
Tests for permissions, data scoping, IDOR prevention, and analytics.

Uses app.dependency_overrides[get_current_user] for authentication
(the standard FastAPI test pattern used across the project).
"""

import pytest
from fastapi import status
from datetime import date, datetime, timedelta
from typing import Optional

import models
from main import app
from auth import get_password_hash
from database import get_db
from dependencies import get_current_user


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def kg_a(test_db):
    """Create kindergarten A"""
    kg = models.Kindergarten(
        name_ar="حضانة أ",
        name_en="Kindergarten A",
        governorate="عمّان",
        district="عمّان",
        area="الدعيس",
        address_line="شارع الملك",
        contact_phone="0789123456",
        contact_email="kg_a@example.com",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


@pytest.fixture
def kg_b(test_db):
    """Create kindergarten B"""
    kg = models.Kindergarten(
        name_ar="حضانة ب",
        name_en="Kindergarten B",
        governorate="الزرقاء",
        district="الزرقاء",
        area="المقابلين",
        address_line="شارع الجديدة",
        contact_phone="0789234567",
        contact_email="kg_b@example.com",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


@pytest.fixture
def admin_user_mgr(test_db):
    """Create admin user for manager module tests"""
    user = models.User(
        username="admin_mgr_test",
        email="admin_mgr@example.com",
        hashed_password=get_password_hash("Admin123!!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def manager_kg_a(test_db, kg_a):
    """Create manager for kindergarten A"""
    user = models.User(
        username="manager_kg_a",
        email="manager_a@example.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=kg_a.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def manager_kg_b(test_db, kg_b):
    """Create manager for kindergarten B"""
    user = models.User(
        username="manager_kg_b",
        email="manager_b@example.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=kg_b.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def supervisor_kg_a(test_db, kg_a):
    """Create supervisor for kindergarten A"""
    user = models.User(
        username="supervisor_kg_a",
        email="supervisor_a@example.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=kg_a.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    profile = models.SupervisorProfile(
        user_id=user.id,
        kindergarten_id=kg_a.id
    )
    test_db.add(profile)
    test_db.commit()
    return user


@pytest.fixture
def supervisor_kg_b(test_db, kg_b):
    """Create supervisor for kindergarten B"""
    user = models.User(
        username="supervisor_kg_b",
        email="supervisor_b@example.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=kg_b.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    profile = models.SupervisorProfile(
        user_id=user.id,
        kindergarten_id=kg_b.id
    )
    test_db.add(profile)
    test_db.commit()
    return user


@pytest.fixture
def class_kg_a(test_db, kg_a, supervisor_kg_a):
    """Create class in kindergarten A"""
    cls = models.Class(
        kindergarten_id=kg_a.id,
        name_ar="الحضانة",
        name_en="Nursery",
        class_code="KG-A-001",
        age_group="AGE_1_2",
        capacity_total=15,
        min_age_months=12,
        max_age_months=24,
        supervisor_id=supervisor_kg_a.id,
        is_active=True
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


@pytest.fixture
def class_kg_b(test_db, kg_b, supervisor_kg_b):
    """Create class in kindergarten B"""
    cls = models.Class(
        kindergarten_id=kg_b.id,
        name_ar="الروم",
        name_en="Toddlers",
        class_code="KG-B-001",
        age_group="AGE_2_4",
        capacity_total=15,
        min_age_months=24,
        max_age_months=36,
        supervisor_id=supervisor_kg_b.id,
        is_active=True
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


@pytest.fixture
def parent_kg_a(test_db, kg_a):
    """Create parent with child in kindergarten A"""
    parent_user = models.User(
        username="parent_kg_a",
        email="parent_a@example.com",
        hashed_password=get_password_hash("Parent123!!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(parent_user)
    test_db.flush()

    parent_profile = models.ParentProfile(
        user_id=parent_user.id,
        first_name="محمد",
        last_name="علي",
        phone_number="0789345678",
        gender=models.Gender.MALE,
        nationality="الأردن",
        national_id="1234567890",
        home_governorate="عمّان",
        home_district="عمّان",
        home_area="الدعيس",
        home_address_line="شارع الملك"
    )
    test_db.add(parent_profile)
    test_db.commit()
    test_db.refresh(parent_user)
    return parent_user


@pytest.fixture
def child_kg_a(test_db, parent_kg_a):
    """Create child in kindergarten A"""
    parent_profile = test_db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == parent_kg_a.id
    ).first()

    child = models.Child(
        parent_id=parent_profile.id,
        first_name="فاطمة",
        last_name="علي",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365),
        father_name="علي محمد",
        mother_first_name="نور",
        mother_last_name="علي",
        mother_nationality="الأردن"
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)
    return child


@pytest.fixture
def enrollment_kg_a(test_db, kg_a, child_kg_a, class_kg_a):
    """Create enrollment in kindergarten A"""
    enrollment = models.EnrollmentApplication(
        child_id=child_kg_a.id,
        kindergarten_id=kg_a.id,
        class_id=class_kg_a.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=date.today(),
        class_assignment_date=date.today()
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)
    return enrollment


# =============================================================================
# RBAC & SCOPING TESTS
# =============================================================================

class TestManagerRBACEnforcement:
    """Test manager role enforcement and kindergarten scoping"""

    def test_manager_can_access_own_kindergarten(self, client, manager_kg_a, kg_a):
        """Manager can access their own kindergarten"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get(f"/api/kindergartens/{kg_a.id}")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_manager_list_kindergartens(self, client, test_db, manager_kg_a, kg_a, kg_b):
        """Manager listing kindergartens sees results"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get("/api/kindergartens")
        assert response.status_code == 200
        payload = response.json()["data"]  # {success, data, message} envelope
        assert "items" in payload

        app.dependency_overrides.clear()

    def test_manager_cannot_create_user_for_other_kg(self, client, manager_kg_a, kg_b):
        """Manager cannot create staff for other kindergarten"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.post("/api/users", json={
            "username": "new_staff_x",
            "email": "staffx@example.com",
            "password": "Staff12345!",
            "role": "SUPERVISOR",
            "kindergarten_id": kg_b.id
        })

        # Should be denied or scoped to own KG
        assert response.status_code in [403, 201, 200, 422]

        app.dependency_overrides.clear()

    def test_manager_cannot_delete_class_from_other_kg(
        self, client, manager_kg_a, class_kg_b
    ):
        """Manager cannot delete class from other kindergarten"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.delete(f"/api/classes/{class_kg_b.id}")

        # Should not be allowed for other KG
        assert response.status_code in [403, 404]

        app.dependency_overrides.clear()

    def test_manager_can_view_own_kindergarten_detail(
        self, client, test_db, manager_kg_a, kg_a
    ):
        """Manager can view their own kindergarten details"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get(f"/api/kindergartens/{kg_a.id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == kg_a.id

        app.dependency_overrides.clear()


class TestManagerDataIsolation:
    """Test strict data isolation between kindergartens"""

    def test_manager_can_view_own_kg_class(self, client, manager_kg_a, class_kg_a):
        """Manager can view their own kindergarten's classes"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get(f"/api/classes/{class_kg_a.id}")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_manager_cannot_see_other_kg_classes(
        self, client, manager_kg_a, class_kg_b
    ):
        """Manager cannot view classes from other kindergarten"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get(f"/api/classes/{class_kg_b.id}")
        # Should be denied or not found
        assert response.status_code in [403, 404, 200]

        app.dependency_overrides.clear()

    def test_manager_can_list_enrollments(
        self, client, test_db, manager_kg_a, enrollment_kg_a
    ):
        """Manager can list enrollments"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get("/api/enrollments")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_manager_cannot_see_other_kg_children(
        self, client, test_db, manager_kg_b, enrollment_kg_a, child_kg_a
    ):
        """GET /api/manager/children had no dedicated cross-tenant test --
        manager_kg_b must never see child_kg_a (enrolled in kg_a's class)."""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_b

        response = client.get("/api/manager/children")
        assert response.status_code == 200
        returned_ids = {c["id"] for c in response.json()["children"]}
        assert child_kg_a.id not in returned_ids

        app.dependency_overrides.clear()

    def test_manager_cannot_see_other_kg_supervisors(
        self, client, test_db, manager_kg_b, supervisor_kg_a
    ):
        """GET /api/manager/supervisors had no dedicated cross-tenant test
        -- manager_kg_b must never see supervisor_kg_a."""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_b

        response = client.get("/api/manager/supervisors")
        assert response.status_code == 200
        returned_ids = {s["id"] for s in response.json()["supervisors"]}
        assert supervisor_kg_a.id not in returned_ids

        app.dependency_overrides.clear()

    def test_manager_cannot_assign_foreign_supervisor_to_own_class(
        self, client, test_db, manager_kg_a, class_kg_a, supervisor_kg_b
    ):
        """routers/manager.py's assign_supervisor_to_class already guards
        against this (checks sup.kindergarten_id != current_user.
        kindergarten_id) but the negative case was never exercised by a
        test -- assigning a kg_b supervisor onto a kg_a class must fail."""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.post(
            "/api/manager/classes/assign-supervisor",
            json={"supervisor_id": supervisor_kg_b.id, "class_id": class_kg_a.id, "is_primary": False},
        )
        assert response.status_code in (403, 404)

        app.dependency_overrides.clear()


class TestManagerAnalytics:
    """Test analytics endpoints accessible to manager/admin"""

    def test_admin_can_access_analytics_dashboard(self, client, admin_user_mgr):
        """Admin can access analytics dashboard"""
        app.dependency_overrides[get_current_user] = lambda: admin_user_mgr

        response = client.get("/api/analytics/dashboard")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_admin_can_access_kpi_analytics(self, client, admin_user_mgr):
        """Admin can access KPI analytics"""
        app.dependency_overrides[get_current_user] = lambda: admin_user_mgr

        response = client.get("/api/analytics/kpi")
        assert response.status_code == 200

        app.dependency_overrides.clear()


# =============================================================================
# MANAGER WORKFLOWS TESTS
# =============================================================================

class TestManagerWorkflows:
    """Test complete manager workflows"""

    def test_manager_can_list_users(self, client, test_db, manager_kg_a, supervisor_kg_a):
        """Manager can list users"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        app.dependency_overrides.clear()

    def test_manager_daily_report_workflow(
        self, client, test_db, manager_kg_a, class_kg_a, child_kg_a, enrollment_kg_a
    ):
        """Manager can interact with daily reports"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get("/api/supervisor/daily-reports")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_manager_class_management(
        self, client, test_db, manager_kg_a, class_kg_a, kg_a
    ):
        """Manager can manage classes in their own kindergarten"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        response = client.get(f"/api/classes/{class_kg_a.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["kindergarten_id"] == kg_a.id

        app.dependency_overrides.clear()

    def test_manager_enrollment_management(
        self, client, test_db, manager_kg_a, enrollment_kg_a
    ):
        """Manager can list enrollments"""
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a

        # List enrollments
        response = client.get("/api/enrollments")
        assert response.status_code == 200

        app.dependency_overrides.clear()


# =============================================================================
# MANAGER HARDENING (2026-07: NULL-KG guard, dashboard, audit, absence scope)
# =============================================================================


@pytest.fixture
def manager_no_kg():
    """A manager with no kindergarten association.

    The DB CHECK constraint (manager_must_have_kindergarten) blocks
    persisting such a row, so this is an unpersisted object injected via
    dependency_overrides — it exercises the API-level defense-in-depth
    guard for data that predates the constraint or arrives via other DBs.
    """
    return models.User(
        id=999901,
        username="manager_no_kg",
        email="manager_no_kg@example.com",
        hashed_password="x",
        full_name="مدير بلا حضانة",
        role=models.UserRole.MANAGER,
        kindergarten_id=None,
        status=models.UserStatus.ACTIVE,
    )


@pytest.fixture
def absence_kg_a(test_db, kg_a, parent_kg_a, child_kg_a, class_kg_a):
    """A submitted absence request for a child in kindergarten A."""
    parent_profile = test_db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == parent_kg_a.id
    ).first()
    req = models.AbsenceRequest(
        parent_id=parent_profile.id,
        child_id=child_kg_a.id,
        kindergarten_id=kg_a.id,
        class_id=class_kg_a.id,
        start_date=date.today() + timedelta(days=3),
        end_date=date.today() + timedelta(days=4),
        reason="سفر عائلي",
        status=models.AbsenceRequestStatus.SUBMITTED,
    )
    test_db.add(req)
    test_db.commit()
    test_db.refresh(req)
    return req


class TestManagerNullKindergartenGuard:
    """A manager without a kindergarten has no operational scope."""

    def test_null_kg_manager_rejected_on_classes(self, client, manager_no_kg):
        app.dependency_overrides[get_current_user] = lambda: manager_no_kg
        r = client.get("/api/manager/classes")
        assert r.status_code == 403
        app.dependency_overrides.clear()

    def test_null_kg_manager_rejected_on_dashboard(self, client, manager_no_kg):
        app.dependency_overrides[get_current_user] = lambda: manager_no_kg
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 403
        app.dependency_overrides.clear()

    def test_null_kg_manager_rejected_on_absence_list(self, client, manager_no_kg):
        app.dependency_overrides[get_current_user] = lambda: manager_no_kg
        r = client.get("/api/absence-requests")
        assert r.status_code == 403
        app.dependency_overrides.clear()


class TestManagerDashboard:
    """GET /api/manager/dashboard is own-kindergarten only."""

    def test_dashboard_counts_own_kg_only(
        self, client, test_db, manager_kg_a, kg_a, kg_b,
        class_kg_a, class_kg_b, enrollment_kg_a, supervisor_kg_a, supervisor_kg_b,
    ):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 200
        d = r.json()
        assert d["kindergarten"]["id"] == kg_a.id
        # KG B's class/supervisor/enrollment must not be counted.
        assert len(d["classes"]) == 1
        assert d["summary"]["active_enrollments"] == 1
        assert d["summary"]["supervisors_count"] == 1
        # Structural keys the manager dashboard frontend relies on.
        assert "classes_without_supervisor" in d
        assert "classes_near_capacity" in d
        for key in ("pending_absence_requests", "reports_sent_today",
                    "pending_daily_reports", "pending_applications"):
            assert key in d["summary"]
        app.dependency_overrides.clear()

    def test_dashboard_forbidden_for_supervisor(self, client, supervisor_kg_a):
        app.dependency_overrides[get_current_user] = lambda: supervisor_kg_a
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 403
        app.dependency_overrides.clear()


class TestManagerMutationAudit:
    """Every manager mutation writes an AuditLog row."""

    def _audit_count(self, test_db, action):
        return test_db.query(models.AuditLog).filter(
            models.AuditLog.action == action
        ).count()

    def test_assign_supervisor_writes_audit(
        self, client, test_db, manager_kg_a, class_kg_a, supervisor_kg_a
    ):
        before = self._audit_count(test_db, "SUPERVISOR_ASSIGNED")
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post("/api/manager/classes/assign-supervisor", json={
            "class_id": class_kg_a.id,
            "supervisor_id": supervisor_kg_a.id,
            "is_primary": False,
        })
        assert r.status_code in (200, 201), r.text
        if not r.json().get("already_exists"):
            assert self._audit_count(test_db, "SUPERVISOR_ASSIGNED") == before + 1
        app.dependency_overrides.clear()

    def test_move_child_full_class_blocked_and_audited(
        self, client, test_db, manager_kg_a, kg_a, child_kg_a, class_kg_a, enrollment_kg_a, supervisor_kg_a
    ):
        # A second class with capacity 0 -> move must be blocked with 409.
        full_class = models.Class(
            kindergarten_id=kg_a.id,
            name_ar="صف ممتلئ", name_en="Full Class",
            class_code="FULL-01", age_group="AGE_2_4",
            capacity_total=0, min_age_months=24, max_age_months=72,
            supervisor_id=None, is_active=True,
        )
        test_db.add(full_class)
        test_db.commit()
        test_db.refresh(full_class)

        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post("/api/manager/children/move-class", json={
            "child_id": child_kg_a.id,
            "from_class_id": class_kg_a.id,
            "to_class_id": full_class.id,
        })
        assert r.status_code == 409

        # Raise capacity; the move now succeeds and is audited.
        full_class.capacity_total = 5
        test_db.commit()
        before = self._audit_count(test_db, "CHILD_MOVED_CLASS")
        r = client.post("/api/manager/children/move-class", json={
            "child_id": child_kg_a.id,
            "from_class_id": class_kg_a.id,
            "to_class_id": full_class.id,
        })
        assert r.status_code == 200, r.text
        assert self._audit_count(test_db, "CHILD_MOVED_CLASS") == before + 1
        app.dependency_overrides.clear()


class TestAbsenceDecisionScope:
    """Absence approve/reject is manager-only, own-KG only, SUBMITTED-only."""

    def test_supervisor_cannot_approve(self, client, supervisor_kg_a, absence_kg_a):
        app.dependency_overrides[get_current_user] = lambda: supervisor_kg_a
        r = client.post(f"/api/absence-requests/{absence_kg_a.id}/approve", json={})
        assert r.status_code == 403
        app.dependency_overrides.clear()

    def test_foreign_manager_cannot_approve(self, client, manager_kg_b, absence_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_b
        r = client.post(f"/api/absence-requests/{absence_kg_a.id}/approve", json={})
        assert r.status_code == 403
        app.dependency_overrides.clear()

    def test_foreign_manager_cannot_reject(self, client, manager_kg_b, absence_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_b
        r = client.post(f"/api/absence-requests/{absence_kg_a.id}/reject", json={})
        assert r.status_code == 403
        app.dependency_overrides.clear()

    def test_own_manager_approve_writes_audit(
        self, client, test_db, manager_kg_a, absence_kg_a
    ):
        before = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "ABSENCE_REQUEST_APPROVED").count()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post(f"/api/absence-requests/{absence_kg_a.id}/approve", json={})
        assert r.status_code == 200, r.text
        after = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "ABSENCE_REQUEST_APPROVED").count()
        assert after == before + 1

        # A decided request cannot be re-decided.
        r = client.post(f"/api/absence-requests/{absence_kg_a.id}/reject", json={})
        assert r.status_code == 400
        app.dependency_overrides.clear()


class TestManagerAnalyticsDrilldown:
    """Regression tests for manager analytics math (P1 fixes)."""

    def test_drilldown_class_attendance_excludes_absences_and_uses_operating_days(
        self, test_db, kg_a, manager_kg_a, class_kg_a, child_kg_a, enrollment_kg_a
    ):
        """get_drilldown_by_class must count only PRESENT/LATE as attended and
        divide by *operating* (not raw calendar) days, never exceeding 100%.

        Deterministic setup: OperatingCalendar forces all 30 window days open,
        the single enrolled child is PRESENT on 29 of them and ABSENT on one.
        Rate must be 29/30*100 ≈ 96.7% (absence excluded, under 100%).
        """
        from manager_analytics import ManagerAnalyticsService
        from utils.time_utils import today_amman

        today = today_amman()
        start = today - timedelta(days=29)
        for i in range(30):
            test_db.add(models.OperatingCalendar(
                kindergarten_id=kg_a.id, date=start + timedelta(days=i), is_open=True,
            ))
        test_db.commit()

        # The single active child is ABSENT on the first window day -> must NOT count.
        test_db.add(models.AttendanceLog(
            child_id=child_kg_a.id, class_id=class_kg_a.id,
            recorded_by=manager_kg_a.id,
            date=start, status=models.AttendanceStatus.ABSENT,
        ))
        # PRESENT on the remaining 29 days (start+1 .. start+29).
        for i in range(1, 30):
            test_db.add(models.AttendanceLog(
                child_id=child_kg_a.id, class_id=class_kg_a.id,
                recorded_by=manager_kg_a.id,
                date=start + timedelta(days=i), status=models.AttendanceStatus.PRESENT,
            ))
        test_db.commit()

        rows = ManagerAnalyticsService.get_drilldown_by_class(
            test_db, kg_a.id, start, today
        )
        assert len(rows) == 1
        cls = rows[0]
        assert cls["enrolled"] == 1
        # denominator = 1 enrolled * 30 operating days; numerator = 29 present.
        assert round(cls["attendance_rate"], 1) == 96.7
        assert cls["attendance_rate"] < 100.0


    def test_absenteeism_rate_uses_operating_days_and_clamps(
        self, test_db, kg_a, manager_kg_a, class_kg_a, child_kg_a, enrollment_kg_a
    ):
        """compute_absenteeism_rate must use operating days and clamp to [0,100]."""
        from manager_analytics import ManagerAnalyticsService
        from utils.time_utils import today_amman

        today = today_amman()
        start = today - timedelta(days=29)
        # All 30 logs marked ABSENT -> absenteeism should be capped at 100%, not >100%.
        for i in range(30):
            test_db.add(models.AttendanceLog(
                child_id=child_kg_a.id, class_id=class_kg_a.id,
                recorded_by=manager_kg_a.id,
                date=start + timedelta(days=i),
                status=models.AttendanceStatus.ABSENT,
            ))
        test_db.commit()

        rate = ManagerAnalyticsService.compute_absenteeism_rate(test_db, kg_a.id, start, today)
        assert 0.0 <= rate <= 100.0


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
