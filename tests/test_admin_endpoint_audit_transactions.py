"""Failure-injection coverage for Admin endpoint audit transaction boundaries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import MagicMock

import pytest

import models
from audit_actions import AuditAction
from auth import get_password_hash, verify_password


def _create_user(db, username, role=models.UserRole.SUPERVISOR, kindergarten_id=None):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Target123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _fail_action(action_to_fail):
    from admin_endpoints import log_audit_event as real_log_audit_event

    def failing_log(*args, **kwargs):
        action = kwargs.get("action")
        if action is None and len(args) > 1:
            action = args[1]
        if action == action_to_fail:
            raise RuntimeError("audit unavailable")
        return real_log_audit_event(*args, **kwargs)

    return failing_log


def test_user_update_rolls_back_when_audit_write_fails(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "audit_update_target",
        kindergarten_id=sample_kindergarten.id,
    )
    original_email = target.email

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.USER_UPDATED),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.put(
                f"/api/admin/users/{target.id}",
                headers=auth_headers_admin,
                json={"email": "mutated@example.com"},
            )

    test_db.expire_all()
    persisted = test_db.get(models.User, target.id)
    assert persisted.email == original_email


def test_bulk_create_rolls_back_every_user_when_audit_write_fails(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    username = "audit_bulk_create_target"
    payload = {
        "users": [
            {
                "username": username,
                "email": f"{username}@example.com",
                "password": "Target123!",
                "role": "SUPERVISOR",
                "kindergarten_id": sample_kindergarten.id,
            }
        ]
    }

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.BULK_USER_CREATE),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/admin/users/bulk-create",
                headers=auth_headers_admin,
                json=payload,
            )

    test_db.expire_all()
    assert test_db.query(models.User).filter_by(username=username).count() == 0


def test_bulk_delete_is_atomic_and_confirmation_token_cannot_be_replayed(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "audit_bulk_delete_target",
        kindergarten_id=sample_kindergarten.id,
    )
    payload = {"user_ids": [target.id]}
    confirmation = client.post(
        "/api/admin/users/bulk-delete",
        headers=auth_headers_admin,
        json=payload,
    )
    assert confirmation.status_code == 200
    token = confirmation.json()["confirmation_token"]

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.BULK_USER_DELETE),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/admin/users/bulk-delete",
                headers=auth_headers_admin,
                json={**payload, "confirmation_token": token},
            )

    test_db.expire_all()
    persisted = test_db.get(models.User, target.id)
    assert persisted.deleted_at is None
    assert persisted.status == models.UserStatus.ACTIVE

    replay = client.post(
        "/api/admin/users/bulk-delete",
        headers=auth_headers_admin,
        json={**payload, "confirmation_token": token},
    )
    assert replay.status_code == 400


def test_message_and_recipient_rows_roll_back_when_audit_write_fails(
    client, test_db, auth_headers_admin, parent_user
):
    subject = "Atomic audit announcement"

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.ADMIN_MESSAGE_SENT),
    ):
        response = client.post(
            "/api/admin/messages",
            headers=auth_headers_admin,
            json={
                "subject": subject,
                "message_body": "This must not survive its failed audit.",
                "target": {"mode": "ALL_PARENTS"},
            },
        )

    assert response.status_code == 500
    assert test_db.query(models.Message).filter_by(subject=subject).count() == 0
    assert test_db.query(models.MessageRecipient).count() == 0


def test_message_rolls_back_when_notification_audit_write_fails(
    client, test_db, auth_headers_admin, parent_user
):
    subject = "Atomic notification audit announcement"

    with (
        patch("admin_endpoints.create_message_notifications", return_value=True),
        patch(
            "admin_endpoints.log_audit_event",
            side_effect=_fail_action(AuditAction.MESSAGE_NOTIFICATIONS_QUEUED),
        ),
    ):
        response = client.post(
            "/api/admin/messages",
            headers=auth_headers_admin,
            json={
                "subject": subject,
                "message_body": "Notification audit failure must roll back everything.",
                "target": {"mode": "ALL_PARENTS"},
            },
        )

    assert response.status_code == 500
    assert test_db.query(models.Message).filter_by(subject=subject).count() == 0
    assert test_db.query(models.MessageRecipient).count() == 0


def test_audit_cleanup_rolls_back_deleted_history_when_its_audit_fails(
    client, test_db, admin_user, auth_headers_admin
):
    historical = models.AuditLog(
        user_id=admin_user.id,
        action="HISTORICAL_EVENT",
        entity_type="User",
        entity_id=admin_user.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    test_db.add(historical)
    test_db.commit()
    historical_id = historical.id

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.AUDIT_LOG_CLEANUP),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/admin/audit-logs/cleanup?days=90",
                headers=auth_headers_admin,
            )

    test_db.expire_all()
    assert test_db.get(models.AuditLog, historical_id) is not None


def test_rejected_mfa_bypass_audit_is_durable(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "audit_mfa_rejection_target",
        kindergarten_id=sample_kindergarten.id,
    )

    response = client.post(
        f"/api/admin/users/{target.id}/mfa-bypass",
        headers=auth_headers_admin,
        json={
            "user_id": target.id,
            "admin_password": "definitely-wrong",
            "reason": "test rejected-attempt durability",
        },
    )

    assert response.status_code == 401
    test_db.rollback()
    audit = (
        test_db.query(models.AuditLog)
        .filter(
            models.AuditLog.action == AuditAction.MFA_BYPASS_FAILED_AUTH,
            models.AuditLog.entity_id == target.id,
        )
        .one_or_none()
    )
    assert audit is not None


def test_reset_request_rolls_back_token_and_preserves_anti_enumeration_on_audit_failure(
    client, test_db, parent_user
):
    with patch("api.users.deliver_password_reset_email") as deliver, patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        response = client.post(
            "/api/users/request-password-reset",
            json={"email": parent_user.email},
        )

    unknown = client.post(
        "/api/users/request-password-reset",
        json={"email": "unknown-reset-user@example.com"},
    )
    assert response.status_code == unknown.status_code == 200
    assert response.json() == unknown.json()
    deliver.assert_not_called()
    assert (
        test_db.query(models.PasswordResetToken)
        .filter_by(user_id=parent_user.id)
        .count()
        == 0
    )


def test_admin_reset_request_alias_uses_single_shared_atomic_audit(
    client, test_db, parent_user
):
    with patch("api.users.deliver_password_reset_email", return_value=False), patch(
        "admin_endpoints.log_audit_event"
    ) as alias_audit:
        response = client.post(
            "/api/admin/password-reset-request",
            json={"email": parent_user.email},
        )

    assert response.status_code == 200
    alias_audit.assert_not_called()
    assert (
        test_db.query(models.PasswordResetToken)
        .filter_by(user_id=parent_user.id, used=False)
        .count()
        == 1
    )
    assert (
        test_db.query(models.AuditLog)
        .filter(
            models.AuditLog.action == AuditAction.PASSWORD_RESET_REQUESTED,
            models.AuditLog.entity_id == parent_user.id,
        )
        .count()
        == 1
    )


def test_canonical_password_reset_rolls_back_password_and_token_on_audit_failure(
    client, test_db, parent_user
):
    from api.auth.password_reset_service import issue_password_reset_token

    token = issue_password_reset_token(test_db, parent_user)
    original_hash = parent_user.hashed_password

    with patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/users/reset-password",
                json={"token": token, "new_password": "CanonicalNew123!"},
            )

    test_db.expire_all()
    persisted_user = test_db.get(models.User, parent_user.id)
    token_record = (
        test_db.query(models.PasswordResetToken)
        .filter_by(token=token)
        .one()
    )
    assert persisted_user.hashed_password == original_hash
    assert verify_password("Parent123!", persisted_user.hashed_password)
    assert token_record.used is False


def test_rejected_password_policy_does_not_consume_reset_token(
    client, test_db, parent_user
):
    from api.auth.password_reset_service import issue_password_reset_token

    token = issue_password_reset_token(test_db, parent_user)
    response = client.post(
        "/api/users/reset-password",
        json={"token": token, "new_password": "weak"},
    )

    assert response.status_code == 400
    test_db.expire_all()
    token_record = (
        test_db.query(models.PasswordResetToken)
        .filter_by(token=token)
        .one()
    )
    assert token_record.used is False


def test_admin_password_reset_alias_rolls_back_password_and_token_on_audit_failure(
    client, test_db, parent_user
):
    from api.auth.password_reset_service import issue_password_reset_token

    token = issue_password_reset_token(test_db, parent_user)
    original_hash = parent_user.hashed_password

    with patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.PASSWORD_RESET_COMPLETED),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/admin/password-reset-confirm",
                json={"token": token, "new_password": "AliasNew123!"},
            )

    test_db.expire_all()
    persisted_user = test_db.get(models.User, parent_user.id)
    token_record = (
        test_db.query(models.PasswordResetToken)
        .filter_by(token=token)
        .one()
    )
    assert persisted_user.hashed_password == original_hash
    assert verify_password("Parent123!", persisted_user.hashed_password)
    assert token_record.used is False


def test_canonical_user_create_rolls_back_when_audit_write_fails(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    username = "canonical_audit_create"
    with patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/users",
                headers=auth_headers_admin,
                json={
                    "username": username,
                    "email": f"{username}@example.com",
                    "password": "Target123!",
                    "role": "SUPERVISOR",
                    "kindergarten_id": sample_kindergarten.id,
                },
            )

    assert test_db.query(models.User).filter_by(username=username).count() == 0


def test_canonical_user_update_rolls_back_when_audit_write_fails(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "canonical_audit_update",
        kindergarten_id=sample_kindergarten.id,
    )
    original_email = target.email

    with patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.put(
                f"/api/users/{target.id}",
                headers=auth_headers_admin,
                json={"email": "canonical-mutated@example.com"},
            )

    test_db.expire_all()
    assert test_db.get(models.User, target.id).email == original_email


def test_canonical_user_delete_rolls_back_when_audit_write_fails(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "canonical_audit_delete",
        kindergarten_id=sample_kindergarten.id,
    )

    with patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.delete(
                f"/api/users/{target.id}",
                headers=auth_headers_admin,
            )

    test_db.expire_all()
    persisted = test_db.get(models.User, target.id)
    assert persisted.deleted_at is None
    assert persisted.status == models.UserStatus.ACTIVE


def test_canonical_bulk_status_rolls_back_when_audit_write_fails(
    client, test_db, admin_user, auth_headers_admin, sample_kindergarten
):
    target = _create_user(
        test_db,
        "canonical_audit_bulk_status",
        kindergarten_id=sample_kindergarten.id,
    )

    with patch(
        "api.users.validators.log_audit_action",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(
                "/api/users/bulk-status-update",
                headers=auth_headers_admin,
                json={"user_ids": [target.id], "new_status": "INACTIVE"},
            )

    test_db.expire_all()
    assert test_db.get(models.User, target.id).status == models.UserStatus.ACTIVE


def test_legacy_admin_reset_alias_rejects_non_admin_actor(
    client, test_db, auth_headers_parent, sample_kindergarten
):
    target = _create_user(
        test_db,
        "legacy_reset_auth_target",
        kindergarten_id=sample_kindergarten.id,
    )
    original_hash = target.hashed_password

    response = client.post(
        f"/api/users/{target.id}/admin-reset-password",
        headers=auth_headers_parent,
        json={"new_password": "Unauthorized123!", "admin_password": "Parent123!"},
    )

    assert response.status_code == 403
    test_db.expire_all()
    assert test_db.get(models.User, target.id).hashed_password == original_hash


def test_password_reset_race_loser_cannot_change_password(test_db, parent_user):
    from api.users import apply_password_reset
    from api.auth.password_reset_service import issue_password_reset_token, resolve_valid_token

    token = issue_password_reset_token(test_db, parent_user)
    token_record = resolve_valid_token(test_db, token)
    original_hash = parent_user.hashed_password
    losing_claim = MagicMock()
    losing_claim.filter.return_value.update.return_value = 0

    with patch("api.users.resolve_valid_token", return_value=token_record), patch.object(
        test_db, "query", return_value=losing_claim
    ):
        result = apply_password_reset(test_db, token, "RaceLoser123!")

    assert result is None
    assert parent_user.hashed_password == original_hash


def test_password_reset_issuance_locks_the_user_namespace():
    from api.auth.password_reset_service import issue_password_reset_token

    db = MagicMock()
    user_lock_query = MagicMock()
    token_update_query = MagicMock()
    db.query.side_effect = [user_lock_query, token_update_query]
    user = SimpleNamespace(id=77)

    token = issue_password_reset_token(db, user, commit=False)

    assert token
    user_lock_query.filter.return_value.with_for_update.assert_called_once_with()
    user_lock_query.filter.return_value.with_for_update.return_value.one.assert_called_once_with()
    token_update_query.filter.return_value.update.assert_called_once_with({"used": True})
    db.flush.assert_called_once_with()


def test_backup_outcome_audit_failure_is_not_mislabeled_as_operation_failure(
    client, test_db, auth_headers_admin
):
    task = SimpleNamespace(id="backup-task-1")
    with patch("backup_tasks.run_backup.delay", return_value=task), patch(
        "admin_endpoints.log_audit_event",
        side_effect=_fail_action(AuditAction.BACKUP_ENQUEUED),
    ):
        response = client.post(
            "/api/admin/backup/create",
            headers=auth_headers_admin,
        )

    assert response.status_code == 500
    test_db.rollback()
    actions = {
        row[0]
        for row in test_db.query(models.AuditLog.action)
        .filter(
            models.AuditLog.action.in_(
                [AuditAction.BACKUP_ENQUEUE_ATTEMPTED, AuditAction.BACKUP_FAILED]
            )
        )
        .all()
    }
    assert actions == {AuditAction.BACKUP_ENQUEUE_ATTEMPTED}


def test_backup_operation_failure_records_durable_attempt_and_failure(
    client, test_db, auth_headers_admin
):
    with patch("backup_tasks.run_backup.delay", side_effect=RuntimeError("queue unavailable")):
        response = client.post(
            "/api/admin/backup/create",
            headers=auth_headers_admin,
        )

    assert response.status_code == 500
    test_db.rollback()
    actions = {
        row[0]
        for row in test_db.query(models.AuditLog.action)
        .filter(
            models.AuditLog.action.in_(
                [AuditAction.BACKUP_ENQUEUE_ATTEMPTED, AuditAction.BACKUP_FAILED]
            )
        )
        .all()
    }
    assert actions == {AuditAction.BACKUP_ENQUEUE_ATTEMPTED, AuditAction.BACKUP_FAILED}


def test_governance_attempt_audit_is_durable_before_service_failure(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    with patch("admin_endpoints.check_reminder_cooldown", return_value=(True, None)), patch(
        "admin_endpoints.send_governance_reminder",
        side_effect=RuntimeError("service unavailable"),
    ):
        with pytest.raises(RuntimeError, match="service unavailable"):
            client.post(
                "/api/admin/governance/reminders",
                headers=auth_headers_admin,
                json={
                    "target_type": "kindergarten",
                    "target_id": sample_kindergarten.id,
                },
            )

    test_db.rollback()
    audit = (
        test_db.query(models.AuditLog)
        .filter(
            models.AuditLog.action == AuditAction.GOVERNANCE_REMINDER_ATTEMPTED,
            models.AuditLog.entity_id == sample_kindergarten.id,
        )
        .one_or_none()
    )
    assert audit is not None
