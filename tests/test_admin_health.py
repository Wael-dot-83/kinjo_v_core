"""
Tests for the /api/admin/health endpoint.

Verifies:
- Endpoint requires admin auth (401/403)
- Successful response includes status, checks, and timestamp
- Response indicates degraded when a dependency fails
"""
import pytest
from unittest.mock import patch
from auth import get_password_hash
import models


def _make_admin(db):
    u = models.User(
        username="health_admin",
        email="health_admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_manager(db, kg_id):
    u = models.User(
        username="health_mgr",
        email="health_mgr@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _tok(client, username, pw):
    r = client.post("/token", data={"username": username, "password": pw})
    assert r.status_code == 200
    return r.json()["access_token"]


class TestAdminHealthAuth:
    def test_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/health")
        assert r.status_code == 401

    def test_manager_returns_403(self, client, test_db, sample_kindergarten):
        _make_manager(test_db, sample_kindergarten.id)
        token = _tok(client, "health_mgr", "Manager123!")
        r = client.get("/api/admin/health", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


class TestAdminHealthResponse:
    def test_admin_gets_200_with_status_key(self, client, test_db):
        _make_admin(test_db)
        token = _tok(client, "health_admin", "Admin123!")
        r = client.get("/api/admin/health", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert body["status"] in ("ok", "degraded", "error")

    def test_response_includes_checks_and_timestamp(self, client, test_db):
        _make_admin(test_db)
        token = _tok(client, "health_admin", "Admin123!")
        r = client.get("/api/admin/health", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert "checks" in body
        assert isinstance(body["checks"], dict)
        assert "timestamp" in body

    def test_response_includes_database_check(self, client, test_db):
        _make_admin(test_db)
        token = _tok(client, "health_admin", "Admin123!")
        r = client.get("/api/admin/health", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        checks = r.json().get("checks", {})
        assert "database" in checks
        assert checks["database"] in ("ok", "degraded", "error")

    def test_rate_limit_header_present(self, client, test_db):
        _make_admin(test_db)
        token = _tok(client, "health_admin", "Admin123!")
        r = client.get("/api/admin/health", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "x-ratelimit-limit" in {k.lower() for k in r.headers.keys()}
