"""
Tests for Governance Daily Report KPIs, Leaderboard, and Reminder System.
"""
import pytest
from datetime import date, datetime, timedelta, timezone

import models
from governance_kpi_service import (
    compute_governance_funnel,
    compute_timeliness_metrics,
    compute_quality_metrics,
    compute_consistency_index,
    compute_fair_ranking,
    detect_low_performers,
    check_reminder_cooldown,
    send_governance_reminder,
)
from cache_service import cache_service


@pytest.fixture(autouse=True)
def _clear_governance_cache():
    """Clear in-memory cache between tests to prevent cross-test interference."""
    cache_service.memory_cache.clear()
    yield
    cache_service.memory_cache.clear()


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_attendance(db, child, class_obj, dt):
    """Create an attendance log for a child on a given date."""
    att = models.AttendanceLog(
        child_id=child.id,
        class_id=class_obj.id,
        date=dt,
        status=models.AttendanceStatus.PRESENT,
        check_in_at=datetime.combine(dt, datetime.min.time()).replace(tzinfo=timezone.utc),
        recorded_by=1,
    )
    db.add(att)
    return att


def _make_report(db, child, kg, dt, status, supervisor_id,
                  created_at=None, submitted_at=None, sent_at=None):
    """Create a daily report with specific status."""
    report = models.DailyReport(
        child_id=child.id,
        kindergarten_id=kg.id,
        date=dt,
        status=status,
        submitted_by=supervisor_id,
        created_at=created_at,
        submitted_at=submitted_at,
        sent_to_parent_at=sent_at,
        arrival_time="08:00",
        leave_time="14:00",
    )
    db.add(report)
    return report


# ── Model tests ──────────────────────────────────────────────────────────

class TestGovernanceModels:
    def test_daily_report_view_creation(self, test_db, sample_child, sample_kindergarten, parent_user, supervisor_user, sample_class):
        """DailyReportView can be created and has correct fields."""
        report = _make_report(
            test_db, sample_child, sample_kindergarten, date.today(),
            models.DailyReportStatus.SENT_TO_PARENT, supervisor_user.id,
        )
        test_db.commit()

        view = models.DailyReportView(
            daily_report_id=report.id,
            parent_user_id=parent_user.id,
        )
        test_db.add(view)
        test_db.commit()
        test_db.refresh(view)

        assert view.id is not None
        assert view.daily_report_id == report.id
        assert view.parent_user_id == parent_user.id
        assert view.viewed_at is not None

    def test_daily_report_view_unique(self, test_db, sample_child, sample_kindergarten, parent_user, supervisor_user, sample_class):
        """DailyReportView enforces uniqueness on (report_id, parent_user_id)."""
        report = _make_report(
            test_db, sample_child, sample_kindergarten, date.today(),
            models.DailyReportStatus.SENT_TO_PARENT, supervisor_user.id,
        )
        test_db.commit()

        v1 = models.DailyReportView(daily_report_id=report.id, parent_user_id=parent_user.id)
        test_db.add(v1)
        test_db.commit()

        v2 = models.DailyReportView(daily_report_id=report.id, parent_user_id=parent_user.id)
        test_db.add(v2)
        with pytest.raises(Exception):
            test_db.commit()
        test_db.rollback()

    def test_governance_reminder_creation(self, test_db, admin_user):
        """GovernanceReminder can be created with payload."""
        now = datetime.now(timezone.utc)
        reminder = models.GovernanceReminder(
            target_type="kindergarten",
            target_id=1,
            reminder_type="low_submission_rate",
            sent_by=admin_user.id,
            sent_at=now,
            cooldown_expires_at=now + timedelta(hours=48),
            payload={"submission_rate": 0.3},
        )
        test_db.add(reminder)
        test_db.commit()
        test_db.refresh(reminder)

        assert reminder.id is not None
        assert reminder.payload["submission_rate"] == 0.3


# ── Service tests ────────────────────────────────────────────────────────

class TestGovernanceFunnel:
    def test_empty_funnel(self, test_db):
        """Funnel returns zeros when no data exists."""
        result = compute_governance_funnel(test_db, date.today() - timedelta(days=7), date.today())
        assert result["aggregate"]["required"] == 0
        assert result["aggregate"]["submitted"] == 0

    def test_funnel_counts(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Funnel correctly counts attendance, submitted, delivered, viewed."""
        today = date.today()

        # 3 days of attendance
        for i in range(3):
            dt = today - timedelta(days=i)
            _make_attendance(test_db, sample_child, sample_class, dt)
        test_db.flush()

        # 2 submitted reports, 1 delivered
        created = datetime.now(timezone.utc) - timedelta(hours=5)
        _make_report(test_db, sample_child, sample_kindergarten, today,
                     models.DailyReportStatus.SUBMITTED, supervisor_user.id,
                     created_at=created, submitted_at=created + timedelta(hours=2))
        report2 = _make_report(test_db, sample_child, sample_kindergarten, today - timedelta(days=1),
                               models.DailyReportStatus.SENT_TO_PARENT, supervisor_user.id,
                               created_at=created, submitted_at=created + timedelta(hours=1),
                               sent_at=created + timedelta(hours=3))
        # Draft (not counted as submitted)
        _make_report(test_db, sample_child, sample_kindergarten, today - timedelta(days=2),
                     models.DailyReportStatus.DRAFT, supervisor_user.id)
        test_db.commit()

        # Add a view for the delivered report
        view = models.DailyReportView(daily_report_id=report2.id, parent_user_id=supervisor_user.id)
        test_db.add(view)
        test_db.commit()

        result = compute_governance_funnel(test_db, today - timedelta(days=7), today)
        agg = result["aggregate"]

        assert agg["required"] == 3
        assert agg["submitted"] == 2  # SUBMITTED + SENT_TO_PARENT
        assert agg["delivered"] == 1
        assert agg["viewed"] == 1

    def test_funnel_kg_filter(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Funnel filters by kindergarten_id."""
        today = date.today()
        _make_attendance(test_db, sample_child, sample_class, today)
        _make_report(test_db, sample_child, sample_kindergarten, today,
                     models.DailyReportStatus.SUBMITTED, supervisor_user.id)
        test_db.commit()

        # Filter by correct KG
        result = compute_governance_funnel(test_db, today - timedelta(days=1), today, sample_kindergarten.id)
        assert result["aggregate"]["required"] == 1

        # Filter by wrong KG
        result = compute_governance_funnel(test_db, today - timedelta(days=1), today, 99999)
        assert result["aggregate"]["required"] == 0


class TestTimelinessMetrics:
    def test_timeliness_with_data(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Timeliness computes median/p90 from 14:00 anchor to submitted_at."""
        today = date.today()
        _make_attendance(test_db, sample_child, sample_class, today)

        created = datetime.combine(today, datetime.min.time()).replace(hour=14, minute=0, tzinfo=timezone.utc)
        submitted = datetime.combine(today, datetime.min.time()).replace(hour=16, minute=30, tzinfo=timezone.utc)
        
        _make_report(test_db, sample_child, sample_kindergarten, today,
                     models.DailyReportStatus.SUBMITTED, supervisor_user.id,
                     created_at=created,
                     submitted_at=submitted)
        test_db.commit()

        result = compute_timeliness_metrics(test_db, today - timedelta(days=1), today)
        assert sample_kindergarten.id in result["per_kindergarten"]
        kg_data = result["per_kindergarten"][sample_kindergarten.id]
        assert kg_data["sample_size"] == 1
        assert kg_data["median_hours"] >= 2.0  # ~2.5 hours


class TestQualityMetrics:
    def test_quality_rejection_rate(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Quality metrics compute rejection and first-pass rates."""
        today = date.today()
        # 1 rejected, 1 approved
        _make_report(test_db, sample_child, sample_kindergarten, today,
                     models.DailyReportStatus.REJECTED, supervisor_user.id)
        _make_report(test_db, sample_child, sample_kindergarten, today - timedelta(days=1),
                     models.DailyReportStatus.APPROVED, supervisor_user.id)
        test_db.commit()

        result = compute_quality_metrics(test_db, today - timedelta(days=7), today)
        kg_data = result["per_kindergarten"][sample_kindergarten.id]
        assert kg_data["rejected"] == 1
        assert kg_data["approved"] == 1
        assert kg_data["total"] == 2
        assert kg_data["rejection_rate"] == 0.5


class TestFairRanking:
    def test_bayesian_ranking(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Fair ranking produces Bayesian scores and filters by minimum threshold."""
        today = date.today()
        # Create enough attendance + reports to meet minimum threshold
        for i in range(6):
            dt = today - timedelta(days=i)
            _make_attendance(test_db, sample_child, sample_class, dt)
            _make_report(test_db, sample_child, sample_kindergarten, dt,
                         models.DailyReportStatus.SUBMITTED, supervisor_user.id)
        test_db.commit()

        funnel = compute_governance_funnel(test_db, today - timedelta(days=7), today)
        ranked = compute_fair_ranking(funnel, test_db)

        assert len(ranked) >= 1
        assert ranked[0]["rank"] == 1
        assert 0 <= ranked[0]["bayesian_score"] <= 1
        assert ranked[0]["kindergarten_id"] == sample_kindergarten.id

    def test_ranking_excludes_below_minimum(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """KGs below minimum required reports are excluded from ranking."""
        today = date.today()
        # Only 2 attendance records (below default threshold of 5)
        for i in range(2):
            _make_attendance(test_db, sample_child, sample_class, today - timedelta(days=i))
        test_db.commit()

        funnel = compute_governance_funnel(test_db, today - timedelta(days=7), today)
        ranked = compute_fair_ranking(funnel, test_db)
        assert len(ranked) == 0


class TestLowPerformers:
    def test_detect_low_performers(self, test_db, sample_child, sample_kindergarten, sample_class, supervisor_user):
        """Low performers are detected when submission rate is below threshold."""
        today = date.today()
        # 6 attendance days, 0 submitted reports
        for i in range(6):
            _make_attendance(test_db, sample_child, sample_class, today - timedelta(days=i))
        test_db.commit()

        funnel = compute_governance_funnel(test_db, today - timedelta(days=7), today)
        low = detect_low_performers(funnel, test_db)

        assert len(low) >= 1
        assert low[0]["kindergarten_id"] == sample_kindergarten.id
        assert low[0]["submission_rate"] == 0


class TestReminderCooldown:
    def test_can_send_when_no_prior(self, test_db):
        """Can send reminder when no prior exists."""
        can_send, last = check_reminder_cooldown(test_db, "kindergarten", 1)
        assert can_send is True
        assert last is None

    def test_cooldown_blocks_repeat(self, test_db, admin_user, sample_kindergarten):
        """Cooldown prevents sending reminder again within window."""
        send_governance_reminder(
            test_db, admin_user,
            "kindergarten", sample_kindergarten.id,
            "low_submission_rate", {"rate": 0.3},
        )

        can_send, last = check_reminder_cooldown(test_db, "kindergarten", sample_kindergarten.id)
        assert can_send is False
        assert last is not None

    def test_cooldown_expires(self, test_db, admin_user, sample_kindergarten):
        """After cooldown expires, can send again."""
        now = datetime.now(timezone.utc)
        reminder = models.GovernanceReminder(
            target_type="kindergarten",
            target_id=sample_kindergarten.id,
            reminder_type="low_submission_rate",
            sent_by=admin_user.id,
            sent_at=now - timedelta(hours=49),
            cooldown_expires_at=now - timedelta(hours=1),
            payload={},
        )
        test_db.add(reminder)
        test_db.commit()

        can_send, last = check_reminder_cooldown(test_db, "kindergarten", sample_kindergarten.id)
        assert can_send is True

    def test_reminder_creates_notification(self, test_db, admin_user, sample_kindergarten, manager_user):
        """Sending reminder to KG creates notifications for managers."""
        send_governance_reminder(
            test_db, admin_user,
            "kindergarten", sample_kindergarten.id,
            "low_submission_rate",
        )

        notifications = test_db.query(models.Notification).filter(
            models.Notification.user_id == manager_user.id,
            models.Notification.notification_type == models.NotificationType.GOVERNANCE_REMINDER,
        ).all()
        assert len(notifications) == 1


# ── API tests ────────────────────────────────────────────────────────────

class TestGovernanceAPI:
    def test_kpis_endpoint_admin(self, client, auth_headers_admin, sample_kindergarten, sample_class):
        """GET /api/admin/governance/kpis returns funnel data for admin."""
        today = date.today()
        resp = client.get(
            f"/api/admin/governance/kpis?start_date={today - timedelta(days=7)}&end_date={today}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "funnel" in data
        assert "timeliness" in data
        assert "quality" in data
        assert "consistency" in data

    def test_kpis_endpoint_non_admin_forbidden(self, client, auth_headers_manager):
        """GET /api/admin/governance/kpis returns 403 for non-admin."""
        today = date.today()
        resp = client.get(
            f"/api/admin/governance/kpis?start_date={today - timedelta(days=7)}&end_date={today}",
            headers=auth_headers_manager,
        )
        assert resp.status_code == 403

    def test_leaderboard_endpoint(self, client, auth_headers_admin, sample_kindergarten, sample_class):
        """GET /api/admin/governance/leaderboard returns sorted list."""
        today = date.today()
        resp = client.get(
            f"/api/admin/governance/leaderboard?start_date={today - timedelta(days=7)}&end_date={today}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert "low_performers" in data

    def test_send_reminder_endpoint(self, client, auth_headers_admin, sample_kindergarten, sample_class, manager_user):
        """POST /api/admin/governance/reminders sends reminder successfully."""
        resp = client.post(
            "/api/admin/governance/reminders",
            headers=auth_headers_admin,
            json={
                "target_type": "kindergarten",
                "target_id": sample_kindergarten.id,
                "reminder_type": "low_submission_rate",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_type"] == "kindergarten"
        assert data["target_id"] == sample_kindergarten.id
        assert "cooldown_expires_at" in data

    def test_send_reminder_cooldown(self, client, auth_headers_admin, sample_kindergarten, sample_class, manager_user):
        """POST /api/admin/governance/reminders respects cooldown."""
        # First send
        resp1 = client.post(
            "/api/admin/governance/reminders",
            headers=auth_headers_admin,
            json={"target_type": "kindergarten", "target_id": sample_kindergarten.id},
        )
        assert resp1.status_code == 200

        # Second send — blocked by cooldown
        resp2 = client.post(
            "/api/admin/governance/reminders",
            headers=auth_headers_admin,
            json={"target_type": "kindergarten", "target_id": sample_kindergarten.id},
        )
        assert resp2.status_code == 429

    def test_send_reminder_non_admin(self, client, auth_headers_manager, sample_kindergarten):
        """POST /api/admin/governance/reminders blocked for non-admin."""
        resp = client.post(
            "/api/admin/governance/reminders",
            headers=auth_headers_manager,
            json={"target_type": "kindergarten", "target_id": sample_kindergarten.id},
        )
        assert resp.status_code == 403

    def test_list_reminders(self, client, auth_headers_admin, sample_kindergarten, sample_class, manager_user):
        """GET /api/admin/governance/reminders returns paginated list."""
        # Send one first
        client.post(
            "/api/admin/governance/reminders",
            headers=auth_headers_admin,
            json={"target_type": "kindergarten", "target_id": sample_kindergarten.id},
        )
        resp = client.get("/api/admin/governance/reminders", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    def test_kpis_invalid_dates(self, client, auth_headers_admin):
        """GET /api/admin/governance/kpis rejects end_date < start_date."""
        resp = client.get(
            "/api/admin/governance/kpis?start_date=2026-02-10&end_date=2026-02-01",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 400

    def test_report_view_endpoint(self, client, test_db, auth_headers_parent,
                                   parent_user, sample_child, sample_kindergarten,
                                   supervisor_user, sample_class):
        """POST /api/daily-reports/{id}/view records parent view."""
        report = _make_report(
            test_db, sample_child, sample_kindergarten, date.today(),
            models.DailyReportStatus.SENT_TO_PARENT, supervisor_user.id,
        )
        test_db.commit()

        resp = client.post(
            f"/api/daily-reports/{report.id}/view",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "recorded"

        # Idempotent — second call returns already_recorded
        resp2 = client.post(
            f"/api/daily-reports/{report.id}/view",
            headers=auth_headers_parent,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_recorded"
