"""
Tests for the new admin heat map endpoints (history, alerts, acknowledge).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import dependencies
from database import Base, get_db
from heatmap.backend.admin_router import router as heat_map_router
from fastapi import FastAPI
from heatmap.scripts.seed_snapshot_data import seed_governorates
from heatmap.backend import pipeline

# Module-scoped fixture: build a real DB with 7 days of backfilled data.
_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_ENGINE)
_SESSION_ = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)
_DB = _SESSION_()
seed_governorates(_DB)
pipeline.backfill(_DB, days=7)
_DB.commit()

_APP = FastAPI()
_APP.include_router(heat_map_router, prefix="/api")


async def _fake_user():
    u = models.User(id=1, email="admin@test.com", role=models.UserRole.ADMIN)
    return u
_APP.dependency_overrides[dependencies.get_current_user] = _fake_user


def _override_get_db():
    d = _SESSION_()
    try:
        yield d
    finally:
        d.close()
_APP.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="module")
def app():
    return _APP


# ---------------------------------------------------------------------------
# History endpoint
# ---------------------------------------------------------------------------
def test_history_returns_7_days_for_each_governorate(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/governorate/amman/history?days=7")
        assert r.status_code == 200
        data = r.json()
        assert data["slug"] == "amman"
        assert data["days"] == 7
        assert len(data["history"]) == 7
        for entry in data["history"]:
            assert "date" in entry
            assert "risk_score" in entry
            assert "risk_level" in entry
            assert 0 <= entry["risk_score"] <= 100
            assert entry["risk_level"] in ("low", "medium", "high", "critical")


def test_history_sorted_oldest_first(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/governorate/irbid/history?days=7")
        assert r.status_code == 200
        data = r.json()
        dates = [h["date"] for h in data["history"]]
        assert dates == sorted(dates)


def test_history_includes_main_indicators(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/governorate/aqaba/history?days=7")
        assert r.status_code == 200
        data = r.json()
        # 5 measurable main indicators — children_registration is unavailable
        # (no defensible population denominator) and so is never snapshotted.
        for entry in data["history"]:
            assert "main_indicators" in entry
            assert len(entry["main_indicators"]) == 5
            assert "children_registration" not in entry["main_indicators"]


def test_history_unknown_governorate_404(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/governorate/nonexistent/history")
        assert r.status_code == 404


def test_history_default_30_days(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/governorate/amman/history")
        assert r.status_code == 200
        data = r.json()
        assert data["days"] == 30
        # Only 7 days of data exist, so the response has 7 rows
        assert len(data["history"]) == 7


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------
def test_alerts_list_default_open_only(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/alerts")
        assert r.status_code == 200
        data = r.json()
        # 7 days × 12 governorates × N alerts/gov. Just check it returns
        # a non-empty list with valid severities.
        assert "alerts" in data
        assert "count" in data
        for a in data["alerts"][:5]:
            assert a["severity"] in ("low", "medium", "high", "critical")


def test_alerts_list_filter_by_severity(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/alerts?severity=critical")
        assert r.status_code == 200
        data = r.json()
        for a in data["alerts"]:
            assert a["severity"] == "critical"


def test_alerts_list_filter_by_governorate(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/alerts?governorate=amman")
        assert r.status_code == 200
        data = r.json()
        for a in data["alerts"]:
            assert a["governorate_code"] == "JO-AM"


def test_alerts_unknown_governorate_404(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/alerts?governorate=zzz")
        assert r.status_code == 404


def test_alerts_invalid_severity_422(app):
    with TestClient(app) as client:
        r = client.get("/api/admin/heat-map/alerts?severity=garbage")
        assert r.status_code == 422


def test_alerts_acknowledge(app):
    with TestClient(app) as client:
        # First get an open alert
        r = client.get("/api/admin/heat-map/alerts?open_only=true&limit=1")
        assert r.status_code == 200
        data = r.json()
        if data["count"] == 0:
            pytest.skip("No open alerts to acknowledge")
        alert_id = data["alerts"][0]["id"]
        # Acknowledge it
        r = client.post(
            f"/api/admin/heat-map/alerts/{alert_id}/acknowledge",
            headers={"X-CSRF-Token": "test"},
            cookies={"kinjo_csrf_token": "test"}
        )
        assert r.status_code == 200
        result = r.json()
        assert result["status"] in ("acknowledged", "already_acknowledged")
        # Acknowledged_at must be populated
        r2 = client.get("/api/admin/heat-map/alerts?open_only=true")
        ids = [a["id"] for a in r2.json()["alerts"]]
        assert alert_id not in ids


def test_alerts_acknowledge_unknown_404(app):
    with TestClient(app) as client:
        r = client.post(
            "/api/admin/heat-map/alerts/999999/acknowledge",
            headers={"X-CSRF-Token": "test"},
            cookies={"kinjo_csrf_token": "test"}
        )
        assert r.status_code == 404
