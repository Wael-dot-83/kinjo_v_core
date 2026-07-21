"""
RBAC tests for analytics endpoints.
All analytics endpoints are Admin-only; Manager, Supervisor, and Parent must get 403.
"""
import pytest
from datetime import date

ANALYTICS_ENDPOINTS = [
    "/api/analytics/overview",
    "/api/analytics/attendance/summary",
    "/api/analytics/attendance/by-governorate",
    "/api/analytics/daily-reports/summary",
    "/api/analytics/safety/summary",
    "/api/analytics/staffing/summary",
    "/api/analytics/enrollments/summary",
]

ANALYTICS_ENDPOINTS_WITH_REQUIRED_PARAMS = [
    "/api/analytics/attendance/by-class?kindergarten_id=1",
    "/api/analytics/attendance/chronic-absence",
    "/api/analytics/daily-reports/supervisor-performance",
    "/api/analytics/enrollment/trends?granularity=weekly",
]

KPI_ADMIN_ENDPOINTS = [
    "/api/kpi/network-summary",
]


class TestAnalyticsAdminOnly:
    def test_admin_can_access_overview(self, client, auth_headers_admin):
        resp = client.get("/api/analytics/overview", headers=auth_headers_admin)
        assert resp.status_code == 200

    @pytest.mark.parametrize("url", ANALYTICS_ENDPOINTS)
    def test_manager_blocked_from_analytics(self, client, auth_headers_manager, url):
        resp = client.get(url, headers=auth_headers_manager)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", ANALYTICS_ENDPOINTS)
    def test_supervisor_blocked_from_analytics(self, client, auth_headers_supervisor, url):
        resp = client.get(url, headers=auth_headers_supervisor)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", ANALYTICS_ENDPOINTS)
    def test_parent_blocked_from_analytics(self, client, auth_headers_parent, url):
        resp = client.get(url, headers=auth_headers_parent)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", ANALYTICS_ENDPOINTS_WITH_REQUIRED_PARAMS)
    def test_manager_blocked_from_new_endpoints(self, client, auth_headers_manager, url):
        resp = client.get(url, headers=auth_headers_manager)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", ANALYTICS_ENDPOINTS_WITH_REQUIRED_PARAMS)
    def test_supervisor_blocked_from_new_endpoints(self, client, auth_headers_supervisor, url):
        resp = client.get(url, headers=auth_headers_supervisor)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", KPI_ADMIN_ENDPOINTS)
    def test_manager_blocked_from_kpi_network(self, client, auth_headers_manager, url):
        resp = client.get(url, headers=auth_headers_manager)
        assert resp.status_code == 403

    @pytest.mark.parametrize("url", KPI_ADMIN_ENDPOINTS)
    def test_supervisor_blocked_from_kpi_network(self, client, auth_headers_supervisor, url):
        resp = client.get(url, headers=auth_headers_supervisor)
        assert resp.status_code == 403

    def test_unauthenticated_blocked(self, client):
        resp = client.get("/api/analytics/overview")
        assert resp.status_code in (401, 403)

    def test_time_series_admin_only(self, client, auth_headers_admin, auth_headers_manager):
        admin_resp = client.get(
            "/api/analytics/time-series?metric=attendance_rate",
            headers=auth_headers_admin
        )
        assert admin_resp.status_code == 200

        mgr_resp = client.get(
            "/api/analytics/time-series?metric=attendance_rate",
            headers=auth_headers_manager
        )
        assert mgr_resp.status_code == 403

    def test_rankings_admin_only(self, client, auth_headers_admin, auth_headers_supervisor):
        admin_resp = client.get(
            "/api/analytics/rankings/attendance_rate",
            headers=auth_headers_admin
        )
        assert admin_resp.status_code == 200

        sup_resp = client.get(
            "/api/analytics/rankings/attendance_rate",
            headers=auth_headers_supervisor
        )
        assert sup_resp.status_code == 403

    def test_rankings_rejects_unknown_metric(self, client, auth_headers_admin):
        """An unrecognized metric must 422, not silently return an all-zeros table.

        The handler's `else: value = 0` branch would rank every kindergarten at 0
        and answer with a 200 — the "silent lie" class where the response looks
        valid but answers a different question than asked.
        """
        resp = client.get(
            "/api/analytics/rankings/not_a_real_metric",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 422, resp.text
