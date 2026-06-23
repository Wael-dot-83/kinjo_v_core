"""
Tests for admin kindergarten overview endpoint.
"""
import pytest
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="kgadmin",
        email="kgadmin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_manager(db, kg_id):
    user = models.User(
        username="kgmgr",
        email="kgmgr@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_token(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


class TestKgOverviewAuth:
    def test_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/kg-overview")
        assert r.status_code == 401

    def test_manager_returns_403(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "kgmgr", "Manager123!")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


class TestKgOverviewResponse:
    def test_admin_gets_200(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_response_contains_expected_keys(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        for key in ["generated_at", "kpis", "kindergartens", "charts", "alerts", "executive_health", "filters"]:
            assert key in data, f"Missing key {key}"

    def test_kpis_has_four_cards(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["kpis"]) >= 4

    def test_kindergartens_is_list(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["kindergartens"], list)

    def test_charts_keys_present(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get("/api/admin/kg-overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        charts = data.get("charts", {})
        for key in ["attendance_by_kg", "occupancy_pressure", "alerts_by_severity", "alerts_by_type", "governorate_comparison"]:
            assert key in charts, f"Missing chart {key}"

    def test_filter_by_governorate(self, client, test_db, sample_kindergarten):
        _create_admin(test_db)
        token = _get_token(client, "kgadmin")
        r = client.get(
            "/api/admin/kg-overview",
            headers={"Authorization": f"Bearer {token}"},
            params={"governorate": sample_kindergarten.governorate},
        )
        assert r.status_code == 200
        data = r.json()
        for kg in data["kindergartens"]:
            assert kg["governorate"] == sample_kindergarten.governorate
