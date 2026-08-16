"""Failure-injection contracts for communication mutation/audit atomicity."""

from datetime import datetime, timezone

import pytest

import communication_service
import models
import notification_service
from audit_actions import AuditAction
from config import settings
from dependencies import get_current_user
from main import app


def _seed_direct_message(db, sender, recipient, *, thread_id=None):
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject="Atomicity probe",
        message_body="Private mutation payload",
        allow_replies=True,
        thread_id=thread_id,
    )
    db.add(message)
    db.commit()
    return message


def _fail_action(monkeypatch, action_to_fail):
    original = communication_service.log_audit_event

    def injected_failure(*args, action, **kwargs):
        if action == action_to_fail:
            raise RuntimeError(f"audit insert failed: {action}")
        return original(*args, action=action, **kwargs)

    monkeypatch.setattr(
        communication_service,
        "log_audit_event",
        injected_failure,
    )


def _override_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_direct_message_rolls_back_when_success_audit_fails(
    monkeypatch, client, test_db, admin_user, parent_user
):
    _override_user(admin_user)
    _fail_action(monkeypatch, AuditAction.MESSAGE_SENT)

    with pytest.raises(RuntimeError, match="MESSAGE_SENT"):
        client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": parent_user.id,
                "subject": "Direct atomicity",
                "message_body": "Must roll back with its audit",
            },
        )

    test_db.rollback()
    assert test_db.query(models.Message).count() == 0


def test_audience_message_and_recipients_roll_back_when_audit_fails(
    monkeypatch, client, test_db, admin_user, parent_user
):
    _override_user(admin_user)
    monkeypatch.setattr(
        communication_service,
        "resolve_recipients",
        lambda **kwargs: [parent_user.id],
    )
    _fail_action(monkeypatch, AuditAction.MESSAGE_ANNOUNCEMENT_SENT)

    with pytest.raises(RuntimeError, match="MESSAGE_ANNOUNCEMENT_SENT"):
        client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Audience atomicity",
                "message_body": "Recipients must roll back too",
                "audience": {"include_roles": ["PARENT"], "scope": "GLOBAL"},
            },
        )

    test_db.rollback()
    assert test_db.query(models.Message).count() == 0
    assert test_db.query(models.MessageRecipient).count() == 0


def test_message_notifications_and_audits_commit_once_before_dispatch(
    monkeypatch, client, test_db, admin_user, parent_user
):
    _override_user(admin_user)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False)
    dispatched = []
    monkeypatch.setattr(
        communication_service,
        "dispatch_message_notification_tasks",
        lambda notifications: dispatched.extend(n.id for n in notifications),
        raising=False,
    )
    commits = 0
    original_commit = test_db.commit

    def tracking_commit():
        nonlocal commits
        commits += 1
        return original_commit()

    monkeypatch.setattr(test_db, "commit", tracking_commit)

    response = client.post(
        "/comm/messages",
        json={
            "mode": "direct",
            "recipient_id": parent_user.id,
            "subject": "Notification atomicity",
            "message_body": "Commit rows before dispatch",
        },
    )

    assert response.status_code == 201, response.text
    assert commits == 1
    message_id = response.json()["id"]
    notification = test_db.query(models.Notification).filter_by(
        message_id=message_id
    ).one()
    assert notification.status == models.NotificationStatus.PENDING
    assert dispatched == [notification.id]
    actions = {
        row.action
        for row in test_db.query(models.AuditLog).filter(
            models.AuditLog.entity_id == message_id
        )
    }
    assert AuditAction.MESSAGE_SENT in actions
    assert AuditAction.MESSAGE_NOTIFICATIONS_QUEUED in actions


def test_caller_owned_dispatch_uses_broker_publish_retries(
    monkeypatch, test_db, admin_user, parent_user
):
    message = _seed_direct_message(test_db, admin_user, parent_user)
    notification = models.Notification(
        user_id=parent_user.id,
        message_id=message.id,
        channel=models.NotificationChannel.EMAIL,
        status=models.NotificationStatus.PENDING,
        payload={"subject": "Retry", "body": "Retry"},
    )
    test_db.add(notification)
    test_db.commit()
    calls = []

    def capture_apply_async(*, args, retry, retry_policy):
        calls.append((args, retry, retry_policy))

    monkeypatch.setattr(
        notification_service.send_email_notification,
        "apply_async",
        capture_apply_async,
    )

    notification_service.dispatch_message_notification_tasks([notification])

    assert calls == [
        (
            [notification.id],
            True,
            {
                "max_retries": 3,
                "interval_start": 0,
                "interval_step": 0.5,
                "interval_max": 1,
            },
        )
    ]


def test_notification_audit_failure_rolls_back_message_and_notification(
    monkeypatch, client, test_db, admin_user, parent_user
):
    _override_user(admin_user)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False)
    dispatched = []
    monkeypatch.setattr(
        communication_service,
        "dispatch_message_notification_tasks",
        lambda notifications: dispatched.extend(notifications),
        raising=False,
    )
    _fail_action(monkeypatch, AuditAction.MESSAGE_NOTIFICATIONS_QUEUED)

    with pytest.raises(RuntimeError, match="MESSAGE_NOTIFICATIONS_QUEUED"):
        client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": parent_user.id,
                "subject": "Notification audit failure",
                "message_body": "Nothing may be partially committed",
            },
        )

    test_db.rollback()
    assert test_db.query(models.Message).count() == 0
    assert test_db.query(models.Notification).count() == 0
    assert dispatched == []


def test_dispatch_failure_preserves_committed_pending_notification(
    monkeypatch, client, test_db, admin_user, parent_user
):
    _override_user(admin_user)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False)

    def dispatch_failure(notifications):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(
        communication_service,
        "dispatch_message_notification_tasks",
        dispatch_failure,
        raising=False,
    )

    response = client.post(
        "/comm/messages",
        json={
            "mode": "direct",
            "recipient_id": parent_user.id,
            "subject": "Retryable dispatch",
            "message_body": "The pending row is the retry record",
        },
    )

    assert response.status_code == 201, response.text
    message_id = response.json()["id"]
    test_db.rollback()
    notification = test_db.query(models.Notification).filter_by(
        message_id=message_id
    ).one()
    assert notification.status == models.NotificationStatus.PENDING
    assert notification.error_message == (
        "Dispatch scheduling failed (RuntimeError); pending retry"
    )
    assert (
        test_db.query(models.AuditLog)
        .filter_by(action=AuditAction.MESSAGE_NOTIFICATIONS_QUEUED)
        .count()
        == 1
    )


@pytest.mark.parametrize(
    ("method", "path_suffix", "action"),
    [
        ("post", "/read", AuditAction.MESSAGE_READ),
        ("delete", "", AuditAction.MESSAGE_DELETED),
        ("post", "/archive", AuditAction.MESSAGE_ARCHIVED),
    ],
)
def test_message_state_mutation_rolls_back_when_audit_fails(
    monkeypatch,
    client,
    test_db,
    admin_user,
    parent_user,
    method,
    path_suffix,
    action,
):
    message = _seed_direct_message(test_db, admin_user, parent_user)
    message_id = message.id
    _override_user(parent_user)
    _fail_action(monkeypatch, action)

    with pytest.raises(RuntimeError, match=action):
        getattr(client, method)(f"/comm/messages/{message_id}{path_suffix}")

    test_db.rollback()
    assert (
        test_db.query(models.MessageUserState)
        .filter_by(message_id=message_id, user_id=parent_user.id)
        .count()
        == 0
    )


def test_unarchive_rolls_back_to_previous_timestamp_when_audit_fails(
    monkeypatch, client, test_db, admin_user, parent_user
):
    message = _seed_direct_message(test_db, admin_user, parent_user)
    archived_at = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    state = models.MessageUserState(
        message_id=message.id,
        user_id=parent_user.id,
        archived_at=archived_at,
    )
    test_db.add(state)
    test_db.commit()
    message_id = message.id
    _override_user(parent_user)
    _fail_action(monkeypatch, AuditAction.MESSAGE_UNARCHIVED)

    with pytest.raises(RuntimeError, match="MESSAGE_UNARCHIVED"):
        client.post(f"/comm/messages/{message_id}/unarchive")

    test_db.rollback()
    restored = test_db.query(models.MessageUserState).filter_by(
        message_id=message_id,
        user_id=parent_user.id,
    ).one()
    assert restored.archived_at == archived_at


def test_bulk_state_changes_roll_back_when_audit_fails(
    monkeypatch, client, test_db, admin_user, parent_user
):
    first = _seed_direct_message(test_db, admin_user, parent_user)
    second = _seed_direct_message(test_db, admin_user, parent_user)
    message_ids = [first.id, second.id]
    _override_user(parent_user)
    _fail_action(monkeypatch, "MESSAGE_BULK_ARCHIVE")

    with pytest.raises(RuntimeError, match="MESSAGE_BULK_ARCHIVE"):
        client.post(
            "/comm/messages/bulk",
            json={"message_ids": message_ids, "action": "archive"},
        )

    test_db.rollback()
    assert (
        test_db.query(models.MessageUserState)
        .filter(models.MessageUserState.message_id.in_(message_ids))
        .count()
        == 0
    )


def test_reply_and_parent_thread_change_roll_back_when_audit_fails(
    monkeypatch,
    client,
    test_db,
    manager_user,
    parent_user,
    parent_enrollment,
):
    parent_message = _seed_direct_message(test_db, manager_user, parent_user)
    parent_id = parent_message.id
    _override_user(parent_user)
    _fail_action(monkeypatch, AuditAction.MESSAGE_REPLIED)

    with pytest.raises(RuntimeError, match="MESSAGE_REPLIED"):
        client.post(
            f"/comm/messages/{parent_id}/replies",
            json={"message_body": "Atomic reply"},
        )

    test_db.rollback()
    assert test_db.query(models.Message).count() == 1
    assert test_db.get(models.Message, parent_id).thread_id is None


def test_attachment_row_rolls_back_when_audit_fails(
    monkeypatch, client, test_db, admin_user, tmp_path
):
    message = _seed_direct_message(test_db, admin_user, admin_user)
    message_id = message.id
    _override_user(admin_user)
    saved_blob = tmp_path / "atomicity-probe.txt"
    saved_blob.write_bytes(b"payload")
    monkeypatch.setattr(
        communication_service,
        "save_attachment",
        lambda file: ("local", "atomicity-probe.txt", 7),
    )
    monkeypatch.setattr(
        communication_service,
        "resolve_attachment_path",
        lambda storage_key: saved_blob,
    )
    _fail_action(monkeypatch, AuditAction.MESSAGE_ATTACHMENT_ADDED)

    with pytest.raises(RuntimeError, match="MESSAGE_ATTACHMENT_ADDED"):
        client.post(
            f"/comm/messages/{message_id}/attachments",
            files={"file": ("probe.txt", b"payload", "text/plain")},
        )

    test_db.rollback()
    assert test_db.query(models.MessageAttachment).count() == 0
    assert not saved_blob.exists()


def test_attachment_compensation_failure_is_observable(
    monkeypatch, caplog, client, test_db, admin_user
):
    message = _seed_direct_message(test_db, admin_user, admin_user)
    _override_user(admin_user)
    monkeypatch.setattr(
        communication_service,
        "save_attachment",
        lambda file: ("s3", "message-attachments/atomicity-probe.txt", 7),
    )

    def cleanup_failure(storage_provider, storage_key):
        raise RuntimeError("object store unavailable")

    monkeypatch.setattr(
        communication_service,
        "_delete_uncommitted_attachment",
        cleanup_failure,
    )
    _fail_action(monkeypatch, AuditAction.MESSAGE_ATTACHMENT_ADDED)

    with pytest.raises(RuntimeError, match="MESSAGE_ATTACHMENT_ADDED"):
        client.post(
            f"/comm/messages/{message.id}/attachments",
            files={"file": ("probe.txt", b"payload", "text/plain")},
        )

    test_db.rollback()
    assert test_db.query(models.MessageAttachment).count() == 0
    assert "Attachment compensation failed provider=s3" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


def test_notification_helper_default_contract_still_commits_and_dispatches(
    monkeypatch, test_db, admin_user, parent_user
):
    message = _seed_direct_message(test_db, admin_user, parent_user)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False)
    dispatched = []
    monkeypatch.setattr(
        notification_service,
        "_queue_notification_tasks",
        lambda notifications: dispatched.extend(n.id for n in notifications),
    )

    result = notification_service.create_message_notifications(
        test_db,
        message,
        [parent_user],
    )

    assert result is True
    test_db.rollback()
    notification = test_db.query(models.Notification).filter_by(
        message_id=message.id
    ).one()
    assert dispatched == [notification.id]
