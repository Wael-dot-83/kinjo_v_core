"""
Pytest configuration and fixtures for integration tests
"""
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import date, datetime

# Set testing environment BEFORE importing app
os.environ["TESTING"] = "true"

from database import Base, get_db
from main import app
from auth import get_password_hash
import models


# Register adapters/converters for date/datetime types to silence Python 3.12+
# deprecation warnings about implicit datetime adaptation in sqlite3.
sqlite3.register_adapter(date, lambda v: v.isoformat())
sqlite3.register_adapter(datetime, lambda v: v.isoformat())

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    """
    Create a fresh test database for each test function
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
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
def sample_kindergarten(test_db):
    """
    Create a sample kindergarten for testing
    """
    kindergarten = models.Kindergarten(
        name_ar="روضة الأمل",
        name_en="Hope Kindergarten",
        license_number="LIC-2026-001",
        governorate="Amman",
        city="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@hope.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31)
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)
    return kindergarten


@pytest.fixture
def sample_class(test_db, sample_kindergarten):
    """
    Create a sample class for testing
    """
    class_obj = models.Class(
        kindergarten_id=sample_kindergarten.id,
        name_ar="الصف الأول",
        name_en="Class A",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True
    )
    test_db.add(class_obj)
    test_db.commit()
    test_db.refresh(class_obj)
    return class_obj


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
def manager_user(test_db, sample_kindergarten):
    """
    Create a manager user for testing
    """
    user = models.User(
        username="testmanager",
        email="manager@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=sample_kindergarten.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def supervisor_user(test_db, sample_kindergarten):
    """
    Create a supervisor user for testing
    """
    user = models.User(
        username="testsupervisor",
        email="supervisor@test.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=sample_kindergarten.id,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def parent_user(test_db):
    """
    Create a parent user with profile for testing
    """
    user = models.User(
        username="testparent@test.com",
        email="testparent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Create parent profile
    profile = models.ParentProfile(
        user_id=user.id,
        first_name="Ahmad",
        last_name="Al-Rashid",
        phone_number="+962791234567",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id="1234567890",
        home_governorate="Amman",
        home_city="Amman",
        home_area="Abdoun",
        home_address_line="123 Main Street",
        correspondence_preference=True
    )
    test_db.add(profile)
    test_db.commit()
    test_db.refresh(profile)

    user.parent = profile
    return user


@pytest.fixture
def sample_child(test_db, parent_user):
    """
    Create a sample child for testing
    """
    child = models.Child(
        parent_id=parent_user.id,
        first_name="Layla",
        last_name="Al-Rashid",
        gender=models.Gender.FEMALE,
        date_of_birth=date(2022, 1, 15),  # ~4 years old
        father_name="Ahmad Al-Rashid",
        mother_first_name="Fatima",
        mother_last_name="Hassan",
        mother_nationality="Jordanian",
        mother_national_id="0987654321",
        media_consent=True
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)
    return child


@pytest.fixture
def admin_token(client, admin_user):
    """
    Get authentication token for admin user
    """
    response = client.post(
        "/token",
        data={
            "username": "testadmin",
            "password": "Admin123!"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def manager_token(client, manager_user):
    """
    Get authentication token for manager user
    """
    response = client.post(
        "/token",
        data={
            "username": "testmanager",
            "password": "Manager123!"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def supervisor_token(client, supervisor_user):
    """
    Get authentication token for supervisor user
    """
    response = client.post(
        "/token",
        data={
            "username": "testsupervisor",
            "password": "Supervisor123!"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def parent_token(client, parent_user):
    """
    Get authentication token for parent user
    """
    response = client.post(
        "/token",
        data={
            "username": "testparent@test.com",
            "password": "Parent123!"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers_admin(admin_token):
    """
    Get authentication headers for admin
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def auth_headers_manager(manager_token):
    """
    Get authentication headers for manager
    """
    return {"Authorization": f"Bearer {manager_token}"}


@pytest.fixture
def auth_headers_supervisor(supervisor_token):
    """
    Get authentication headers for supervisor
    """
    return {"Authorization": f"Bearer {supervisor_token}"}


@pytest.fixture
def auth_headers_parent(parent_token):
    """
    Get authentication headers for parent
    """
    return {"Authorization": f"Bearer {parent_token}"}
