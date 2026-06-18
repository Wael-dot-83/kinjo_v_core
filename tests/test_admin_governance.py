"""
Tests for admin governance endpoints.

Verifies:
- Governance endpoints require admin auth (401/403)
- Admin can access KPIs, leaderboard, and reminders
- Reminder POST requires a valid kindergarten
"""
import pytest
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="govadmin",
        email="govadmin@test.com",
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
        username="govmgr",
        email="govmgr@test.com",
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


class TestGovernanceAuth:
    def test_kpis_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/governance/kpis")
        assert r.status_code == 401

    def test_leaderboard_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/governance/leaderboard")
        assert r.status_code == 401

    def test_reminders_unauthenticated_returns_401(self, client, test_db):
        r = client.get("/api/admin/governance/reminders")
        assert r.status_code == 401

    def test_manager_cannot_access_kpis(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "govmgr", "Manager123!")
        r = client.get("/api/admin/governance/kpis", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


class TestGovernanceKPIs:
    def test_admin_gets_kpis(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/kpis?start_date=2026-01-01&end_date=2026-06-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_admin_gets_leaderboard(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/leaderboard?start_date=2026-01-01&end_date=2026-06-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_kpis_missing_dates_returns_422(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/kpis",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422


class TestGovernanceReminders:
    def test_admin_can_list_reminders(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_send_reminder_to_nonexistent_kg_returns_error(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.post(
            "/api/admin/governance/reminders",
            json={"kindergarten_id": 999999, "reminder_type": "EMAIL"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code in (400, 404, 422, 429)

    def test_admin_gets_reminder_stats(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "sent_today" in data
        assert "total_sent" in data

    def test_reminder_stats_requires_admin(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "govmgr", "Manager123!")
        r = client.get(
            "/api/admin/governance/reminders/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
