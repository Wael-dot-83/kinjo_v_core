"""Transaction-boundary coverage for communication and analytics audit events."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

import analytics_service
import communication_service
import models
from audit_actions import AuditAction
from config import settings
from dependencies import get_current_user
from main import app
from routers import manager


def _audit_count(db, action: str) -> int:
    return db.query(models.AuditLog).filter(models.AuditLog.action == action).count()


def _assert_audit_durable(db, action: str) -> models.AuditLog:
    assert _audit_count(db, action) > 0, f"{action} was not flushed"
    db.rollback()
    audits = db.query(models.AuditLog).filter(models.AuditLog.action == action).all()
    assert audits, f"{action} was flushed but not committed"
    return audits[-1]


def _csrf_request(path: str) -> Request:
    token = "audit-transaction-token"
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [
                (b"x-csrf-token", token.encode()),
                (
                    b"cookie",
                    f"{settings.CSRF_COOKIE_NAME}={token}".encode(),
                ),
            ],
            "client": ("127.0.0.1", 12345),
        }
    )


def test_message_view_audit_is_durable_without_message_content(
    client, test_db, admin_user
):
    secret_body = "private-message-body-must-not-enter-audit"
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=admin_user.id,
        recipient_id=admin_user.id,
        subject="Private subject",
        message_body=secret_body,
    )
    test_db.add(message)
    test_db.commit()
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = client.get(f"/comm/messages/{message.id}")

    assert response.status_code == 200, response.text
    audit = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.MESSAGE_VIEWED)
        .one()
    )
    serialized_audit = json.dumps(
        {"details": audit.details, "new_data": audit.new_data},
        default=str,
    )
    assert secret_body not in serialized_audit
    assert "Private subject" not in serialized_audit
    _assert_audit_durable(test_db, AuditAction.MESSAGE_VIEWED)


def test_attachment_download_audit_is_durable(
    monkeypatch, client, test_db, admin_user, tmp_path
):
    attachment_path = tmp_path / "attachment.txt"
    attachment_path.write_text("download payload", encoding="utf-8")
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=admin_user.id,
        recipient_id=admin_user.id,
        subject="Attachment",
        message_body="See the attachment",
    )
    test_db.add(message)
    test_db.flush()
    attachment = models.MessageAttachment(
        message_id=message.id,
        uploaded_by_id=admin_user.id,
        file_name="attachment.txt",
        content_type="text/plain",
        file_size=attachment_path.stat().st_size,
        storage_provider="local",
        storage_key="attachment-key",
    )
    test_db.add(attachment)
    test_db.commit()
    monkeypatch.setattr(
        communication_service,
        "resolve_attachment_path",
        lambda storage_key: attachment_path,
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = client.get(f"/comm/messages/attachments/{attachment.id}")

    assert response.status_code == 200, response.text
    _assert_audit_durable(test_db, AuditAction.MESSAGE_ATTACHMENT_DOWNLOADED)


def test_sync_export_rejection_audit_is_durable(test_db, admin_user):
    payload = analytics_service.ExportRequest(
        report_type="attendance",
        export_format="CSV",
        filters={"period_start": "not-a-date", "period_end": "2026-08-16"},
    )

    with pytest.raises(HTTPException, match="Invalid date format"):
        analytics_service.export_analytics_data(
            request_body=payload,
            current_user=admin_user,
            db=test_db,
            request=_csrf_request("/api/analytics/export/sync"),
        )

    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_SYNC_FAILED)


def test_sync_export_success_audit_is_durable(test_db, admin_user):
    response = analytics_service.export_analytics_data(
        request_body=analytics_service.ExportRequest(
            report_type="attendance",
            export_format="CSV",
            filters={},
        ),
        current_user=admin_user,
        db=test_db,
        request=_csrf_request("/api/analytics/export/sync"),
    )

    assert response.status_code == 200
    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_SYNC)


def test_export_request_rejection_audit_is_durable(test_db, admin_user):
    payload = analytics_service.ExportRequest(
        report_type="overview",
        export_format="DOCX",
        filters={},
    )

    with pytest.raises(HTTPException, match="Unsupported export format"):
        analytics_service.request_export(
            request_body=payload,
            background_tasks=BackgroundTasks(),
            current_user=admin_user,
            db=test_db,
            request=_csrf_request("/api/analytics/export"),
        )

    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_REQUEST_FAILED)


def test_export_request_rolls_back_job_when_success_audit_fails(
    monkeypatch, test_db, admin_user
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(analytics_service, "_log_analytics_export_audit", fail_audit)
    payload = analytics_service.ExportRequest(
        report_type="overview",
        export_format="CSV",
        filters={},
    )

    with pytest.raises(RuntimeError, match="audit insert failed"):
        analytics_service.request_export(
            request_body=payload,
            background_tasks=BackgroundTasks(),
            current_user=admin_user,
            db=test_db,
            request=_csrf_request("/api/analytics/export"),
        )

    test_db.rollback()
    assert test_db.query(models.ExportJob).count() == 0


def test_export_request_and_success_audit_use_one_commit(
    monkeypatch, test_db, admin_user
):
    commits = 0
    original_commit = test_db.commit

    def tracking_commit():
        nonlocal commits
        commits += 1
        return original_commit()

    monkeypatch.setattr(test_db, "commit", tracking_commit)

    result = analytics_service.request_export(
        request_body=analytics_service.ExportRequest(
            report_type="overview",
            export_format="CSV",
            filters={},
        ),
        background_tasks=BackgroundTasks(),
        current_user=admin_user,
        db=test_db,
        request=_csrf_request("/api/analytics/export"),
    )

    assert result.job_id is not None
    assert commits == 1
    test_db.rollback()
    assert test_db.get(models.ExportJob, result.job_id) is not None
    assert _audit_count(test_db, AuditAction.ANALYTICS_EXPORT_REQUESTED) == 1


def test_export_download_audit_is_durable(test_db, admin_user, tmp_path):
    export_path = tmp_path / "analytics.csv"
    export_path.write_text("Metric,Value\nattendance,95\n", encoding="utf-8")
    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=models.ExportStatus.COMPLETED,
        file_path=str(export_path),
        file_size=export_path.stat().st_size,
    )
    test_db.add(job)
    test_db.commit()

    response = analytics_service.download_export_file(
        job_id=job.id,
        current_user=admin_user,
        db=test_db,
    )

    assert response.status_code == 200
    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_DOWNLOADED)


def test_export_worker_completion_and_audit_are_durable(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=models.ExportStatus.PENDING,
    )
    test_db.add(job)
    test_db.flush()
    job_id = job.id
    test_db.commit()
    worker_session = type(test_db)(bind=test_db.bind)
    monkeypatch.setattr(analytics_service, "SessionLocal", lambda: worker_session)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))
    monkeypatch.setattr(
        analytics_service,
        "compute_report_preview",
        lambda *args, **kwargs: SimpleNamespace(
            sample_data=[{"Metric": "attendance", "Value": 95}],
            kpis=[],
        ),
    )

    analytics_service.process_export_job(job_id)

    test_db.expire_all()
    assert test_db.get(models.ExportJob, job_id).status == models.ExportStatus.COMPLETED
    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED)


def test_export_worker_does_not_commit_completion_without_success_audit(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=models.ExportStatus.PENDING,
    )
    test_db.add(job)
    test_db.flush()
    job_id = job.id
    test_db.commit()
    worker_session = type(test_db)(bind=test_db.bind)
    monkeypatch.setattr(analytics_service, "SessionLocal", lambda: worker_session)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))
    monkeypatch.setattr(
        analytics_service,
        "compute_report_preview",
        lambda *args, **kwargs: SimpleNamespace(
            sample_data=[{"Metric": "attendance", "Value": 95}],
            kpis=[],
        ),
    )
    original_audit = analytics_service._log_analytics_export_audit

    def fail_completion_audit(db, *, action, **kwargs):
        if action == AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED:
            raise RuntimeError("completion audit failed")
        return original_audit(db, action=action, **kwargs)

    monkeypatch.setattr(
        analytics_service,
        "_log_analytics_export_audit",
        fail_completion_audit,
    )

    analytics_service.process_export_job(job_id)

    test_db.expire_all()
    persisted_job = test_db.get(models.ExportJob, job_id)
    assert persisted_job.status == models.ExportStatus.FAILED
    assert persisted_job.completed_at is None
    assert _audit_count(test_db, AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED) == 0
    _assert_audit_durable(test_db, AuditAction.ANALYTICS_EXPORT_JOB_FAILED)


def test_manager_audit_helper_delegates_commit_to_caller(
    monkeypatch, test_db, admin_user
):
    commits = 0
    original_commit = test_db.commit

    def tracking_commit():
        nonlocal commits
        commits += 1
        return original_commit()

    monkeypatch.setattr(test_db, "commit", tracking_commit)
    manager._audit(
        test_db,
        admin_user,
        AuditAction.USER_UPDATED,
        "user",
        admin_user.id,
        f"Manager updated user {admin_user.id}",
    )

    assert commits == 0
    assert _audit_count(test_db, AuditAction.USER_UPDATED) == 1
    test_db.commit()
    test_db.rollback()
    assert _audit_count(test_db, AuditAction.USER_UPDATED) == 1
