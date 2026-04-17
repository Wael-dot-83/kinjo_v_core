import pytest

from dependencies import get_current_user
from main import app

pytestmark = [pytest.mark.integration, pytest.mark.p0]


@pytest.fixture
def auth_user():
    def _set(user):
        app.dependency_overrides[get_current_user] = lambda: user

    yield _set
    app.dependency_overrides.clear()


def test_analytics_kpi_manager(client, manager_user, auth_user):
    auth_user(manager_user)
    response = client.get("/api/analytics/kpi")
    assert response.status_code == 200
    data = response.json()
    assert "attendance_rate" in data
    assert "governance_score" in data
    assert "incident_rate" in data
    assert "report_completion" in data


def test_analytics_attendance_admin(client, admin_user, auth_user):
    auth_user(admin_user)
    response = client.get("/api/analytics/attendance")
    assert response.status_code == 200
    data = response.json()
    assert "attendance_rate" in data
    assert "present_today" in data
    assert "total_children" in data


def test_analytics_dashboard_manager(client, manager_user, auth_user):
    auth_user(manager_user)
    response = client.get("/api/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "kpis" in data


def test_kpi_summary_manager(client, manager_user, auth_user):
    auth_user(manager_user)
    response = client.get("/api/kpi/summary")
    assert response.status_code == 200
    data = response.json()
    assert "attendance_rate" in data
    assert "incident_rate" in data
    assert "ratio_compliance" in data
    assert "gqi_score" in data


def test_kpi_summary_forbidden_for_parent(client, parent_user, auth_user):
    auth_user(parent_user)
    response = client.get("/api/kpi/summary")
    assert response.status_code == 403
