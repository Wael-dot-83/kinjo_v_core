"""ADMIN-003 — impersonation hardening (specification section 2.2).

One test per numbered requirement, plus the module-level invariants that keep
the limits from being widened by accident.


TODO(i18n-review): ADMIN-I18N-001 -- this file asserts on Arabic literals
authored in this branch rather than taken from the specification. If the
native-speaker pass in Phase 5 changes any wording, these assertions change
with it.
"""

import json

import pytest

import models
from conftest import bearer_headers
from routers.admin.impersonation import (
    IMPERSONATION_CHAIN_MAX_DEPTH,
    IMPERSONATION_MAX_DURATION_MINUTES,
    IMPERSONATION_MAX_SESSIONS_PER_DAY,
    _jordan_day_start,
)

IMPERSONATION_COOKIE = "kinjo_impersonation"


def _start(client, token, target_id, reason="Approved support case", *, restore_cookie=None):
    """POST /api/admin/impersonate.

    ``bearer_headers`` sends an explicit ``Cookie`` header for CSRF, which
    overrides httpx's cookie jar entirely. Tests that need the browser's real
    behaviour -- the restore cookie riding along on the next request -- must
    pass it through ``restore_cookie`` so it lands in the same header.
    """
    headers = bearer_headers(token)
    if restore_cookie:
        headers["Cookie"] = f"{headers['Cookie']}; {IMPERSONATION_COOKIE}={restore_cookie}"
    return client.post(
        "/api/admin/impersonate",
        json={"target_user_id": target_id, "reason": reason},
        headers=headers,
    )


def _second_manager(test_db, _kindergarten=None):
    """A second manager, for tests that need two distinct impersonation targets.

    Gets its own kindergarten: the platform enforces one active manager per
    kindergarten as a unique index, so reusing the fixture's kindergarten
    raises IntegrityError rather than creating a second manager.
    """
    from datetime import date

    from auth import get_password_hash

    kindergarten = models.Kindergarten(
        name_ar="حضانة النور",
        name_en="Light Kindergarten",
        license_number="LIC-2026-002",
        governorate="Amman",
        district="Amman",
        area="Sweifieh",
        address_line="45 Second Street",
        contact_phone="+962791234568",
        contact_email="contact@light.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)

    user = models.User(
        username="manager_two",
        email="manager_two@test.com",
        hashed_password=get_password_hash("Passw0rd!23"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten.id,
        full_name="Manager Two",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestHardLimits:
    """The constants are the control. Widening them must be deliberate."""

    def test_max_duration_is_thirty_minutes(self):
        assert IMPERSONATION_MAX_DURATION_MINUTES == 30

    def test_chain_depth_is_one(self):
        assert IMPERSONATION_CHAIN_MAX_DEPTH == 1

    def test_daily_quota_is_five(self):
        assert IMPERSONATION_MAX_SESSIONS_PER_DAY == 5

    def test_day_boundary_is_jordan_not_utc(self):
        """CLAUDE.md: operational dates are Jordan UTC+3, never UTC."""
        start = _jordan_day_start()

        assert start.utcoffset().total_seconds() == 3 * 3600
        assert (start.hour, start.minute, start.second) == (0, 0, 0)


class TestRequirement1SelfImpersonation:
    def test_admin_cannot_impersonate_themselves(self, client, admin_user, admin_token):
        response = _start(client, admin_token, admin_user.id)

        assert response.status_code == 422
        assert "yourself" in response.json()["detail"].lower()

    def test_self_attempt_is_audited(self, client, test_db, admin_user, admin_token):
        _start(client, admin_token, admin_user.id)

        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "IMPERSONATION_ATTEMPT_FAILED")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert "Self-impersonation" in row.impersonation_reason


class TestRequirement2AdminTarget:
    def test_admin_cannot_impersonate_another_admin(
        self, client, test_db, admin_user, admin_token
    ):
        from auth import get_password_hash

        other_admin = models.User(
            username="admin_two",
            email="admin_two@test.com",
            hashed_password=get_password_hash("Passw0rd!23"),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other_admin)
        test_db.commit()
        test_db.refresh(other_admin)

        response = _start(client, admin_token, other_admin.id)

        assert response.status_code == 403
        assert "Administrators cannot be impersonated." == response.json()["detail"]

    def test_non_manager_still_rejected(
        self, client, admin_user, supervisor_user, admin_token
    ):
        response = _start(client, admin_token, supervisor_user.id)

        assert response.status_code == 422


class TestRequirement3ChainPrevention:
    def test_cannot_start_a_second_session_while_impersonating(
        self, client, test_db, admin_user, manager_user, sample_kindergarten, admin_token
    ):
        other = _second_manager(test_db)

        first = _start(client, admin_token, manager_user.id)
        assert first.status_code == 200
        restore = client.cookies.get(IMPERSONATION_COOKIE)
        assert restore

        second = _start(client, admin_token, other.id, restore_cookie=restore)

        assert second.status_code == 409
        assert "Already impersonating" in second.json()["detail"]

    def test_chain_attempt_is_audited(
        self, client, test_db, admin_user, manager_user, sample_kindergarten, admin_token
    ):
        other = _second_manager(test_db)
        _start(client, admin_token, manager_user.id)
        restore = client.cookies.get(IMPERSONATION_COOKIE)
        _start(client, admin_token, other.id, restore_cookie=restore)

        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "IMPERSONATION_ATTEMPT_FAILED")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert "Chained impersonation refused" in row.impersonation_reason

    def test_chain_is_refused_before_the_target_is_resolved(
        self, client, admin_user, manager_user, admin_token
    ):
        """A chained request must not be able to probe for valid target ids."""
        _start(client, admin_token, manager_user.id)
        restore = client.cookies.get(IMPERSONATION_COOKIE)

        response = _start(client, admin_token, 999999, restore_cookie=restore)

        # 409 (already impersonating), not 404 (no such user).
        assert response.status_code == 409

    def test_an_impersonated_token_cannot_reach_the_endpoint_at_all(
        self, client, admin_user, manager_user, admin_token
    ):
        """The other half of chain prevention.

        Once the admin is carrying the target's token, they hold the target's
        permissions -- and a manager has no IMPERSONATE grant, so the endpoint
        refuses them before the chain guard is even consulted.
        """
        start = _start(client, admin_token, manager_user.id)
        assert start.status_code == 200

        impersonated_session = client.cookies.get("kinjo_session")
        response = client.post(
            "/api/admin/impersonate",
            json={"target_user_id": manager_user.id, "reason": "chain attempt"},
            headers={
                "X-CSRF-Token": "t" * 32,
                "Cookie": f"kinjo_csrf_token={'t' * 32}; kinjo_session={impersonated_session}",
            },
        )

        assert response.status_code == 403


class TestRequirement4TargetNotification:
    def test_response_reports_whether_the_target_was_notified(
        self, client, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)

        assert response.status_code == 200
        assert "target_notified" in response.json()

    def test_notification_outcome_is_audited(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        """A dead SMTP must be visible in the log, not silently skipped."""
        _start(client, admin_token, manager_user.id)

        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "IMPERSONATION_START")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        details = json.loads(row.details)
        assert "target_notified" in details
        assert isinstance(details["target_notified"], bool)

    def test_notification_is_attempted_with_both_languages(
        self, client, admin_user, manager_user, monkeypatch
    ):
        """Mandate 1: the security notice reaches the target in Arabic and English."""
        sent = {}

        def _capture(to_email, subject, body, attachments=None):
            sent["to"] = to_email
            sent["subject"] = subject
            sent["body"] = body

        monkeypatch.setattr("email_service.send_email", _capture)
        monkeypatch.setattr("email_service.is_smtp_configured", lambda: True)

        from routers.admin.impersonation import _notify_target

        notified = _notify_target(
            manager_user, admin_user, _jordan_day_start(), "203.0.113.9"
        )

        assert notified is True
        assert sent["to"] == manager_user.email
        assert "Security alert" in sent["subject"]
        assert "تنبيه أمني" in sent["subject"]
        assert "203.0.113.9" in sent["body"]
        assert "If this was not authorized" in sent["body"]
        assert "إذا لم يكن هذا الوصول" in sent["body"]

    def test_smtp_failure_does_not_break_impersonation(
        self, client, admin_user, manager_user, monkeypatch
    ):
        def _boom(*args, **kwargs):
            raise RuntimeError("SMTP configuration is missing")

        monkeypatch.setattr("email_service.send_email", _boom)

        from routers.admin.impersonation import _notify_target

        assert _notify_target(manager_user, admin_user, _jordan_day_start(), None) is False


class TestRequirement5SessionExpiry:
    def test_response_carries_an_expiry(
        self, client, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)

        assert response.status_code == 200
        assert response.json()["expires_at"]

    def test_expiry_is_at_most_thirty_minutes_out(
        self, client, admin_user, manager_user, admin_token
    ):
        from datetime import datetime, timedelta, timezone

        response = _start(client, admin_token, manager_user.id)
        expires_at = datetime.fromisoformat(response.json()["expires_at"])
        now = datetime.now(timezone(timedelta(hours=3)))

        assert expires_at - now <= timedelta(minutes=IMPERSONATION_MAX_DURATION_MINUTES)

    def test_cookies_expire_with_the_session(
        self, client, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)

        cap = IMPERSONATION_MAX_DURATION_MINUTES * 60
        for header in response.headers.get_list("set-cookie"):
            if "Max-Age=" in header:
                max_age = int(header.split("Max-Age=")[1].split(";")[0])
                assert max_age <= cap, header


class TestRequirement6SessionCorrelation:
    def test_start_returns_a_session_id(
        self, client, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)

        session_id = response.json()["session_id"]
        assert len(session_id) == 36  # uuid4

    def test_audit_row_carries_the_session_id(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)
        session_id = response.json()["session_id"]

        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "IMPERSONATION_START")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert row.impersonation_session_id == session_id

    def test_session_ids_are_unique_per_session(
        self, client, test_db, admin_user, manager_user, sample_kindergarten, admin_token
    ):
        other = _second_manager(test_db, sample_kindergarten)

        first = _start(client, admin_token, manager_user.id).json()["session_id"]
        client.cookies.delete(IMPERSONATION_COOKIE)
        second = _start(client, admin_token, other.id).json()["session_id"]

        assert first != second

    def test_audit_listener_stamps_rows_written_during_a_session(
        self, test_db, admin_user
    ):
        """database.py stamps every audit row created inside an impersonation."""
        # Real user ids, not literals: audit_logs.user_id and .impersonated_by
        # are foreign keys, and Postgres enforces them where SQLite does not.
        actor_id = admin_user.id
        test_db.info["impersonated_by"] = actor_id
        test_db.info["impersonation_reason"] = "support"
        test_db.info["impersonation_session_id"] = "session-under-test"
        try:
            row = models.AuditLog(
                user_id=actor_id, action="SOMETHING_ELSE",
                entity_type="User", entity_id=actor_id,
            )
            test_db.add(row)
            test_db.commit()

            assert row.impersonation_session_id == "session-under-test"
            assert row.impersonated_by == actor_id
        finally:
            test_db.info.pop("impersonated_by", None)
            test_db.info.pop("impersonation_reason", None)
            test_db.info.pop("impersonation_session_id", None)


class TestRequirement7Banner:
    def test_start_supplies_bilingual_banner_text(
        self, client, admin_user, manager_user, admin_token
    ):
        """Mandate 1: the banner ships from the server in both languages."""
        response = _start(client, admin_token, manager_user.id)
        banner = response.json()["banner"]

        target_name = manager_user.full_name or manager_user.username
        assert target_name in banner["ar"]
        assert target_name in banner["en"]
        assert "You are acting as" in banner["en"]
        assert "أنت تعمل باسم" in banner["ar"]

    def test_banner_names_the_expiry(
        self, client, admin_user, manager_user, admin_token
    ):
        response = _start(client, admin_token, manager_user.id)
        body = response.json()

        assert body["expires_at"] in body["banner"]["ar"]
        assert body["expires_at"] in body["banner"]["en"]


class TestRequirement8DailyQuota:
    def test_sixth_session_in_a_day_is_refused(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        from routers.admin.impersonation import _jordan_day_start

        # Seed the quota straight into the audit log, which is what the counter
        # reads. Going through the endpoint would trip the chain guard instead.
        for _ in range(IMPERSONATION_MAX_SESSIONS_PER_DAY):
            test_db.add(models.AuditLog(
                user_id=admin_user.id,
                action="IMPERSONATION_START",
                entity_type="User",
                entity_id=manager_user.id,
                created_at=_jordan_day_start(),
            ))
        test_db.commit()

        response = _start(client, admin_token, manager_user.id)

        assert response.status_code == 429
        assert "Daily impersonation limit" in response.json()["detail"]

    def test_quota_exhaustion_is_audited(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        for _ in range(IMPERSONATION_MAX_SESSIONS_PER_DAY):
            test_db.add(models.AuditLog(
                user_id=admin_user.id,
                action="IMPERSONATION_START",
                entity_type="User",
                entity_id=manager_user.id,
                created_at=_jordan_day_start(),
            ))
        test_db.commit()

        _start(client, admin_token, manager_user.id)

        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "IMPERSONATION_ATTEMPT_FAILED")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert "quota exhausted" in row.impersonation_reason

    def test_another_admins_usage_does_not_count_against_you(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        from auth import get_password_hash

        other_admin = models.User(
            username="admin_three",
            email="admin_three@test.com",
            hashed_password=get_password_hash("Passw0rd!23"),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other_admin)
        test_db.commit()
        test_db.refresh(other_admin)

        for _ in range(IMPERSONATION_MAX_SESSIONS_PER_DAY + 2):
            test_db.add(models.AuditLog(
                user_id=other_admin.id,
                action="IMPERSONATION_START",
                entity_type="User",
                entity_id=manager_user.id,
                created_at=_jordan_day_start(),
            ))
        test_db.commit()

        response = _start(client, admin_token, manager_user.id)

        assert response.status_code == 200


class TestAuthorization:
    def test_non_admin_cannot_impersonate(
        self, client, manager_user, supervisor_user, manager_token
    ):
        response = _start(client, manager_token, supervisor_user.id)

        assert response.status_code == 403

    def test_denial_uses_the_permission_layer(
        self, client, manager_user, supervisor_user, manager_token
    ):
        """ADMIN-001: the guard is Permission.IMPERSONATE, not an inline check."""
        response = _start(client, manager_token, supervisor_user.id)
        detail = response.json()["detail"]

        assert detail["code"] == "INSUFFICIENT_PERMISSIONS"
        assert detail["missing"] == ["admin:impersonate"]
