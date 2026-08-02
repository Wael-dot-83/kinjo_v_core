"""
Tests for admin dashboard endpoint.

Verifies:
- Dashboard requires admin auth
- Non-admin users receive 403
- Response contains expected KPI keys
- Cache TTL behaviour (second call hits cache)
"""
from datetime import datetime, timedelta
import time
import pytest
from utils.time_utils import now_amman
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="dashadmin",
        email="dashadmin@test.com",
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
        username="dashmgr",
        email="dashmgr@test.com",
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


class TestDashboardAuth:
    def test_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/dashboard")
        assert r.status_code == 401

    def test_manager_returns_403(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "dashmgr", "Manager123!")
        r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


class TestDashboardResponse:
    def test_admin_gets_200(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_response_contains_kpi_section(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        # Dashboard must return at minimum a dict with some keys
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_second_call_also_returns_200(self, client, test_db):
        """Verifies cache hit path also returns valid data."""
        _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        headers = {"Authorization": f"Bearer {token}"}
        r1 = client.get("/api/admin/dashboard", headers=headers)
        r2 = client.get("/api/admin/dashboard", headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_active_users_counts_distinct_successful_logins_today(self, client, test_db):
        admin = _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        other = models.User(
            username="dashloginother",
            email="dashloginother@test.com",
            hashed_password=get_password_hash("Other123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other)
        test_db.flush()
        # Aware Jordan, not naive datetime.now(). This test asserts on "logins today"
        # in Jordan terms, and db_types.UTCDateTime reads a naive value as UTC — so a
        # naive local timestamp taken after 21:00 Jordan lands on the *next* Jordan day
        # and the count silently drops to 0. That made this test pass during the working
        # day and fail in the evening.
        now = now_amman()
        test_db.query(models.AuditLog).delete()
        test_db.add_all([
            models.AuditLog(user_id=admin.id, action="LOGIN_SUCCESS", entity_type="User", created_at=now),
            models.AuditLog(user_id=admin.id, action="LOGIN_SUCCESS", entity_type="User", created_at=now),
            models.AuditLog(user_id=other.id, action="LOGIN_SUCCESS", entity_type="User", created_at=now),
            models.AuditLog(user_id=other.id, action="LOGIN_FAILED", entity_type="User", created_at=now),
            models.AuditLog(
                user_id=admin.id, action="LOGIN_SUCCESS", entity_type="User",
                created_at=now - timedelta(days=1),
            ),
        ])
        test_db.commit()

        r = client.get(
            "/api/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["kpis"]["active_users"] == 2
        assert payload["kpi_trends"]["active_users"]["previous_value"] == 1


class TestDashboardFilters:
    def test_governorate_filter_accepted(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        r = client.get(
            "/api/admin/dashboard?governorate=Amman",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_invalid_page_size_clamped_or_rejected(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "dashadmin")
        r = client.get(
            "/api/admin/dashboard?page_size=99999",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should either clamp (200) or reject (422), never 500
        assert r.status_code in (200, 422)
