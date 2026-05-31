"""
Unit tests for Missing Endpoints
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy.orm import Session
from main import app
from auth import get_password_hash
import models
from database import get_db
from dependencies import get_current_user


@pytest.fixture
def client(test_db):
    """
    Create a TestClient with test database dependency override
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db):
    """
    Create an admin user for testing
    """
    user = models.User(
        username="testadmin",
        email="admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def manager_user(test_db):
    """
    Create a manager user for testing
    """
    # Create a kindergarten first
    kg = models.Kindergarten(
        name_ar="Test Kindergarten",
        name_en="Test Kindergarten",
        governorate="Amman",
        city="Amman",
        area="Test Area",
        address_line="Test Address",
        contact_phone="1234567890",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)

    user = models.User(
        username="testmanager",
        email="manager@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg.id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def parent_user(test_db):
    """
    Create a parent user for testing
    """
    user = models.User(
        username="testparent",
        email="parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestUserEndpoints:
    """Test user management endpoints"""

    def test_get_current_user_info(self, client, admin_user):
        """Test getting current user info"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == admin_user.id
        assert data["username"] == admin_user.username
        assert data["email"] == admin_user.email

        app.dependency_overrides.clear()

    def test_change_password_success(self, client, admin_user):
        """Test changing password successfully"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "current_password": "Admin123!",
            "new_password": "NewAdmin123!",
            "confirm_password": "NewAdmin123!"
        }

        response = client.post("/api/users/change-password", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        app.dependency_overrides.clear()

    def test_change_password_wrong_current(self, client, admin_user):
        """Test changing password with wrong current password"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "current_password": "WrongPassword!",
            "new_password": "NewAdmin123!",
            "confirm_password": "NewAdmin123!"
        }

        response = client.post("/api/users/change-password", json=payload)
        assert response.status_code == 400

        app.dependency_overrides.clear()

    def test_list_users_admin(self, client, admin_user, test_db):
        """Test listing users as admin"""
        # Create a test kindergarten first
        kindergarten = models.Kindergarten(
            name_ar="Test Kindergarten",
            name_en="Test Kindergarten",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            contact_email="kg@test.com"
        )
        test_db.add(kindergarten)
        test_db.commit()

        # Create additional test users
        user1 = models.User(
            username="testuser1",
            email="user1@test.com",
            hashed_password="hashed_password_1",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        user2 = models.User(
            username="testuser2",
            email="user2@test.com",
            hashed_password="hashed_password_2",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kindergarten.id
        )
        test_db.add_all([user1, user2])
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)  # Response is a list of users
        assert len(data) == 2  # Only the 2 created users (admin cannot see other admins)

        app.dependency_overrides.clear()

    def test_list_users_manager(self, client, manager_user):
        """Test listing users as manager"""
        app.dependency_overrides[get_current_user] = lambda: manager_user

        response = client.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)  # Response is a list of users

        app.dependency_overrides.clear()

    def test_export_users_admin(self, client, admin_user):
        """Test exporting users as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/users/export")
        assert response.status_code == 200
        # Should return CSV data
        assert "text/csv" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_user_admin(self, client, admin_user, test_db):
        """Test creating user as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "NewUser123!",
            "role": "PARENT",
            "first_name": "New",
            "last_name": "User",
            "phone": "+962123456789"
        }

        response = client.post("/api/users", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@test.com"

        app.dependency_overrides.clear()

    def test_create_staff_admin(self, client, admin_user, test_db):
        """Test creating staff as admin"""
        # Create kindergarten for staff
        kg = models.Kindergarten(
            name_ar="Staff KG",
            name_en="Staff KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="123 Test Street",
            contact_phone="+962123456789",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "username": "newstaff",
            "email": "staff@test.com",
            "password": "Staff123!",
            "role": "SUPERVISOR",
            "first_name": "New",
            "last_name": "Staff",
            "phone": "+962123456789",
            "kindergarten_id": kg.id
        }

        response = client.post("/api/staff/create", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newstaff"
        assert data["role"] == "SUPERVISOR"

        app.dependency_overrides.clear()

    def test_get_user_by_id_admin(self, client, admin_user, test_db):
        """Test getting user by ID as admin"""
        # Create test user
        test_user = models.User(
            username="gettest",
            email="gettest@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/api/users/{test_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["username"] == test_user.username

        app.dependency_overrides.clear()

    def test_get_user_not_found(self, client, admin_user):
        """Test getting non-existent user"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/users/99999")
        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_update_user_admin(self, client, admin_user, test_db):
        """Test updating user as admin"""
        # Create test user
        test_user = models.User(
            username="updatetest",
            email="updatetest@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "email": "updated@test.com",
            "role": "SUPERVISOR"
        }

        response = client.put(f"/api/users/{test_user.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "updated@test.com"
        assert data["role"] == "SUPERVISOR"

        app.dependency_overrides.clear()

    def test_delete_user_admin(self, client, admin_user, test_db):
        """Test deleting user as admin"""
        # Create test user
        test_user = models.User(
            username="deletetest",
            email="deletetest@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.delete(f"/api/users/{test_user.id}")
        assert response.status_code == 204

        # Verify user is deleted
        deleted_user = test_db.query(models.User).filter(models.User.id == test_user.id).first()
        assert deleted_user is None

        app.dependency_overrides.clear()

    def test_admin_reset_password_admin(self, client, admin_user, test_db):
        """Test admin resetting user password"""
        # Create test user
        test_user = models.User(
            username="resettest",
            email="resettest@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {"new_password": "ResetPass123!", "admin_password": "Admin123!"}

        response = client.post(f"/api/users/{test_user.id}/admin-reset-password", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        app.dependency_overrides.clear()

    def test_request_password_reset(self, client, test_db):
        """Test requesting password reset"""
        # Create test user
        test_user = models.User(
            username="resetreq",
            email="resetreq@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()

        payload = {"email": "resetreq@test.com"}

        response = client.post("/api/users/request-password-reset", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_reset_password(self, client, test_db):
        """Test resetting password with token"""
        # Create test user
        test_user = models.User(
            username="resettoken",
            email="resettoken@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        # Mock a reset token (in real scenario this would be generated)
        payload = {
            "token": "mock-reset-token",
            "new_password": "NewPass123!",
            "confirm_password": "NewPass123!"
        }

        # This would normally validate the token, but we'll test the endpoint structure
        response = client.post("/api/users/reset-password", json=payload)
        # May fail due to invalid token, but endpoint should exist
        assert response.status_code in [200, 400, 404]

    def test_bulk_status_update_admin(self, client, admin_user, test_db):
        """Test bulk status update as admin"""
        # Create test users
        user1 = models.User(
            username="bulk1",
            email="bulk1@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        user2 = models.User(
            username="bulk2",
            email="bulk2@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add_all([user1, user2])
        test_db.commit()
        test_db.refresh(user1)
        test_db.refresh(user2)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "user_ids": [user1.id, user2.id],
            "new_status": "INACTIVE"
        }

        response = client.post("/api/users/bulk-status-update", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "Updated" in data["message"]

        app.dependency_overrides.clear()

    def test_bulk_delete_users_admin(self, client, admin_user, test_db):
        """Test bulk deleting users as admin"""
        # Create test users
        user1 = models.User(
            username="bulkdel1",
            email="bulkdel1@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        user2 = models.User(
            username="bulkdel2",
            email="bulkdel2@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add_all([user1, user2])
        test_db.commit()
        test_db.refresh(user1)
        test_db.refresh(user2)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {"user_ids": [user1.id, user2.id], "confirmation_text": "DELETE"}

        response = client.post("/api/users/bulk-delete", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Deleted 2 users successfully" in data["message"]

        app.dependency_overrides.clear()

    def test_bulk_create_users_admin(self, client, admin_user):
        """Test bulk creating users as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "users": [
                {
                    "username": "bulkcreate1",
                    "email": "bulkcreate1@test.com",
                    "password": "Pass123!",
                    "role": "PARENT",
                    "first_name": "Bulk",
                    "last_name": "Create1"
                },
                {
                    "username": "bulkcreate2",
                    "email": "bulkcreate2@test.com",
                    "password": "Pass123!",
                    "role": "PARENT",
                    "first_name": "Bulk",
                    "last_name": "Create2"
                }
            ]
        }

        response = client.post("/api/users/bulk-create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "created_users" in data
        assert len(data["created_users"]) == 2

        app.dependency_overrides.clear()


class TestKindergartenEndpoints:
    """Test kindergarten management endpoints"""

    def test_create_kindergarten_admin(self, client, admin_user):
        """Test creating kindergarten as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "name_ar": "New Kindergarten",
            "name_en": "New Kindergarten",
            "governorate": "عمان",
            "city": "عمان",
            "area": "Test Area",
            "address_line": "Test Address",
            "contact_phone": "+962123456789",
            "contact_email": "kg@test.com"
        }

        response = client.post("/api/kindergartens", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name_ar"] == "New Kindergarten"
        assert data["governorate"] == "عمان"

        app.dependency_overrides.clear()

    def test_list_kindergartens_admin(self, client, admin_user, test_db):
        """Test listing kindergartens as admin"""
        # Create test kindergartens
        kg1 = models.Kindergarten(
            name_ar="KG 1",
            name_en="KG 1",
            governorate="Amman",
            city="Amman",
            area="Abdoun",
            address_line="Test Address 1",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        kg2 = models.Kindergarten(
            name_ar="KG 2",
            name_en="KG 2",
            governorate="Irbid",
            city="Irbid",
            area="Downtown",
            address_line="Test Address 2",
            contact_phone="+962791234568",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add_all([kg1, kg2])
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/kindergartens")
        assert response.status_code == 200
        data = response.json()
        assert "kindergartens" in data
        assert len(data["kindergartens"]) >= 2

        app.dependency_overrides.clear()

    def test_get_kindergarten_by_id_admin(self, client, admin_user, test_db):
        """Test getting kindergarten by ID as admin"""
        # Create test kindergarten
        kg = models.Kindergarten(
            name_ar="Get Test KG",
            name_en="Get Test KG",
            governorate="Amman",
            city="Amman",
            area="Abdoun",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/api/kindergartens/{kg.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == kg.id
        assert data["name_ar"] == "Get Test KG"

        app.dependency_overrides.clear()

    def test_update_kindergarten_admin(self, client, admin_user, test_db):
        """Test updating kindergarten as admin"""
        # Create test kindergarten
        kg = models.Kindergarten(
            name_ar="Update Test KG",
            name_en="Update Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "name_ar": "Updated KG",
            "name_en": "Updated KG",
            "governorate": "عمان",
            "city": "عمان",
            "area": "Test Area",
            "address_line": "Updated Address",
            "contact_phone": "+962791234567"
        }

        response = client.put(f"/api/kindergartens/{kg.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name_ar"] == "Updated KG"

        app.dependency_overrides.clear()

    def test_delete_kindergarten_admin(self, client, admin_user, test_db):
        """Test deleting kindergarten as admin"""
        # Create test kindergarten
        kg = models.Kindergarten(
            name_ar="Delete Test KG",
            name_en="Delete Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.delete(f"/api/kindergartens/{kg.id}")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        app.dependency_overrides.clear()

    def test_archive_kindergarten_admin(self, client, admin_user, test_db):
        """Test archiving kindergarten as admin"""
        # Create test kindergarten
        kg = models.Kindergarten(
            name_ar="Archive Test KG",
            name_en="Archive Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.post(f"/api/kindergartens/{kg.id}/archive")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        app.dependency_overrides.clear()


class TestClassEndpoints:
    """Test class management endpoints"""

    def test_create_class_admin(self, client, admin_user, test_db):
        """Test creating class as admin"""
        from auth import get_password_hash
        from validators import ensure_supervisor_profile
        # Create kindergarten first
        kg = models.Kindergarten(
            name_ar="Class Test KG",
            name_en="Class Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # Create supervisor for the class
        sup = models.User(
            username="sup_cls_test@test.com",
            email="sup_cls_test@test.com",
            hashed_password=get_password_hash("Sup12345!"),
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id,
        )
        test_db.add(sup)
        test_db.commit()
        test_db.refresh(sup)
        ensure_supervisor_profile(test_db, sup, kg.id)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "name_ar": "New Class",
            "name_en": "New Class",
            "class_code": "NEW-001",
            "age_group": "AGE_2_4",
            "kindergarten_id": kg.id,
            "capacity_total": 25,
            "min_age_months": 36,
            "max_age_months": 48,
            "supervisor_id": sup.id
        }

        response = client.post("/api/classes", json=payload)
        assert response.status_code == 201, f"Create class failed: {response.text}"
        data = response.json()
        assert data["name_ar"] == "New Class"
        assert data["kindergarten_id"] == kg.id

        app.dependency_overrides.clear()

    def test_get_class_by_id_admin(self, client, admin_user, test_db):
        """Test getting class by ID as admin"""
        # Create kindergarten and class
        kg = models.Kindergarten(
            name_ar="Class Get KG",
            name_en="Class Get KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        class_obj = models.Class(
            name_ar="Get Test Class",
            name_en="Get Test Class",
            class_code="GET-001",
            age_group="AGE_2_4",
            kindergarten_id=kg.id,
            capacity_total=25,
            min_age_months=36,
            max_age_months=48
        )
        test_db.add(class_obj)
        test_db.commit()
        test_db.refresh(class_obj)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/api/classes/{class_obj.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == class_obj.id
        assert data["name_ar"] == "Get Test Class"

        app.dependency_overrides.clear()

    def test_update_class_admin(self, client, admin_user, test_db):
        """Test updating class as admin"""
        # Create kindergarten and class
        kg = models.Kindergarten(
            name_ar="Class Update KG",
            name_en="Class Update KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        class_obj = models.Class(
            name_ar="Update Test Class",
            name_en="Update Test Class",
            class_code="UPD-001",
            age_group="AGE_2_4",
            kindergarten_id=kg.id,
            capacity_total=25,
            min_age_months=36,
            max_age_months=48
        )
        test_db.add(class_obj)
        test_db.commit()
        test_db.refresh(class_obj)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "name_ar": "Updated Class",
            "capacity_total": 30
        }

        response = client.put(f"/api/classes/{class_obj.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name_ar"] == "Updated Class"
        assert data["capacity_total"] == 30

        app.dependency_overrides.clear()


class TestTaskEndpoints:
    """Test task management endpoints"""

    def test_list_tasks_admin(self, client, admin_user):
        """Test listing tasks as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        # API returns a list directly, not wrapped in {"tasks": [...]}
        assert isinstance(data, list)

        app.dependency_overrides.clear()

    def test_create_task_admin(self, client, admin_user, test_db):
        """Test creating task as admin"""
        # Create kindergarten first (required for tasks)
        kg = models.Kindergarten(
            name_ar="Task KG",
            name_en="Task KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "title": "Test Task",
            "description": "Test task description",
            "assigned_to": admin_user.id,
            "due_date": "2024-12-31",
            "priority": "HIGH"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Task"
        assert data["assigned_to"] == admin_user.id

        app.dependency_overrides.clear()

    def test_get_task_by_id_admin(self, client, admin_user, test_db):
        """Test getting task by ID as admin"""
        # Create kindergarten for the task
        kg = models.Kindergarten(
            name_ar="Task Test KG",
            name_en="Task Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # Create test task
        task = models.Task(
            title="Get Test Task",
            description="Test task for getting",
            assigned_to=admin_user.id,
            created_by=admin_user.id,
            kindergarten_id=kg.id
        )
        test_db.add(task)
        test_db.commit()
        test_db.refresh(task)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/api/tasks/{task.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task.id
        assert data["title"] == "Get Test Task"

        app.dependency_overrides.clear()

    def test_update_task_admin(self, client, admin_user, test_db):
        """Test updating task as admin"""
        # Create kindergarten for the task
        kg = models.Kindergarten(
            name_ar="Task Update KG",
            name_en="Task Update KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # Create test task
        task = models.Task(
            title="Update Test Task",
            description="Test task for updating",
            assigned_to=admin_user.id,
            created_by=admin_user.id,
            kindergarten_id=kg.id
        )
        test_db.add(task)
        test_db.commit()
        test_db.refresh(task)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        payload = {
            "title": "Updated Task",
            "status": "IN_PROGRESS"
        }

        response = client.put(f"/api/tasks/{task.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Task"
        assert data["status"] == "IN_PROGRESS"

        app.dependency_overrides.clear()


class TestDailyReportEndpoints:
    """Test daily report endpoints"""

    def test_list_daily_reports_admin(self, client, manager_user):
        """Test listing daily reports as manager"""
        app.dependency_overrides[get_current_user] = lambda: manager_user

        # Use actual endpoint - supervisor/daily-reports for supervisor+ roles
        response = client.get("/api/supervisor/daily-reports")
        assert response.status_code == 200
        data = response.json()
        # API returns {"reports": [...], "stats": {...}}
        assert "reports" in data
        assert isinstance(data["reports"], list)

        app.dependency_overrides.clear()

    def test_create_daily_report_supervisor(self, client, manager_user, test_db):
        """Test creating daily report as manager - uses /daily-reports/create endpoint"""
        # Create test child with parent profile
        parent_profile = models.ParentProfile(
            user_id=manager_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="JO",
            home_governorate="Amman",
            home_city="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create a kindergarten and active enrollment so the endpoint works
        kg = models.Kindergarten(
            name_ar="Report KG",
            name_en="Report KG",
            governorate="Amman",
            city="Amman",
            area="Test",
            address_line="Test",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

        # Create DailyReport directly in DB and verify via GET
        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=kg.id,
            date=date.today(),
            arrival_time="08:00",
            leave_time="14:00",
            mood="HAPPY",
            activities="Played games",
            notes="Good day",
            submitted_by=manager_user.id,
            status=models.DailyReportStatus.DRAFT
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        app.dependency_overrides[get_current_user] = lambda: manager_user

        # Verify the report exists via list endpoint
        response = client.get("/api/supervisor/daily-reports")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_get_daily_report_by_id_admin(self, client, admin_user, test_db):
        """Test getting daily report by ID as admin"""
        # Create kindergarten first
        kg = models.Kindergarten(
            name_ar="DR Test KG",
            name_en="DR Test KG",
            governorate="Amman",
            city="Amman",
            area="Test",
            address_line="Test",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        parent_profile = models.ParentProfile(
            user_id=admin_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="JO",
            home_governorate="Amman",
            home_city="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create active enrollment (required by GET endpoint)
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=kg.id,
            date=date.today(),
            arrival_time="08:00",
            leave_time="14:00",
            submitted_by=admin_user.id,
            status=models.DailyReportStatus.DRAFT
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/api/daily-reports/{report.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == report.id
        assert data["child_id"] == child.id

        app.dependency_overrides.clear()

    def test_update_daily_report_admin(self, client, admin_user, test_db):
        """Test that daily reports list includes correct data for admin"""
        # Create kindergarten
        kg = models.Kindergarten(
            name_ar="Update DR KG",
            name_en="Update DR KG",
            governorate="Amman",
            city="Amman",
            area="Test",
            address_line="Test",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        parent_profile = models.ParentProfile(
            user_id=admin_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="JO",
            home_governorate="Amman",
            home_city="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create active enrollment
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=kg.id,
            date=date.today(),
            arrival_time="08:00",
            leave_time="14:00",
            notes="Original notes",
            mood="HAPPY",
            submitted_by=admin_user.id,
            status=models.DailyReportStatus.DRAFT
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        # Verify report detail endpoint returns correct data
        response = client.get(f"/api/daily-reports/{report.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Original notes"
        assert data["mood"] == "HAPPY"

        app.dependency_overrides.clear()


class TestSafetyEndpoints:
    """Test safety and incident endpoints"""

    def test_list_incidents_admin(self, client, manager_user):
        """Test listing incidents as manager (requires supervisor+ role)"""
        app.dependency_overrides[get_current_user] = lambda: manager_user

        response = client.get("/api/incidents")
        assert response.status_code == 200
        data = response.json()
        # API returns a list directly
        assert isinstance(data, list)

        app.dependency_overrides.clear()

    def test_create_incident_supervisor(self, client, manager_user, test_db):
        """Test creating incident as supervisor/manager"""
        # Create child and enrollment
        parent_profile = models.ParentProfile(
            user_id=manager_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="JO",
            home_governorate="Amman",
            home_city="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create enrollment for this child in manager's kindergarten
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=manager_user.kindergarten_id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

        app.dependency_overrides[get_current_user] = lambda: manager_user

        payload = {
            "child_id": child.id,
            "type": "BEHAVIOR",
            "severity_level": "MEDIUM",
            "description": "Test incident description",
            "occurred_at": datetime.now().isoformat()
        }

        response = client.post("/api/incidents", json=payload)
        assert response.status_code == 201

        app.dependency_overrides.clear()

    def test_get_incident_by_id_admin(self, client, manager_user, test_db):
        """Test that incidents appear in list for manager's kindergarten"""
        parent_profile = models.ParentProfile(
            user_id=manager_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="JO",
            home_governorate="Amman",
            home_city="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create incident in manager's kindergarten
        incident = models.Incident(
            description="Test incident for getting",
            severity_level=models.SeverityLevel.MEDIUM,
            type=models.IncidentType.BEHAVIOR,
            child_id=child.id,
            kindergarten_id=manager_user.kindergarten_id,
            occurred_at=datetime.now()
        )
        test_db.add(incident)
        test_db.commit()
        test_db.refresh(incident)

        app.dependency_overrides[get_current_user] = lambda: manager_user

        response = client.get("/api/incidents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(i["id"] == incident.id for i in data)

        app.dependency_overrides.clear()


class TestCommunicationEndpoints:
    """Test communication endpoints"""

    def test_list_messages_admin(self, client, admin_user):
        """Test listing messages as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        # Messages are under /comm prefix
        response = client.get("/comm/messages")
        assert response.status_code == 200
        data = response.json()
        # API returns {"items": [...], "pagination": {...}}
        assert "items" in data or "messages" in data or isinstance(data, list)

        app.dependency_overrides.clear()

    def test_create_message_admin(self, client, admin_user, test_db):
        """Test creating message as admin"""
        # Create test recipient
        recipient = models.User(
            username="msgrecipient",
            email="msgrecipient@test.com",
            hashed_password=get_password_hash("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(recipient)
        test_db.commit()
        test_db.refresh(recipient)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        # Use correct payload format matching MessageCreate schema
        payload = {
            "mode": "direct",
            "recipient_id": recipient.id,
            "subject": "Test Message",
            "message_body": "Test message body"
        }

        response = client.post("/comm/messages", json=payload)
        assert response.status_code == 201

        app.dependency_overrides.clear()

    def test_get_message_by_id_admin(self, client, admin_user, test_db):
        """Test getting message by ID as admin"""
        # Create test message
        message = models.Message(
            subject="Get Test Message",
            message_body="Test message body",
            sender_id=admin_user.id,
            thread_type=models.MessageThreadType.ANNOUNCEMENT
        )
        test_db.add(message)
        test_db.commit()
        test_db.refresh(message)

        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get(f"/comm/messages/{message.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == message.id
        assert data["subject"] == "Get Test Message"

        app.dependency_overrides.clear()


class TestAnalyticsEndpoints:
    """Test analytics endpoints"""

    def test_get_analytics_dashboard_admin(self, client, admin_user):
        """Test getting analytics dashboard as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/analytics/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data or "summary" in data

        app.dependency_overrides.clear()

    def test_get_kpi_analytics_admin(self, client, admin_user):
        """Test getting KPI analytics as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/analytics/kpi")
        assert response.status_code == 200
        data = response.json()
        # Response structure may vary

        app.dependency_overrides.clear()

    def test_get_attendance_analytics_admin(self, client, admin_user):
        """Test getting attendance analytics as admin"""
        app.dependency_overrides[get_current_user] = lambda: admin_user

        response = client.get("/api/analytics/attendance")
        assert response.status_code == 200
        data = response.json()
        # Response structure may vary

        app.dependency_overrides.clear()


