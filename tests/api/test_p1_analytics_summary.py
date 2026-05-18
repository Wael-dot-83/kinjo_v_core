from datetime import date, timedelta

import pytest

from dependencies import get_current_user
from main import app

pytestmark = [pytest.mark.integration, pytest.mark.p1]


@pytest.fixture
def auth_user():
    def _set(user):
        app.dependency_overrides[get_current_user] = lambda: user

    yield _set
    app.dependency_overrides.clear()


def _date_params():
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
    }


def test_analytics_metadata(client):
    response = client.get("/api/analytics/metadata?lang=en")
    assert response.status_code == 200
    data = response.json()
    assert "dimensions" in data
    assert "metrics" in data
    assert "time_grains" in data


def test_analytics_network_summary_manager(client, manager_user, auth_user):
    auth_user(manager_user)
    response = client.get("/api/analytics/network-summary", params=_date_params())
    assert response.status_code == 200
    data = response.json()
    assert "total_kindergartens" in data
    assert "attendance_rate" in data


def test_analytics_governorate_breakdown_manager(client, manager_user, auth_user):
    auth_user(manager_user)
    response = client.get("/api/analytics/governorate-breakdown", params=_date_params())
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_analytics_enrollments_summary_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/enrollments/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data


def test_analytics_attendance_summary_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/attendance/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data


def test_analytics_daily_reports_summary_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/daily-reports/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data


def test_analytics_safety_summary_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/safety/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data


def test_analytics_staffing_summary_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/staffing/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data
