"""
Pytest configuration and fixtures for integration tests
"""
import os
import shutil
import uuid
import pytest
import secrets
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import date, datetime, timedelta

# Set testing environment BEFORE importing app
os.environ["TESTING"] = "true"

from database import Base, get_db
from main import app
from auth import get_password_hash
import models


# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def tmp_path():
    """
    Provide a workspace-backed temp directory.
    This avoids host temp-directory permission issues on Windows.
    """
    base_dir = Path(__file__).resolve().parent / ".tmp" / "pytest-fixtures"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"tmp_path_{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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
        class_code="A001",
        age_group="AGE_1_2",
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

    user.parent_profile = profile
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def sample_child(test_db, parent_user):
    """
    Create a sample child for testing
    """
    child = models.Child(
        parent_id=parent_user.parent_profile.id,
        first_name="Layla",
        last_name="Al-Rashid",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
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
def parent_enrollment(test_db, sample_child, sample_kindergarten):
    """
    Create an active enrollment for the sample child
    """
    enrollment = models.EnrollmentApplication(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACCEPTED
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)
    return enrollment


@pytest.fixture
def active_enrollment(test_db, sample_child, sample_kindergarten, sample_class):
    """
    Create an ACTIVE enrollment for absence-request tests.
    """
    enrollment = models.EnrollmentApplication(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=sample_class.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)
    return enrollment


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
    csrf_token = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}"
    }


@pytest.fixture
def auth_headers_manager(manager_token):
    """
    Get authentication headers for manager
    """
    csrf_token = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {manager_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}"
    }


@pytest.fixture
def auth_headers_supervisor(supervisor_token):
    """
    Get authentication headers for supervisor
    """
    csrf_token = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {supervisor_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}"
    }


@pytest.fixture
def auth_headers_parent(parent_token):
    """
    Get authentication headers for parent
    """
    csrf_token = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {parent_token}",
        "X-CSRF-Token": csrf_token,
        "Cookie": f"kinjo_csrf_token={csrf_token}"
    }


@pytest.fixture
def sample_enrollment(test_db, sample_child, sample_kindergarten, sample_class):
    from models import EnrollmentApplication, EnrollmentStatus
    enrollment = EnrollmentApplication(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=sample_class.id,
        status=EnrollmentStatus.ACTIVE,
        source="WEB",
        created_at=datetime(2026, 1, 10),
        submitted_at=datetime(2026, 1, 10),
        enrollment_start_date=date(2026, 1, 15),
    )
    test_db.add(enrollment)
    test_db.commit()
    test_db.refresh(enrollment)
    return enrollment


@pytest.fixture
def sample_incident(test_db, sample_child, sample_kindergarten, supervisor_user, sample_enrollment):
    from models import Incident, IncidentType, SeverityLevel
    incident = Incident(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        supervisor_id=supervisor_user.id,
        type=IncidentType.ILLNESS,
        severity_level=SeverityLevel.LOW,
        description="تعثّر الطفل في الملعب",
        occurred_at=datetime(2026, 5, 2, 10, 30),
        reported_by=supervisor_user.id,
        parent_informed=True,
        followup_required_flag=False,
    )
    test_db.add(incident)
    test_db.commit()
    test_db.refresh(incident)
    return incident


@pytest.fixture
def sample_daily_report(test_db, sample_child, supervisor_user, sample_enrollment, sample_kindergarten):
    from models import DailyReport, DailyReportStatus
    report = DailyReport(
        child_id=sample_child.id,
        date=date(2026, 5, 1),
        status=DailyReportStatus.SUBMITTED,
        submitted_by=supervisor_user.id,
        submitted_at=datetime(2026, 5, 1, 14, 0),
        arrival_time="08:00",
        leave_time="14:00",
        breakfast=True,
        snack=True,
        milk=True,
        lunch=False,
        kindergarten_id=sample_kindergarten.id,
    )
    test_db.add(report)
    test_db.commit()
    test_db.refresh(report)
    return report


@pytest.fixture
def sample_attendance(test_db, sample_child, sample_class, supervisor_user, sample_enrollment):
    from models import AttendanceLog, AttendanceStatus
    from datetime import datetime, timezone
    log = AttendanceLog(
        child_id=sample_child.id,
        class_id=sample_class.id,
        date=date(2026, 5, 1),
        status=AttendanceStatus.PRESENT,
        check_in_at=datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc),
        recorded_by=supervisor_user.id,
    )
    test_db.add(log)
    test_db.commit()
    test_db.refresh(log)
    return log


@pytest.fixture
def sample_supervisor_assignment(test_db, supervisor_user, sample_class):
    from models import SupervisorAssignment
    assignment = SupervisorAssignment(
        class_id=sample_class.id,
        supervisor_id=supervisor_user.id,
        is_primary=True,
        start_date=date(2026, 1, 1),
    )
    test_db.add(assignment)
    test_db.commit()
    test_db.refresh(assignment)
    return assignment
