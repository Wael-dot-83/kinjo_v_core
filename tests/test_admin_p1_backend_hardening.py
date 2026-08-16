"""Exploit-focused regressions for Admin backend authorization and recovery controls."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

import pytest

import models
from admin_security import (
    APIError,
    can_admin_access_user,
    compute_diff,
    redact_sensitive_data,
    require_admin_or_manager_role,
)
from auth import get_password_hash, verify_password
from conftest import csrf_pair


def _create_user(
    db,
    username: str,
    role: models.UserRole,
    *,
    kindergarten_id=None,
    deleted_at=None,
):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id,
        deleted_at=deleted_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client, username: str) -> dict:
    response = client.post("/token", data={"username": username, "password": "Admin123!"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}", **csrf_pair()}


class TestFailClosedManagerScope:
    def test_unassigned_manager_dependency_and_object_check_fail_closed(self):
        # Model constraints prevent new null-scope Managers, but legacy/corrupt
        # rows and partially hydrated identities still must fail closed.
        manager = models.User(
            id=901,
            username="unscoped_manager",
            role=models.UserRole.MANAGER,
            kindergarten_id=None,
        )
        unassigned_parent = models.User(
            id=902,
            username="unassigned_parent",
            role=models.UserRole.PARENT,
            kindergarten_id=None,
        )

        with pytest.raises(APIError) as exc_info:
            require_admin_or_manager_role(manager)

        assert exc_info.value.status_code == 403
        assert can_admin_access_user(manager, unassigned_parent) is False

    def test_unassigned_manager_cannot_list_unassigned_users(self, client, test_db):
        from admin_endpoints import get_current_user
        from main import app

        manager = models.User(
            id=903,
            username="unscoped_route_manager",
            role=models.UserRole.MANAGER,
            kindergarten_id=None,
        )
        _create_user(test_db, "unassigned_route_parent", models.UserRole.PARENT)

        app.dependency_overrides[get_current_user] = lambda: manager
        try:
            response = client.get("/api/admin/users")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 403


class TestPeerAdminMFAIsolation:
    def test_admin_cannot_read_or_bypass_peer_admin_mfa(
        self, client, test_db, admin_user, auth_headers_admin
    ):
        peer = _create_user(test_db, "peer_mfa_admin", models.UserRole.ADMIN)
        peer.mfa_enabled = True
        peer.mfa_secret = "peer-secret"
        test_db.commit()

        status_response = client.get(
            f"/api/admin/users/{peer.id}/mfa-status",
            headers=auth_headers_admin,
        )
        bypass_response = client.post(
            f"/api/admin/users/{peer.id}/mfa-bypass",
            headers=auth_headers_admin,
            json={
                "user_id": peer.id,
                "admin_password": "Admin123!",
                "reason": "attempted peer takeover",
            },
        )

        assert status_response.status_code == 403
        assert bypass_response.status_code == 403
        test_db.refresh(peer)
        assert peer.mfa_enabled is True
        assert peer.mfa_secret == "peer-secret"

    def test_mfa_bypass_rejects_path_body_user_mismatch(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        target = _create_user(
            test_db,
            "mfa_mismatch_target",
            models.UserRole.SUPERVISOR,
            kindergarten_id=sample_kindergarten.id,
        )

        response = client.post(
            f"/api/admin/users/{target.id}/mfa-bypass",
            headers=auth_headers_admin,
            json={
                "user_id": target.id + 1,
                "admin_password": "Admin123!",
                "reason": "mismatched identifiers",
            },
        )

        assert response.status_code == 400


class TestPasswordResetCompatibilityAlias:
    def test_alias_enforces_captcha(self, client):
        with patch("api.users.captcha_required", return_value=True), patch(
            "api.users.verify_captcha", return_value=False
        ):
            response = client.post(
                "/api/admin/password-reset-request",
                json={"email": "target@example.com", "captcha_token": "bad-token"},
                headers=csrf_pair(),
            )

        assert response.status_code == 400

    def test_alias_does_not_issue_token_for_deleted_user(self, client, test_db):
        deleted_user = _create_user(
            test_db,
            "deleted_reset_target",
            models.UserRole.PARENT,
            deleted_at=datetime.now(timezone.utc),
        )

        with patch("api.users.issue_password_reset_token") as issue_token:
            response = client.post(
                "/api/admin/password-reset-request",
                json={"email": deleted_user.email},
                headers=csrf_pair(),
            )

        assert response.status_code == 200
        issue_token.assert_not_called()
        assert test_db.query(models.PasswordResetToken).filter_by(user_id=deleted_user.id).count() == 0

    def test_alias_applies_canonical_password_lifecycle(self, client, test_db, parent_user):
        from api.auth.password_reset_service import issue_password_reset_token

        parent_user.must_change_password = True
        parent_user.password_changed_at = None
        test_db.commit()
        token = issue_password_reset_token(test_db, parent_user)

        response = client.post(
            "/api/admin/password-reset-confirm",
            json={"token": token, "new_password": "NewAliasPass123!"},
            headers=csrf_pair(),
        )

        assert response.status_code == 200
        test_db.refresh(parent_user)
        assert parent_user.must_change_password is False
        assert parent_user.password_changed_at is not None
        assert parent_user.updated_at is not None
        assert verify_password("NewAliasPass123!", parent_user.hashed_password)
        token_record = test_db.query(models.PasswordResetToken).filter_by(token=token).one()
        assert token_record.used is True


class TestAtomicParentCreation:
    def test_late_audit_failure_rolls_back_user_profile_and_children(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        payload = {
            "username": "atomic_parent",
            "email": "atomic_parent@example.com",
            "password": "SecurePass123!",
            "role": "PARENT",
            "kindergarten_id": sample_kindergarten.id,
            "children": [
                {
                    "first_name": "Child",
                    "last_name": "Atomic",
                    "date_of_birth": (date.today() - timedelta(days=365 * 2)).isoformat(),
                    "gender": "MALE",
                    "father_name": "Father Atomic",
                    "mother_first_name": "Mother",
                    "mother_last_name": "Atomic",
                    "mother_nationality": "Jordanian",
                }
            ],
        }

        with patch("admin_endpoints.log_audit_event", side_effect=RuntimeError("audit unavailable")):
            with pytest.raises(RuntimeError, match="audit unavailable"):
                client.post(
                    "/api/admin/users",
                    json=payload,
                    headers=auth_headers_admin,
                )

        assert test_db.query(models.User).filter_by(username="atomic_parent").count() == 0
        assert test_db.query(models.ParentProfile).count() == 0
        assert test_db.query(models.Child).count() == 0


class TestAuditContextHardening:
    def test_invalid_correlation_id_is_replaced_and_forwarded_ip_is_ignored(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        headers = {
            **auth_headers_admin,
            "X-Correlation-ID": "not-a-uuid",
            "X-Forwarded-For": "203.0.113.77",
        }
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "correlation_target",
                "email": "correlation_target@example.com",
                "password": "SecurePass123!",
                "role": "PARENT",
                "kindergarten_id": sample_kindergarten.id,
            },
        )

        assert response.status_code == 201
        response_id = response.headers["X-Correlation-ID"]
        assert str(UUID(response_id)) == response_id
        audit = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "USER_CREATED")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.request_id == response_id
        assert audit.ip_address != "203.0.113.77"

    def test_nested_diff_and_list_secrets_are_recursively_redacted(self):
        diff = compute_diff(
            {"settings": {"token": "old-token", "label": "before"}},
            {"settings": {"token": "new-token", "label": "after"}},
        )
        redacted = redact_sensitive_data(
            {"items": [[{"secret": "nested-secret", "visible": "ok"}]]}
        )

        assert diff["changed"]["settings"]["before"]["token"] == "[REDACTED]"
        assert diff["changed"]["settings"]["after"]["token"] == "[REDACTED]"
        assert redacted["items"][0][0]["secret"] == "[REDACTED]"
        assert redacted["items"][0][0]["visible"] == "ok"
