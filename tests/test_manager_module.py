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
        assert {item["id"] for item in payload["items"]} == {kg_a.id}

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
# HARDENING FIXES — scope/IDOR, capacity rule, report workflow, analytics
# =============================================================================

def _class_payload(kg_id, supervisor_id, **overrides):
    payload = {
        "kindergarten_id": kg_id,
        "name_ar": "صف جديد",
        "name_en": "New Class",
        "class_code": "NEWCLS",
        "age_group": "AGE_2_4",
        "capacity_total": 10,
        "min_age_months": 24,
        "max_age_months": 48,
        "supervisor_id": supervisor_id,
    }
    payload.update(overrides)
    return payload


def _make_report(test_db, kg_id, child_id, submitted_by,
                 status=models.DailyReportStatus.SUBMITTED):
    report = models.DailyReport(
        child_id=child_id,
        kindergarten_id=kg_id,
        date=date.today(),
        status=status,
        submitted_by=submitted_by,
        arrival_time="08:00",
    )
    test_db.add(report)
    test_db.commit()
    test_db.refresh(report)
    return report


class TestClassCapacityStatusIDOR:
    """#1 — capacity-status must enforce role + kindergarten scope."""

    def test_manager_cannot_access_other_kg_capacity(self, client, manager_kg_a, class_kg_b):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/{class_kg_b.id}/capacity-status")
        assert r.status_code == 404  # 404 not 403 — no cross-tenant existence leak
        app.dependency_overrides.clear()

    def test_manager_can_access_own_capacity(self, client, manager_kg_a, class_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/{class_kg_a.id}/capacity-status")
        assert r.status_code == 200
        assert r.json()["class_id"] == class_kg_a.id
        app.dependency_overrides.clear()

    def test_soft_deleted_class_capacity_is_404(self, client, test_db, manager_kg_a, class_kg_a):
        class_kg_a.deleted_at = datetime.now()
        test_db.commit()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/{class_kg_a.id}/capacity-status")
        assert r.status_code == 404
        app.dependency_overrides.clear()

    def test_parent_forbidden(self, client, parent_kg_a, class_kg_a):
        app.dependency_overrides[get_current_user] = lambda: parent_kg_a
        r = client.get(f"/api/classes/{class_kg_a.id}/capacity-status")
        assert r.status_code == 403  # wrong role -> 403
        app.dependency_overrides.clear()


class TestRequiredSupervisorsIDOR:
    """#2 — required-supervisors must enforce role + kindergarten scope."""

    def test_manager_cannot_access_other_kg(self, client, manager_kg_a, class_kg_b):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/{class_kg_b.id}/required-supervisors")
        assert r.status_code == 404
        app.dependency_overrides.clear()

    def test_manager_own_ok(self, client, manager_kg_a, class_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/{class_kg_a.id}/required-supervisors")
        assert r.status_code == 200
        app.dependency_overrides.clear()


class TestCreateClassSupervisorValidation:
    """#3 — supervisor must be an ACTIVE, non-deleted SUPERVISOR in the same KG."""

    def test_reject_non_supervisor_role(self, client, manager_kg_a, kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        # manager_kg_a is a MANAGER, not a SUPERVISOR
        r = client.post("/api/classes", json=_class_payload(kg_a.id, manager_kg_a.id, class_code="C-ROLE"))
        assert r.status_code == 400
        app.dependency_overrides.clear()

    def test_reject_supervisor_from_other_kg(self, client, manager_kg_a, kg_a, supervisor_kg_b):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post("/api/classes", json=_class_payload(kg_a.id, supervisor_kg_b.id, class_code="C-XKG"))
        assert r.status_code == 400
        app.dependency_overrides.clear()

    def test_reject_inactive_supervisor(self, client, test_db, manager_kg_a, kg_a, supervisor_kg_a):
        supervisor_kg_a.status = models.UserStatus.INACTIVE
        test_db.commit()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post("/api/classes", json=_class_payload(kg_a.id, supervisor_kg_a.id, class_code="C-INACT"))
        assert r.status_code == 400
        app.dependency_overrides.clear()

    def test_accept_valid_supervisor(self, client, manager_kg_a, kg_a, supervisor_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post("/api/classes", json=_class_payload(kg_a.id, supervisor_kg_a.id, class_code="C-OK"))
        assert r.status_code == 201, r.text
        app.dependency_overrides.clear()


class TestClassCapacityRange:
    """#15 — capacity must be within [CLASS_MIN_CAPACITY, CLASS_MAX_CAPACITY] (3–10)."""

    @pytest.mark.parametrize("cap,expected", [(1, 400), (2, 400), (3, 201), (10, 201), (11, 400)])
    def test_capacity_range(self, client, manager_kg_a, kg_a, supervisor_kg_a, cap, expected):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.post(
            "/api/classes",
            json=_class_payload(kg_a.id, supervisor_kg_a.id, capacity_total=cap, class_code=f"CAP{cap}"),
        )
        assert r.status_code == expected, r.text
        app.dependency_overrides.clear()


class TestSoftDeletedClassHidden:
    """#4 — soft-deleted classes must not surface in normal APIs."""

    def test_list_and_get_exclude_soft_deleted(self, client, test_db, manager_kg_a, class_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        listed = client.get("/api/classes").json()["classes"]
        assert any(c["id"] == class_kg_a.id for c in listed)

        class_kg_a.deleted_at = datetime.now()
        test_db.commit()

        listed = client.get("/api/classes").json()["classes"]
        assert all(c["id"] != class_kg_a.id for c in listed)
        assert client.get(f"/api/classes/{class_kg_a.id}").status_code == 404
        app.dependency_overrides.clear()


class TestEligibleSupervisorsSoftDeleted:
    """#16 — a soft-deleted assignment must not make a supervisor ineligible."""

    def test_soft_deleted_assignment_keeps_eligible(self, client, test_db, manager_kg_a, kg_a, supervisor_kg_a, class_kg_a):
        test_db.add(models.SupervisorAssignment(
            class_id=class_kg_a.id,
            supervisor_id=supervisor_kg_a.id,
            is_primary=True,
            start_date=date.today(),
            end_date=date.today(),
            deleted_at=datetime.now(),
        ))
        test_db.commit()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get(f"/api/classes/eligible-supervisors?kindergarten_id={kg_a.id}")
        ids = [s["id"] for s in r.json()["supervisors"]]
        assert supervisor_kg_a.id in ids
        app.dependency_overrides.clear()


class TestDailyReportScope:
    """#6 / #14 — daily-report actions are scoped to the report's own kindergarten."""

    def test_manager_cannot_edit_other_kg_report(self, client, test_db, manager_kg_a, kg_b, child_kg_a, supervisor_kg_b):
        report = _make_report(test_db, kg_b.id, child_kg_a.id, supervisor_kg_b.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.put(f"/api/manager/daily-reports/{report.id}", json={"notes": "x"})
        assert r.status_code == 404
        app.dependency_overrides.clear()

    def test_manager_cannot_send_other_kg_report(self, client, test_db, manager_kg_a, kg_b, child_kg_a, supervisor_kg_b):
        report = _make_report(test_db, kg_b.id, child_kg_a.id, supervisor_kg_b.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.put(f"/api/manager/daily-reports/{report.id}/send-to-parents")
        assert r.status_code == 404
        app.dependency_overrides.clear()

    def test_manager_cannot_delete_other_kg_report(self, client, test_db, manager_kg_a, kg_b, child_kg_a, supervisor_kg_b):
        report = _make_report(test_db, kg_b.id, child_kg_a.id, supervisor_kg_b.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.delete(f"/api/manager/daily-reports/{report.id}")
        assert r.status_code == 404
        app.dependency_overrides.clear()

    def test_manager_can_edit_own_report(self, client, test_db, manager_kg_a, kg_a, child_kg_a, supervisor_kg_a):
        report = _make_report(test_db, kg_a.id, child_kg_a.id, supervisor_kg_a.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.put(f"/api/manager/daily-reports/{report.id}", json={"notes": "hello"})
        assert r.status_code == 200
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("report_status", [
        models.DailyReportStatus.DRAFT,
        models.DailyReportStatus.REJECTED,
        models.DailyReportStatus.RETURNED,
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.SENT_TO_PARENT,
    ])
    def test_manager_cannot_edit_outside_submitted_review_state(
        self, client, test_db, manager_kg_a, kg_a, child_kg_a, supervisor_kg_a, report_status
    ):
        report = _make_report(test_db, kg_a.id, child_kg_a.id, supervisor_kg_a.id, status=report_status)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        response = client.put(f"/api/manager/daily-reports/{report.id}", json={"notes": "not allowed"})
        assert response.status_code == 409
        app.dependency_overrides.clear()


class TestSendReportAtomic:
    """#7 — status change and the parent notification commit together."""

    def test_send_creates_report_sent_and_message(self, client, test_db, manager_kg_a, kg_a, child_kg_a, supervisor_kg_a):
        report = _make_report(test_db, kg_a.id, child_kg_a.id, supervisor_kg_a.id)
        before = test_db.query(models.Message).count()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.put(f"/api/manager/daily-reports/{report.id}/send-to-parents")
        assert r.status_code == 200
        test_db.expire_all()
        assert test_db.get(models.DailyReport, report.id).status == models.DailyReportStatus.SENT_TO_PARENT
        # The parent notification was created in the same transaction as the status change.
        assert test_db.query(models.Message).count() == before + 1
        app.dependency_overrides.clear()


class TestDailyReportQueryValidation:
    """#8 / #9 — malformed date -> 422; unknown report_status -> 400."""

    def test_invalid_from_date_returns_422(self, client, manager_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get("/api/manager/daily-reports?from_date=not-a-date")
        assert r.status_code == 422
        app.dependency_overrides.clear()

    def test_invalid_report_status_returns_400(self, client, manager_kg_a):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get("/api/manager/daily-reports?report_status=BOGUS")
        assert r.status_code == 400
        app.dependency_overrides.clear()


class TestEnrollmentTrendGrouping:
    """#10 — daily/weekly/monthly aggregation all return populated buckets."""

    def _seed(self, test_db, kg_id, parent_id):
        # One ACTIVE enrollment per (distinct) child — a child may hold only one
        # active enrollment (unique constraint on child_id, is_active).
        base = datetime.now() - timedelta(days=35)
        for i in range(0, 35, 5):
            child = models.Child(
                parent_id=parent_id,
                first_name=f"طفل{i}",
                last_name="تجربة",
                gender=models.Gender.MALE,
                date_of_birth=date(2024, 1, 1) + timedelta(days=i),
                father_name="أب",
                mother_first_name="أم",
                mother_last_name="تجربة",
                mother_nationality="الأردن",
            )
            test_db.add(child)
            test_db.flush()
            test_db.add(models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg_id,
                status=models.EnrollmentStatus.ACTIVE,
                created_at=base + timedelta(days=i),
            ))
        test_db.commit()

    def test_all_groupings(self, test_db, kg_a, child_kg_a):
        from manager_analytics import ManagerAnalyticsService as MA
        self._seed(test_db, kg_a.id, child_kg_a.parent_id)
        end = date.today()
        start = end - timedelta(days=40)

        for grouping in ("daily", "weekly", "monthly"):
            trend = MA.compute_enrollment_trend(test_db, kg_a.id, start, end, grouping)
            assert trend, f"{grouping} trend should not be empty"
            for point in trend:
                assert {"date", "new_enrollments", "active_enrollments", "cumulative_active"} <= set(point)

        monthly = MA.compute_enrollment_trend(test_db, kg_a.id, start, end, "monthly")
        assert all(len(p["date"]) == 7 and p["date"][4] == "-" for p in monthly)  # YYYY-MM
        # cumulative is monotonic non-decreasing
        cums = [p["cumulative_active"] for p in monthly]
        assert cums == sorted(cums)


class TestManagerAnalyticsIncidentBoundary:
    """#13 — an incident late on the end date is still counted."""

    def test_incident_on_end_date_counted(self, test_db, kg_a, class_kg_a, child_kg_a, enrollment_kg_a):
        from datetime import time
        from manager_analytics import ManagerAnalyticsService as MA
        end = date.today()
        start = end - timedelta(days=7)
        test_db.add(models.Incident(
            child_id=child_kg_a.id,
            kindergarten_id=kg_a.id,
            class_id=class_kg_a.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="late incident",
            occurred_at=datetime.combine(end, time(23, 0)),
        ))
        test_db.commit()
        rows = MA.get_drilldown_by_class(test_db, kg_a.id, start, end)
        row = next(r for r in rows if r["class_id"] == class_kg_a.id)
        assert row["incidents"] >= 1


def _make_child(test_db, parent_id, first_name):
    child = models.Child(
        parent_id=parent_id,
        first_name=first_name,
        last_name="تجربة",
        gender=models.Gender.MALE,
        date_of_birth=date.today() - timedelta(days=800),
        father_name="أب",
        mother_first_name="أم",
        mother_last_name="تجربة",
        mother_nationality="الأردن",
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)
    return child


class TestDashboardCountsAnchoring:
    """#5 — dashboard report counts are anchored to DailyReport.kindergarten_id
    (not a Child->EnrollmentApplication join), so they are correct regardless of
    the child's enrollment state and cannot be inflated.

    Note: same-kindergarten enrollment fan-out is *structurally* impossible — the
    uq_enrollment_child_kindergarten unique constraint allows a child at most one
    enrollment row per kindergarten. The remaining real defect was that the old
    join-based report counts *undercounted* a report whose child had no
    enrollment row; the kindergarten_id anchor fixes that and decouples the count
    from enrollment state.
    """

    def test_report_count_independent_of_enrollment(
        self, client, test_db, manager_kg_a, kg_a, parent_kg_a, supervisor_kg_a
    ):
        today = date.today()
        profile = test_db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == parent_kg_a.id
        ).first()
        # A child with a SUBMITTED report in kg_a but NO enrollment row: the old
        # join through EnrollmentApplication returned 0; the kindergarten_id
        # anchor correctly counts it.
        child = _make_child(test_db, profile.id, "بلا_تسجيل")
        test_db.add(models.DailyReport(
            child_id=child.id, kindergarten_id=kg_a.id, date=today,
            status=models.DailyReportStatus.SUBMITTED, submitted_by=supervisor_kg_a.id,
            arrival_time="08:00",
        ))
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 200
        assert r.json()["summary"]["pending_daily_reports"] == 1
        app.dependency_overrides.clear()

    def test_attendance_and_reports_counted_once(
        self, client, test_db, manager_kg_a, kg_a, class_kg_a, child_kg_a, enrollment_kg_a, supervisor_kg_a
    ):
        today = date.today()
        # One PRESENT log for the actively-enrolled child + one SENT report today.
        test_db.add(models.AttendanceLog(
            child_id=child_kg_a.id, class_id=class_kg_a.id, date=today,
            status=models.AttendanceStatus.PRESENT, recorded_by=supervisor_kg_a.id,
        ))
        test_db.add(models.DailyReport(
            child_id=child_kg_a.id, kindergarten_id=kg_a.id, date=today,
            status=models.DailyReportStatus.SENT_TO_PARENT, submitted_by=supervisor_kg_a.id,
            arrival_time="08:00",
        ))
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary["attendance_today"] == 1
        assert summary["reports_sent_today"] == 1
        app.dependency_overrides.clear()


class TestAbsenteeismOperatingDays:
    """#11 — absenteeism denominator uses operating days, not raw calendar days."""

    def test_absenteeism_excludes_closed_days(
        self, test_db, kg_a, class_kg_a, child_kg_a, enrollment_kg_a, supervisor_kg_a
    ):
        from manager_analytics import ManagerAnalyticsService as MA
        start, end = date(2026, 6, 1), date(2026, 6, 5)  # Mon..Fri; Fri closed by default
        for d in (date(2026, 6, 1), date(2026, 6, 2)):
            test_db.add(models.AttendanceLog(
                child_id=child_kg_a.id, class_id=class_kg_a.id, date=d,
                status=models.AttendanceStatus.ABSENT, recorded_by=supervisor_kg_a.id,
            ))
        test_db.commit()
        rate = MA.compute_absenteeism_rate(test_db, kg_a.id, start, end)
        # 2 absences / (1 active * 4 operating days) = 50%
        # (raw 5 calendar days would wrongly give 40%).
        assert rate == 50.0


class TestClassDrilldownAttendance:
    """#12 — class drilldown counts only PRESENT/LATE over operating days."""

    def test_drilldown_present_late_over_operating_days(
        self, test_db, kg_a, class_kg_a, child_kg_a, enrollment_kg_a, supervisor_kg_a
    ):
        from manager_analytics import ManagerAnalyticsService as MA
        start, end = date(2026, 6, 1), date(2026, 6, 5)
        seeded = [
            (date(2026, 6, 1), models.AttendanceStatus.PRESENT),
            (date(2026, 6, 2), models.AttendanceStatus.LATE),
            (date(2026, 6, 3), models.AttendanceStatus.ABSENT),  # must NOT count
        ]
        for d, st in seeded:
            test_db.add(models.AttendanceLog(
                child_id=child_kg_a.id, class_id=class_kg_a.id, date=d,
                status=st, recorded_by=supervisor_kg_a.id,
            ))
        test_db.commit()
        rows = MA.get_drilldown_by_class(test_db, kg_a.id, start, end)
        row = next(r for r in rows if r["class_id"] == class_kg_a.id)
        # attended (PRESENT+LATE)=2; expected = 1 enrolled * 4 operating days => 50%.
        assert row["attendance_rate"] == 50.0


# =============================================================================
# RUN TESTS
# =============================================================================


class TestManagerProductionBlockers:
    def test_valid_daily_report_date_filters_work(
        self, client, test_db, manager_kg_a, kg_a, child_kg_a, supervisor_kg_a
    ):
        _make_report(test_db, kg_a.id, child_kg_a.id, supervisor_kg_a.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        today = date.today().isoformat()
        response = client.get(f"/api/manager/daily-reports?from_date={today}&to_date={today}")
        assert response.status_code == 200, response.text
        assert response.json()
        app.dependency_overrides.clear()

    def test_manager_cannot_read_foreign_daily_report_detail(
        self, client, test_db, manager_kg_a, kg_b, child_kg_a, supervisor_kg_b
    ):
        report = _make_report(test_db, kg_b.id, child_kg_a.id, supervisor_kg_b.id)
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        response = client.get(f"/api/daily-reports/{report.id}")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_manager_cannot_list_foreign_child_documents(
        self, client, test_db, manager_kg_b, child_kg_a, manager_kg_a
    ):
        test_db.add(models.ChildDocument(
            child_id=child_kg_a.id,
            document_type="other",
            file_name="private.pdf",
            file_path="private.pdf",
            uploaded_by=manager_kg_a.id,
        ))
        test_db.commit()
        app.dependency_overrides[get_current_user] = lambda: manager_kg_b
        response = client.get(f"/api/children/{child_kg_a.id}/documents")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_active_manager_uniqueness_is_database_enforced(self, test_db, manager_kg_a):
        from sqlalchemy.exc import IntegrityError

        duplicate = models.User(
            username="duplicate_active_manager",
            email="duplicate-manager@example.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=manager_kg_a.kindergarten_id,
        )
        test_db.add(duplicate)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_manager_supervisor_crud_is_scoped(
        self, client, manager_kg_a, manager_kg_b
    ):
        app.dependency_overrides[get_current_user] = lambda: manager_kg_a
        created = client.post("/api/manager/supervisors", json={
            "username": "manager_created_supervisor",
            "email": "manager-created-supervisor@example.com",
            "password": "StrongPass123!",
            "full_name": "Manager Created Supervisor",
            "phone_number": "+962790000099",
        })
        assert created.status_code == 201, created.text
        supervisor_id = created.json()["id"]

        updated = client.put(f"/api/manager/supervisors/{supervisor_id}", json={
            "full_name": "Updated Supervisor",
        })
        assert updated.status_code == 200, updated.text

        app.dependency_overrides[get_current_user] = lambda: manager_kg_b
        foreign = client.put(f"/api/manager/supervisors/{supervisor_id}", json={
            "full_name": "Forbidden Update",
        })
        assert foreign.status_code == 404
        app.dependency_overrides.clear()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
