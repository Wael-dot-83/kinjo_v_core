"""Tests for the role-neutral account self-service endpoints (/api/me/*).

Before these endpoints existed, only ADMIN could edit its own profile or change
its own password through the API (`/api/admin/profile*` is behind
`require_admin`), and the shared settings page faked every save. These tests pin
down that a MANAGER — the role that had no path at all — can now do it, that the
changes actually persist, and that each rejection path really rejects.

`TestPasswordAgeTimezone` covers a separate, crash-level regression: see
`auth.requires_password_change`.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

import models
from auth import get_password_hash, requires_password_change, verify_password


def _auth(client, username, password):
    """Log in and return headers carrying the bearer token + CSRF double-submit pair."""
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


@pytest.fixture
def manager_headers(client, manager_user):
    return _auth(client, "testmanager", "Manager123!")


class TestProfileSelfService:
    def test_manager_can_read_own_profile(self, client, manager_headers):
        r = client.get("/api/me/profile", headers=manager_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["username"] == "testmanager"
        assert body["role"] == "MANAGER"

    def test_manager_can_update_own_profile_and_it_persists(
        self, client, test_db, manager_user, manager_headers
    ):
        r = client.put(
            "/api/me/profile",
            json={"full_name": "Updated Manager", "phone_number": "0791234567"},
            headers=manager_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["changed"] is True

        test_db.refresh(manager_user)
        assert manager_user.full_name == "Updated Manager"
        assert manager_user.phone_number == "0791234567"

    def test_response_carries_both_languages(self, client, manager_headers):
        r = client.put(
            "/api/me/profile", json={"full_name": "Bilingual Check"}, headers=manager_headers
        )
        assert r.status_code == 200
        body = r.json()
        # CLAUDE.md: UI-visible backend strings must supply _ar and _en.
        assert body["message_ar"] and body["message_en"]
        assert body["message_ar"] != body["message_en"]

    def test_unchanged_submit_reports_no_change(self, client, manager_user, manager_headers):
        payload = {"full_name": "Same Name", "phone_number": "0791234567"}
        first = client.put("/api/me/profile", json=payload, headers=manager_headers)
        assert first.json()["changed"] is True
        second = client.put("/api/me/profile", json=payload, headers=manager_headers)
        assert second.status_code == 200
        assert second.json()["changed"] is False

    def test_invalid_phone_is_rejected(self, client, test_db, manager_user, manager_headers):
        r = client.put(
            "/api/me/profile", json={"phone_number": "12345"}, headers=manager_headers
        )
        assert r.status_code >= 400
        test_db.refresh(manager_user)
        assert manager_user.phone_number != "12345"

    def test_profile_update_is_audited(self, client, test_db, manager_user, manager_headers):
        client.put("/api/me/profile", json={"full_name": "Audited"}, headers=manager_headers)
        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "USER_PROFILE_UPDATED")
            .first()
        )
        assert row is not None, "profile update must leave an audit trail"

    def test_endpoint_requires_authentication(self, client):
        assert client.get("/api/me/profile").status_code in (401, 403)

    def test_cannot_change_own_role_or_username(self, client, test_db, manager_user, manager_headers):
        """Identity fields are not in the schema, so they must be ignored, not applied."""
        r = client.put(
            "/api/me/profile",
            json={"full_name": "Ok", "username": "hacked", "role": "ADMIN", "email": "x@y.z"},
            headers=manager_headers,
        )
        assert r.status_code == 200, r.text
        test_db.refresh(manager_user)
        assert manager_user.username == "testmanager"
        assert manager_user.role == models.UserRole.MANAGER
        assert manager_user.email == "manager@test.com"


class TestPasswordSelfService:
    def test_manager_can_change_own_password(
        self, client, test_db, manager_user, manager_headers
    ):
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "Manager123!",
                "new_password": "BrandNew@2026",
                "confirm_password": "BrandNew@2026",
            },
            headers=manager_headers,
        )
        assert r.status_code == 200, r.text
        test_db.refresh(manager_user)
        assert verify_password("BrandNew@2026", manager_user.hashed_password)

    def test_wrong_current_password_rejected(
        self, client, test_db, manager_user, manager_headers
    ):
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "NotMyPassword1!",
                "new_password": "BrandNew@2026",
                "confirm_password": "BrandNew@2026",
            },
            headers=manager_headers,
        )
        assert r.status_code >= 400
        test_db.refresh(manager_user)
        assert verify_password("Manager123!", manager_user.hashed_password)

    def test_failed_attempt_is_audited(self, client, test_db, manager_user, manager_headers):
        client.post(
            "/api/me/password",
            json={
                "current_password": "NotMyPassword1!",
                "new_password": "BrandNew@2026",
                "confirm_password": "BrandNew@2026",
            },
            headers=manager_headers,
        )
        row = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "USER_PASSWORD_CHANGE_FAILED")
            .first()
        )
        assert row is not None, "a failed password change must be audited"

    def test_mismatched_confirmation_rejected(self, client, manager_headers):
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "Manager123!",
                "new_password": "BrandNew@2026",
                "confirm_password": "Different@2026",
            },
            headers=manager_headers,
        )
        assert r.status_code >= 400

    def test_weak_password_rejected_by_policy(self, client, manager_headers):
        """min_length alone would let this through; the full policy must not."""
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "Manager123!",
                "new_password": "alllowercase",
                "confirm_password": "alllowercase",
            },
            headers=manager_headers,
        )
        assert r.status_code >= 400

    def test_reusing_current_password_rejected(self, client, manager_headers):
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "Manager123!",
                "new_password": "Manager123!",
                "confirm_password": "Manager123!",
            },
            headers=manager_headers,
        )
        assert r.status_code >= 400


class TestNotificationPreferences:
    def test_defaults_are_on(self, client, manager_headers):
        r = client.get("/api/me/notification-preferences", headers=manager_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"in_app": True, "email": True}

    def test_update_round_trips(self, client, manager_headers):
        put = client.put(
            "/api/me/notification-preferences",
            json={"in_app": True, "email": False},
            headers=manager_headers,
        )
        assert put.status_code == 200, put.text
        get = client.get("/api/me/notification-preferences", headers=manager_headers)
        assert get.json()["email"] is False
        assert get.json()["in_app"] is True

    def test_update_preserves_other_writers_keys(
        self, client, test_db, manager_user, manager_headers
    ):
        """routers/supervisor.py stores richer per-event keys in the same column."""
        manager_user.notification_preferences = {
            "in_app": True,
            "email": True,
            "new_messages": {"in_app": True, "email": False},
        }
        test_db.commit()

        client.put(
            "/api/me/notification-preferences",
            json={"in_app": False, "email": False},
            headers=manager_headers,
        )
        test_db.refresh(manager_user)
        assert manager_user.notification_preferences["new_messages"] == {
            "in_app": True,
            "email": False,
        }, "unrelated preference keys must survive a channel-toggle save"


class TestPasswordAgeTimezone:
    """Regression: password age must not explode on a naive stored timestamp.

    `User.password_changed_at` is DateTime(timezone=True), but SQLite has no
    tz-aware type and returns the value naive. `requires_password_change`
    subtracted it from an aware `datetime.now(timezone.utc)`, raising
      TypeError: can't subtract offset-naive and offset-aware datetimes
    That dependency runs on every authenticated page, so any account that had
    ever changed its password got a 500 on every page it opened. It stayed
    hidden only because seeded users have the column NULL.
    """

    def test_naive_recent_timestamp_does_not_raise(self, test_db):
        user = models.User(
            username="naive_recent",
            email="naive_recent@test.com",
            hashed_password=get_password_hash("Whatever1!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            # Naive UTC, exactly as SQLite hands the column back.
            password_changed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        assert requires_password_change(user) is False

    def test_naive_old_timestamp_still_expires(self, test_db):
        user = models.User(
            username="naive_old",
            email="naive_old@test.com",
            hashed_password=get_password_hash("Whatever1!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            password_changed_at=(
                datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)
            ),
        )
        assert requires_password_change(user) is True

    def test_aware_timestamp_still_works(self, test_db):
        user = models.User(
            username="aware_recent",
            email="aware_recent@test.com",
            hashed_password=get_password_hash("Whatever1!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            password_changed_at=datetime.now(timezone.utc),
        )
        assert requires_password_change(user) is False

    def test_authenticated_page_after_password_change(
        self, client, test_db, manager_user, manager_headers
    ):
        """End-to-end: change the password, then load an authenticated page.

        This is the exact sequence that produced the 500.
        """
        r = client.post(
            "/api/me/password",
            json={
                "current_password": "Manager123!",
                "new_password": "BrandNew@2026",
                "confirm_password": "BrandNew@2026",
            },
            headers=manager_headers,
        )
        assert r.status_code == 200, r.text

        fresh = _auth(client, "testmanager", "BrandNew@2026")
        page = client.get("/api/me/profile", headers=fresh)
        assert page.status_code == 200, (
            f"authenticated request failed after a password change: {page.text}"
        )
