"""Production contracts for notification delivery and audience filtering."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

import communication_service
import messaging_permissions
import models
import notification_service
import notification_tasks
from audit_actions import AuditAction
from dependencies import get_current_user
from main import app


def _stale_notification(test_db, user_id, *, channel=models.NotificationChannel.EMAIL):
    row = models.Notification(
        user_id=user_id,
        channel=channel,
        status=models.NotificationStatus.PENDING,
        payload={"subject": "Retry", "body": "Retry body"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    test_db.add(row)
    test_db.commit()
    test_db.refresh(row)
    return row


def _worker_session_factory(test_db):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_db.get_bind())


def _request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def _add_supervisor(test_db, kindergarten, suffix: str):
    user = models.User(
        username=f"filter-supervisor-{suffix}",
        email=f"filter-supervisor-{suffix}@example.test",
        hashed_password="not-used",
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten.id,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _add_kindergarten(test_db, suffix: str):
    row = models.Kindergarten(
        name_ar=f"حضانة {suffix}",
        name_en=f"Nursery {suffix}",
        license_number=f"FILTER-{suffix}",
        governorate="Irbid",
        district="Irbid",
        area="Center",
        address_line="Test address",
        contact_phone="+962790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(row)
    test_db.commit()
    test_db.refresh(row)
    return row


def test_fresh_celery_loader_registers_notification_tasks():
    env = os.environ.copy()
    env["TESTING"] = "true"
    script = (
        "from celery_app import celery_app; "
        "celery_app.loader.import_default_modules(); "
        "required={'notification_tasks.send_email_notification',"
        "'notification_tasks.send_push_notification',"
        "'notification_tasks.redispatch_stale_pending_notifications'}; "
        "missing=required-set(celery_app.tasks); "
        "assert not missing, missing"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_broker_failure_is_persisted_then_stale_retry_is_republished(
    monkeypatch, test_db, parent_user
):
    notification = _stale_notification(test_db, parent_user.id)

    def broker_down(**_kwargs):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(notification_tasks.send_email_notification, "apply_async", broker_down)
    with pytest.raises(ConnectionError, match="broker unavailable"):
        notification_service.dispatch_message_notification_tasks([notification])
    test_db.refresh(notification)
    assert notification.status == models.NotificationStatus.PENDING
    assert notification.delivery_attempts == 0

    assert notification_tasks.redispatch_stale_pending_notifications_now(
        db=test_db,
        stale_after_seconds=0,
    ) == 0

    test_db.refresh(notification)
    assert notification.status == models.NotificationStatus.PENDING
    assert notification.delivery_attempts == 1
    assert notification.next_retry_at is not None
    assert "ConnectionError" in notification.error_message
    assert notification.dispatch_claim_token is None

    notification.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    test_db.commit()
    published = []
    monkeypatch.setattr(
        notification_tasks.send_email_notification,
        "apply_async",
        lambda **kwargs: published.append(kwargs),
    )

    assert notification_tasks.redispatch_stale_pending_notifications_now(
        db=test_db,
        stale_after_seconds=0,
    ) == 1
    test_db.refresh(notification)
    assert notification.delivery_attempts == 2
    assert published[0]["args"] == [notification.id, notification.dispatch_claim_token]


def test_broker_retry_budget_is_finite(monkeypatch, test_db, parent_user):
    notification = _stale_notification(test_db, parent_user.id)
    monkeypatch.setattr(
        notification_tasks.send_email_notification,
        "apply_async",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("broker down")),
    )

    for attempt in range(1, notification_tasks.MAX_NOTIFICATION_DELIVERY_ATTEMPTS + 1):
        notification.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        test_db.commit()
        assert notification_tasks.redispatch_stale_pending_notifications_now(
            db=test_db,
            stale_after_seconds=0,
        ) == 0
        test_db.refresh(notification)
        assert notification.delivery_attempts == attempt

    assert notification.status == models.NotificationStatus.FAILED
    assert notification.next_retry_at is None
    assert "exhausted" in notification.error_message


def test_delivery_claim_prevents_duplicate_successful_send(
    monkeypatch, test_db, parent_user
):
    notification = _stale_notification(test_db, parent_user.id)
    sends = []
    monkeypatch.setattr(notification_tasks.settings, "NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(notification_tasks, "_send_email", lambda *args: sends.append(args))
    monkeypatch.setattr(
        notification_tasks,
        "SessionLocal",
        _worker_session_factory(test_db),
    )

    notification_tasks.send_email_notification.run(notification.id)
    notification_tasks.send_email_notification.run(notification.id)

    test_db.expire_all()
    stored = test_db.get(models.Notification, notification.id)
    assert stored.status == models.NotificationStatus.SENT
    assert stored.delivery_attempts == 1
    assert len(sends) == 1


def test_retry_sweep_never_exceeds_fixed_batch_bound(
    monkeypatch, test_db, parent_user
):
    for _ in range(notification_tasks.NOTIFICATION_RETRY_BATCH_SIZE + 5):
        test_db.add(
            models.Notification(
                user_id=parent_user.id,
                channel=models.NotificationChannel.EMAIL,
                status=models.NotificationStatus.PENDING,
                payload={"subject": "Batch", "body": "Batch"},
                created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
        )
    test_db.commit()
    published = []
    monkeypatch.setattr(
        notification_tasks.send_email_notification,
        "apply_async",
        lambda **kwargs: published.append(kwargs),
    )

    count = notification_tasks.redispatch_stale_pending_notifications_now(
        db=test_db,
        batch_size=10_000,
        stale_after_seconds=0,
    )

    assert count == notification_tasks.NOTIFICATION_RETRY_BATCH_SIZE
    assert len(published) == notification_tasks.NOTIFICATION_RETRY_BATCH_SIZE
    assert test_db.query(models.Notification).filter(
        models.Notification.delivery_attempts == 1
    ).count() == notification_tasks.NOTIFICATION_RETRY_BATCH_SIZE


def test_kindergarten_filter_cannot_over_broadcast(
    test_db, admin_user, sample_kindergarten
):
    other_kindergarten = _add_kindergarten(test_db, "other")
    expected = _add_supervisor(test_db, sample_kindergarten, "expected")
    _add_supervisor(test_db, other_kindergarten, "excluded")
    audience = messaging_permissions.AudienceDefinition(
        include_roles=["SUPERVISOR"],
        scope="CUSTOM",
        filters=[
            messaging_permissions.FilterClause(
                field="kindergarten.id",
                op=messaging_permissions.FilterOperator.EQ,
                value=sample_kindergarten.id,
            )
        ],
    )

    assert messaging_permissions.resolve_recipients(test_db, audience, admin_user) == {
        expected.id
    }


@pytest.mark.parametrize(
    ("field", "op", "value"),
    [
        ("kindergarten.city", "EQ", "Amman"),
        ("kindergarten.id", "LIKE", "%1%"),
        ("kindergarten.id", "IN", []),
    ],
)
def test_unsupported_or_invalid_filters_are_rejected(
    test_db, admin_user, field, op, value
):
    audience = messaging_permissions.AudienceDefinition(
        include_roles=["SUPERVISOR"],
        scope="CUSTOM",
        filters=[messaging_permissions.FilterClause(field=field, op=op, value=value)],
    )
    with pytest.raises(HTTPException) as exc_info:
        messaging_permissions.resolve_recipients(test_db, audience, admin_user)
    assert exc_info.value.status_code == 400


def test_preview_and_send_persist_the_identical_recipient_set(
    monkeypatch, test_db, admin_user, sample_kindergarten
):
    other_kindergarten = _add_kindergarten(test_db, "preview-other")
    expected = _add_supervisor(test_db, sample_kindergarten, "preview-expected")
    _add_supervisor(test_db, other_kindergarten, "preview-excluded")
    audience_data = {
        "include_roles": ["SUPERVISOR"],
        "scope": "CUSTOM",
        "filters": [
            {
                "field": "kindergarten.id",
                "op": "EQ",
                "value": sample_kindergarten.id,
            }
        ],
    }
    audience = communication_service.AudienceDefinition(**audience_data)
    preview = communication_service.preview_audience(
        request=_request("/comm/audience/preview"),
        audience=audience,
        current_user=admin_user,
        db=test_db,
    )
    monkeypatch.setattr(communication_service.settings, "TESTING", True)
    result = communication_service.send_message(
        request=_request("/comm/messages"),
        msg_data=communication_service.MessageCreate(
            mode="audience",
            subject="Equivalent audience",
            message_body="Preview and send must agree",
            audience=audience,
        ),
        current_user=admin_user,
        db=test_db,
    )
    stored_ids = {
        row[0]
        for row in test_db.query(models.MessageRecipient.recipient_user_id).filter(
            models.MessageRecipient.message_id == result.id
        ).all()
    }
    assert preview.total_count == 1
    assert {recipient.id for recipient in preview.recipients} == {expected.id}
    assert stored_ids == {expected.id}


def test_notification_retry_model_and_migration_contract():
    column_names = set(models.Notification.__table__.columns.keys())
    assert {
        "delivery_attempts",
        "last_attempt_at",
        "next_retry_at",
        "dispatch_claimed_at",
        "dispatch_claim_token",
    } <= column_names
    assert "ix_notifications_retry_due" in {
        index.name for index in models.Notification.__table__.indexes
    }
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "notif_delivery_retry_01.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "ncfa_snap_01"' in migration
    assert "def upgrade()" in migration
    assert "def downgrade()" in migration


def _seed_attachment(test_db, admin_user, *, provider: str, storage_key: str):
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=admin_user.id,
        recipient_id=admin_user.id,
        subject="Attachment",
        message_body="Attachment",
    )
    test_db.add(message)
    test_db.flush()
    attachment = models.MessageAttachment(
        message_id=message.id,
        uploaded_by_id=admin_user.id,
        file_name="missing.txt",
        content_type="text/plain",
        file_size=1,
        storage_provider=provider,
        storage_key=storage_key,
    )
    test_db.add(attachment)
    test_db.commit()
    return attachment


def test_missing_local_attachment_records_no_download_success_audit(
    monkeypatch, client, test_db, admin_user, tmp_path
):
    attachment = _seed_attachment(
        test_db,
        admin_user,
        provider="local",
        storage_key="missing",
    )
    monkeypatch.setattr(
        communication_service,
        "resolve_attachment_path",
        lambda _key: tmp_path / "does-not-exist.txt",
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = client.get(f"/comm/messages/attachments/{attachment.id}")

    assert response.status_code == 404
    assert test_db.query(models.AuditLog).filter(
        models.AuditLog.action.in_(
            [
                AuditAction.MESSAGE_ATTACHMENT_DOWNLOADED,
                AuditAction.MESSAGE_ATTACHMENT_ACCESS_AUTHORIZED,
            ]
        )
    ).count() == 0


def test_s3_presign_failure_records_no_download_success_audit(
    monkeypatch, test_db, admin_user
):
    attachment = _seed_attachment(
        test_db,
        admin_user,
        provider="s3",
        storage_key="unavailable",
    )

    class BrokenClient:
        def generate_presigned_url(self, *_args, **_kwargs):
            raise RuntimeError("presign unavailable")

    class FakeSession:
        def __init__(self, **_kwargs):
            pass

        def client(self, *_args, **_kwargs):
            return BrokenClient()

    import boto3

    monkeypatch.setattr(boto3.session, "Session", FakeSession)
    with pytest.raises(RuntimeError, match="presign unavailable"):
        communication_service.download_message_attachment(
            request=_request(
                f"/comm/messages/attachments/{attachment.id}",
                method="GET",
            ),
            attachment_id=attachment.id,
            current_user=admin_user,
            db=test_db,
        )
    assert test_db.query(models.AuditLog).filter(
        models.AuditLog.action.in_(
            [
                AuditAction.MESSAGE_ATTACHMENT_DOWNLOADED,
                AuditAction.MESSAGE_ATTACHMENT_ACCESS_AUTHORIZED,
            ]
        )
    ).count() == 0
