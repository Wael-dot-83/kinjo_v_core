"""
Tests for admin governance endpoints.

Verifies:
- Governance endpoints require admin auth (401/403)
- Admin can access KPIs, leaderboard, and reminders
- Reminder POST requires a valid kindergarten
"""
from datetime import datetime, timedelta, timezone

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
            json={
                "target_type": "kindergarten",
                "target_id": 999999,
                "reminder_type": "low_submission_rate",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_send_reminder_rejects_non_supervisor_user(self, client, test_db):
        admin = _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.post(
            "/api/admin/governance/reminders",
            json={
                "target_type": "supervisor",
                "target_id": admin.id,
                "reminder_type": "low_submission_rate",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_admin_gets_reminder_stats(self, client, test_db):
        _create_admin(test_db)
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert set(data) == {"sent_today", "total_sent"}
        assert data == {"sent_today": 0, "total_sent": 0}

    def test_reminder_stats_count_today_without_fabricated_fields(self, client, test_db):
        admin = _create_admin(test_db)
        now = datetime.now(timezone.utc)
        test_db.add_all([
            models.GovernanceReminder(
                target_type="supervisor", target_id=admin.id,
                reminder_type="test_today", sent_by=admin.id, sent_at=now,
                cooldown_expires_at=now + timedelta(hours=1),
            ),
            models.GovernanceReminder(
                target_type="supervisor", target_id=admin.id,
                reminder_type="test_yesterday", sent_by=admin.id,
                sent_at=now - timedelta(days=1),
                cooldown_expires_at=now,
            ),
        ])
        test_db.commit()
        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == {"sent_today": 1, "total_sent": 2}

    def test_reminder_list_resolves_kindergarten_governorate(self, client, test_db, sample_kindergarten):
        """The dedicated /admin/governance/reminders page's "Governorate"
        column was permanently rendered as a literal "-" placeholder --
        the list endpoint never returned a governorate field at all, even
        though it's trivially resolvable from target_id for
        target_type="kindergarten" reminders."""
        admin = _create_admin(test_db)
        db_reminder = models.GovernanceReminder(
            target_type="kindergarten",
            target_id=sample_kindergarten.id,
            reminder_type="low_submission_rate",
            sent_by=admin.id,
            cooldown_expires_at=datetime.now(timezone.utc),
        )
        test_db.add(db_reminder)
        test_db.commit()

        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["governorate"] == "Amman"

    def test_reminder_list_resolves_supervisor_governorate_via_their_kindergarten(
        self, client, test_db, sample_kindergarten
    ):
        """Supervisor-targeted reminders should resolve governorate via the
        supervisor's own assigned kindergarten, not just kindergarten-
        targeted reminders."""
        admin = _create_admin(test_db)
        supervisor = models.User(
            username="gov_sup_reminder_test",
            email="gov_sup_reminder_test@test.com",
            hashed_password=get_password_hash("Supervisor123!"),
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=sample_kindergarten.id,
        )
        test_db.add(supervisor)
        test_db.commit()
        test_db.refresh(supervisor)

        db_reminder = models.GovernanceReminder(
            target_type="supervisor",
            target_id=supervisor.id,
            reminder_type="low_submission_rate",
            sent_by=admin.id,
            cooldown_expires_at=datetime.now(timezone.utc),
        )
        test_db.add(db_reminder)
        test_db.commit()

        token = _get_token(client, "govadmin")
        r = client.get(
            "/api/admin/governance/reminders",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["governorate"] == "Amman"

    def test_reminder_stats_requires_admin(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "govmgr", "Manager123!")
        r = client.get(
            "/api/admin/governance/reminders/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
