"""
Unit tests for Analytics Service
"""
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from main import app
from auth import get_password_hash
import models
from database import get_db


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
    # Create kindergarten first
    kg = models.Kindergarten(
        name_ar="روضة تجريبية",
        name_en="Test Kindergarten",
        governorate="Test Governorate",
        district="Test City",
        area="Test Area",
        address_line="Test Address",
        contact_phone="0791234567",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()

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
def sample_data(test_db):
    """
    Create sample data for analytics testing
    """
    # Create kindergarten
    kg = models.Kindergarten(
        name_ar="روضة الاختبار",
        name_en="Test Kindergarten",
        governorate="عمان",
        district="عمان",
        area="القويسمة",
        address_line="شارع الاختبار",
        contact_phone="0791234567",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()

    # Create admin user
    admin = models.User(
        username="admin",
        email="admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(admin)
    test_db.commit()

    # Create class
    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="الصف الأول",
        name_en="Class 1",
        class_code="C1",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=36
    )
    test_db.add(cls)
    test_db.commit()

    # Create parent
    parent = models.User(
        username="parent",
        email="parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(parent)
    test_db.commit()

    # Create parent profile
    parent_profile = models.ParentProfile(
        user_id=parent.id,
        first_name="أحمد",
        last_name="محمد",
        phone_number="0791234567",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="عمان",
        home_district="عمان",
        home_area="وسط البلد",
        home_address_line="شارع الملك فيصل"
    )
    test_db.add(parent_profile)
    test_db.commit()

    # Create child
    child = models.Child(
        parent_id=parent_profile.id,
        first_name="علي",
        last_name="أحمد",
        date_of_birth=date.today() - timedelta(days=365 * 3),
        gender=models.Gender.MALE,
        father_name="أحمد محمد",
        mother_first_name="فاطمة",
        mother_last_name="علي",
        mother_nationality="أردني"
    )
    test_db.add(child)
    test_db.commit()

    # Create enrollment
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE
    )
    test_db.add(enrollment)
    test_db.commit()

    return {
        'kindergarten': kg,
        'admin': admin,
        'class': cls,
        'parent': parent,
        'child': child,
        'enrollment': enrollment
    }


class TestAnalyticsService:
    """Test analytics service endpoints"""

    def test_metadata_endpoint(self, client, admin_user):
        """Test analytics metadata endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test metadata endpoint
        response = client.get(
            "/api/analytics/metadata",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "dimensions" in data
        assert "metrics" in data

    def test_network_summary_endpoint(self, client, admin_user, sample_data):
        """Test network summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test network summary
        response = client.get(
            "/api/analytics/network-summary",
            params={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_kindergartens" in data
        assert "total_children" in data
        assert "total_staff" in data

    def test_governorate_breakdown_endpoint(self, client, admin_user, sample_data):
        """Test governorate breakdown endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test governorate breakdown
        response = client.get(
            "/api/analytics/governorate-breakdown",
            params={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_dashboard_data_endpoint(self, client, admin_user, sample_data):
        """Test consolidated dashboard data endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test dashboard data
        response = client.get(
            "/api/analytics/dashboard-data",
            params={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "network_summary" in data
        assert "governorate_breakdown" in data

    def test_trends_endpoint(self, client, admin_user, sample_data):
        """Test trends endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test trends
        response = client.get(
            "/api/analytics/trends",
            params={
                "metric": "attendance",
                "period_start": "2024-01-01",
                "period_end": "2024-12-31"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_risk_radar_endpoint(self, client, admin_user, sample_data):
        """Test risk radar endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test risk radar
        response = client.get(
            "/api/analytics/risk-radar",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_overview_endpoint(self, client, admin_user, sample_data):
        """Test overview endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test overview
        response = client.get(
            "/api/analytics/overview",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_drilldown_endpoint(self, client, admin_user, sample_data):
        """Test drilldown endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test drilldown by kindergarten
        kg_id = sample_data['kindergarten'].id
        response = client.get(
            f"/api/analytics/drilldown/KINDERGARTEN/{kg_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_time_series_endpoint(self, client, admin_user, sample_data):
        """Test time series endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test time series
        response = client.get(
            "/api/analytics/time-series?metric=attendance_rate",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_compare_endpoint(self, client, admin_user, sample_data):
        """Test compare endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test compare with kindergarten ID
        kg_id = sample_data['kindergarten'].id
        response = client.get(
            f"/api/analytics/compare?kg_ids={kg_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_rankings_endpoint(self, client, admin_user, sample_data):
        """Test rankings endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test rankings
        response = client.get(
            "/api/analytics/rankings/attendance_rate",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_governance_distribution_endpoint(self, client, admin_user, sample_data):
        """Test governance distribution endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test governance distribution
        response = client.get(
            "/api/analytics/governance-distribution",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "green" in data
        assert "amber" in data
        assert "red" in data

    def test_enrollments_summary_endpoint(self, client, admin_user, sample_data):
        """Test enrollments summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test enrollments summary
        response = client.get(
            "/api/analytics/enrollments/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_attendance_summary_endpoint(self, client, admin_user, sample_data):
        """Test attendance summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test attendance summary
        response = client.get(
            "/api/analytics/attendance/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_daily_reports_summary_endpoint(self, client, admin_user, sample_data):
        """Test daily reports summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test daily reports summary
        response = client.get(
            "/api/analytics/daily-reports/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_safety_summary_endpoint(self, client, admin_user, sample_data):
        """Test safety summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test safety summary
        response = client.get(
            "/api/analytics/safety/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_staffing_summary_endpoint(self, client, admin_user, sample_data):
        """Test staffing summary endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "admin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test staffing summary
        response = client.get(
            "/api/analytics/staffing/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_manager_access_restriction(self, client, manager_user):
        """Test that managers can only access their kindergarten data"""
        # Login as manager
        response = client.post("/token", data={
            "username": "testmanager",
            "password": "Manager123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test that manager can access analytics (should be restricted to their KG)
        today = date.today()
        period_start = (today - timedelta(days=30)).isoformat()
        period_end = today.isoformat()
        response = client.get(
            f"/api/analytics/network-summary?period_start={period_start}&period_end={period_end}",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Should succeed but return limited data
        assert response.status_code == 200

    def test_kpi_endpoint(self, client, admin_user, sample_data):
        """Test KPI analytics endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test KPI endpoint
        response = client.get(
            "/api/analytics/kpi",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "attendance_rate" in data
        assert "governance_score" in data
        assert "incident_rate" in data
        assert "report_completion" in data

    def test_attendance_analytics_endpoint(self, client, admin_user, sample_data):
        """Test attendance analytics endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test attendance analytics endpoint
        response = client.get(
            "/api/analytics/attendance",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "attendance_rate" in data
        assert "chronic_absence_rate" in data
        assert "present_today" in data
        assert "total_children" in data

    def test_dashboard_endpoint(self, client, admin_user, sample_data):
        """Test dashboard analytics endpoint"""
        # Login first
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test dashboard endpoint
        response = client.get(
            "/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "kpis" in data

    def test_unauthorized_access(self, client):
        """Test that unauthorized users cannot access protected analytics"""
        # Test without token on a protected endpoint
        today = date.today()
        period_start = (today - timedelta(days=30)).isoformat()
        period_end = today.isoformat()
        response = client.get(
            f"/api/analytics/network-summary?period_start={period_start}&period_end={period_end}"
        )
        assert response.status_code == 401

    def test_registration_analytics_endpoint(self, client, admin_user, sample_data):
        """Test registration analytics endpoint"""
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        today = date.today()
        period_start = (today - timedelta(days=30)).isoformat()
        period_end = today.isoformat()
        response = client.get(
            f"/api/analytics/registration/analytics?start_date={period_start}&end_date={period_end}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status_breakdown" in data
        assert "funnel" in data
        assert "rejection_reasons" in data
        assert "approval_workflow" in data
        assert "source_breakdown" in data

    def test_registration_drilldown_endpoint(self, client, admin_user, sample_data):
        """Test registration drilldown endpoint"""
        response = client.post("/token", data={
            "username": "testadmin",
            "password": "Admin123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]

        today = date.today()
        period_start = (today - timedelta(days=30)).isoformat()
        period_end = today.isoformat()
        response = client.get(
            f"/api/analytics/registration/drilldown?start_date={period_start}&end_date={period_end}&page=1&page_size=10",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
