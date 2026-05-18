"""
Integration tests for analytics/KPI endpoints: overview, drilldown, time-series, compare, rankings, summary, export
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from datetime import date, timedelta

def get_token_for_admin(client):
    # Placeholder: must be replaced with admin creation logic if available
    return "invalidtoken"  # Will trigger 401/403 for RBAC tests

@pytest.fixture
def client():
    return TestClient(app)

def test_overview_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/analytics/overview", headers=headers)
    assert response.status_code in (401, 403)

def test_drilldown_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/analytics/drilldown/GOVERNORATE/Amman", headers=headers)
    assert response.status_code in (401, 403)

def test_time_series_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/analytics/time-series", params={
        "metric": "attendance_rate",
        "dimension_type": "NETWORK",
        "granularity": "monthly"
    }, headers=headers)
    assert response.status_code in (401, 403)

def test_compare_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/analytics/compare", params={
        "kg_ids": "1,2"
    }, headers=headers)
    assert response.status_code in (401, 403)

def test_rankings_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/analytics/rankings/attendance_rate", headers=headers)
    assert response.status_code in (401, 403)

def test_export_requires_admin(client):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/analytics/export", json={
        "export_format": "CSV",
        "report_type": "attendance",
        "filters": {}
    }, headers=headers)
    assert response.status_code in (401, 403)
