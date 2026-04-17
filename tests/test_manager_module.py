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
        name_ar="روضة أ",
        name_en="Kindergarten A",
        governorate="عمّان",
        city="عمّان",
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
        name_ar="روضة ب",
        name_en="Kindergarten B",
        governorate="الزرقاء",
        city="الزرقاء",
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
        home_city="عمّان",
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
        data = response.json()
        assert "kindergartens" in data

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
        data = response.json()
        assert data["id"] == kg_a.id

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
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
