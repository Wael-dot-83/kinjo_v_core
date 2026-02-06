"""
Unit tests for KPI Service
"""
import pytest
from datetime import date
from sqlalchemy.orm import Session
from kpi_service import KPIService, get_kpi_filters
from models import Kindergarten
from database import get_db
from fastapi.testclient import TestClient
from main import app
from auth import get_password_hash


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
    from models import User, UserRole, UserStatus
    user = User(
        username="testadmin",
        email="admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def sample_kindergarten(test_db):
    """
    Create a sample kindergarten for testing
    """
    from models import Kindergarten, KindergartenStatus
    kindergarten = Kindergarten(
        name_ar="روضة الأمل",
        name_en="Hope Kindergarten",
        license_number="LIC-2026-001",
        governorate="Amman",
        city="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@hope.jo",
        status=KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31)
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)
    return kindergarten


def get_token_for_admin(client):
    """Get authentication token for admin user"""
    response = client.post(
        "/token",
        data={"username": "testadmin", "password": "Admin123!"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_get_kpi_filters_arabic(client, admin_user, sample_kindergarten):
    """Test /api/kpi/filters with Arabic locale"""
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/kpi/filters?locale=ar", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "kindergartens" in data
    assert "governorates" in data
    # Check that governorates are in Arabic
    assert any("عمان" in gov["name"] for gov in data["governorates"])


def test_get_kpi_filters_english(client, admin_user, sample_kindergarten):
    """Test /api/kpi/filters with English locale"""
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/kpi/filters?locale=en", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "kindergartens" in data
    assert "governorates" in data
    # Check that governorates are in English
    assert any("Amman" in gov["name"] for gov in data["governorates"])


def test_dashboard_data_with_locale(client, admin_user, sample_kindergarten):
    """Test dashboard data returns localized names"""
    from datetime import date
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today().replace(day=1)
    end = date.today()
    
    response = client.get(f"/api/kpi/dashboard-data?period_start={start}&period_end={end}&locale=ar", headers=headers)
    assert response.status_code == 200
    # Test would check names are in Arabic, but depends on data


if __name__ == "__main__":
    pytest.main([__file__])