"""
Tests for admin governance endpoints.

Verifies:
- Governance endpoints require admin auth (401/403)
- Admin can access KPIs, leaderboard, and reminders
- Reminder POST requires a valid kindergarten
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from auth import get_password_hash
from governance_kpi_service import _JORDAN_TZ
import models
from conftest import csrf_pair



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
            headers={"Authorization": f"Bearer {token}", **csrf_pair()},
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
            headers={"Authorization": f"Bearer {token}", **csrf_pair()},
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
        # Records are written in Jordan-local time (governance_kpi_service) and the
        # endpoint counts "today" against Jordan-local midnight. Seeding in UTC made
        # this test fail between 00:00 and 03:00 local, when the two frames' dates
        # differ on SQLite's naive wall-clock storage.
        now = datetime.now(_JORDAN_TZ)
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


class TestGovernanceAggregatesInSQL:
    """The governance page took 8-13s in production because three queries
    selected raw rows and reduced them in Python. daily_reports.created_at
    records when the row was written rather than when the report was filed,
    so the "last 30 days" / "last 7 days" cutoffs matched all 378k rows and
    shipped every one of them to the app on each page load -- against a
    ~250ms database scan. These assert the reductions stay in SQL."""

    def test_submission_timing_buckets_hours_in_the_database(self):
        """Must GROUP BY hour rather than materialise every created_at."""
        import inspect
        from governance_quality_service import GovernanceQualityService

        src = inspect.getsource(GovernanceQualityService.submission_timing_distribution)
        assert 'func.extract("hour"' in src, (
            "hour bucketing must happen in SQL"
        )
        assert ".group_by(" in src
        assert "db.query(DailyReport.created_at)" not in src, (
            "selecting every created_at is the regression this guards against"
        )

    def test_leaderboard_enrichment_aggregates_per_kindergarten(self):
        """Morning rate and average approval hours must both reduce in SQL."""
        import inspect
        import admin_endpoints

        src = inspect.getsource(admin_endpoints.get_governance_leaderboard)
        # morning rate: one row per kindergarten, not one row per report
        assert 'func.extract("hour"' in src
        assert "db.query(models.DailyReport.kindergarten_id, models.DailyReport.created_at)" not in src, (
            "pulling (kindergarten_id, created_at) for every report is the regression"
        )
        # avg approval: SQL on PostgreSQL, Python fallback elsewhere
        assert 'dialect.name == "postgresql"' in src
        assert 'func.extract(\n                    "epoch",' in src or 'func.extract("epoch"' in src

    def test_submission_timing_matches_a_python_reduction(self, test_db, sample_daily_report):
        """Same numbers as counting hours in Python, on real rows."""
        from collections import Counter
        from governance_quality_service import GovernanceQualityService

        result = GovernanceQualityService().submission_timing_distribution(test_db)

        rows = test_db.query(models.DailyReport.created_at).filter(
            models.DailyReport.created_at
            >= (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7))
        ).all()
        expected = Counter()
        for (created_at,) in rows:
            if created_at:
                expected[created_at.hour] += 1

        assert len(rows) > 0, "fixture must supply rows or this proves nothing"
        assert result["total_reports"] == len(rows)
        assert result["hour_distribution"] == {
            str(h): c for h, c in sorted(expected.items())
        }


class TestGovernanceEndpointsRunInThreadpool:
    """The governance page fires five API calls at once. They were all
    `async def` doing blocking sync-SQLAlchemy work with no `await` anywhere,
    so Starlette ran them straight on the event loop and each one stalled the
    others: /trend answered in 0.22s alone but reported 3.03s inside the
    batch. As plain `def`, FastAPI runs them in its threadpool and they
    overlap.

    An `await` appearing in one of these is the thing that breaks the
    property -- it forces `async def` back, and the blocking DB work returns
    to the event loop."""

    GOVERNANCE_HANDLERS = [
        "get_governance_kpis",
        "get_governance_leaderboard",
        "get_governance_trend",
        "get_governance_safeguarding",
        "send_governance_reminder_endpoint",
        "list_governance_reminders",
        "get_governance_reminder_stats",
    ]

    def test_handlers_are_not_coroutine_functions(self):
        import inspect
        import admin_endpoints

        for name in self.GOVERNANCE_HANDLERS:
            fn = getattr(admin_endpoints, name)
            assert not inspect.iscoroutinefunction(fn), (
                f"{name} is a coroutine function; FastAPI will run it on the "
                "event loop, where its blocking DB work stalls every other "
                "request in the process"
            )

    def test_handlers_contain_no_await(self):
        """The conversion is only valid while these bodies stay await-free."""
        import ast
        import inspect
        import admin_endpoints

        src = inspect.getsource(admin_endpoints)
        tree = ast.parse(src)
        by_name = {
            n.name: n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in self.GOVERNANCE_HANDLERS:
            node = by_name[name]
            awaits = [
                n for n in ast.walk(node)
                if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))
            ]
            assert not awaits, (
                f"{name} now awaits; it must become `async def` again, and its "
                "blocking DB work must then move off the event loop"
            )
