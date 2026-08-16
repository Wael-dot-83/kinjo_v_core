"""Durability and truthfulness contracts for Admin analytics exports."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

import analytics_service
import export_tasks
import models
from audit_actions import AuditAction
from config import settings


def _job(db, user, *, status=models.ExportStatus.PENDING, started_at=None):
    job = models.ExportJob(
        user_id=user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=status,
        started_at=started_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _worker_session(monkeypatch, test_db):
    session = type(test_db)(bind=test_db.bind)
    monkeypatch.setattr(analytics_service, "SessionLocal", lambda: session)
    return session


def test_export_worker_builder_failure_is_generic_and_audited(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = _job(test_db, admin_user)
    _worker_session(monkeypatch, test_db)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))

    def fail_builder(*args, **kwargs):
        raise RuntimeError("database password is super-secret")

    monkeypatch.setattr(analytics_service, "compute_report_preview", fail_builder)

    result = analytics_service.process_export_job(job.id)

    test_db.expire_all()
    persisted = test_db.get(models.ExportJob, job.id)
    assert result["status"] == "FAILED"
    assert persisted.status == models.ExportStatus.FAILED
    assert persisted.completed_at is None
    assert persisted.error_message.startswith("EXPORT_FAILED:")
    assert "super-secret" not in persisted.error_message
    assert persisted.file_path is None
    assert list(tmp_path.iterdir()) == []
    audit = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_JOB_FAILED)
        .one()
    )
    assert "super-secret" not in (audit.details or "")
    assert "EXPORT_FAILED:" in (audit.details or "")


def test_export_worker_is_idempotent_after_completion(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = _job(test_db, admin_user)
    _worker_session(monkeypatch, test_db)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))
    builds = 0

    def build(*args, **kwargs):
        nonlocal builds
        builds += 1
        return SimpleNamespace(sample_data=[{"Metric": "attendance", "Value": 95}], kpis=[])

    monkeypatch.setattr(analytics_service, "compute_report_preview", build)

    first = analytics_service.process_export_job(job.id)
    second = analytics_service.process_export_job(job.id)

    test_db.expire_all()
    persisted = test_db.get(models.ExportJob, job.id)
    assert first["status"] == "COMPLETED"
    assert second["status"] == "COMPLETED"
    assert builds == 1
    assert persisted.file_path == str(tmp_path / f"overview_{job.id}.csv")
    assert Path(persisted.file_path).is_file()
    assert not list(tmp_path.glob(".*.tmp*"))
    assert (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED)
        .count()
        == 1
    )


def test_completion_audit_failure_removes_prepared_file_and_marks_failed(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = _job(test_db, admin_user)
    _worker_session(monkeypatch, test_db)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))
    monkeypatch.setattr(
        analytics_service,
        "compute_report_preview",
        lambda *args, **kwargs: SimpleNamespace(sample_data=[{"Metric": "x"}], kpis=[]),
    )
    original = analytics_service._log_analytics_export_audit

    def fail_completion(db, *, action, **kwargs):
        if action == AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED:
            raise RuntimeError("audit storage internals")
        return original(db, action=action, **kwargs)

    monkeypatch.setattr(analytics_service, "_log_analytics_export_audit", fail_completion)

    analytics_service.process_export_job(job.id)

    test_db.expire_all()
    persisted = test_db.get(models.ExportJob, job.id)
    assert persisted.status == models.ExportStatus.FAILED
    assert persisted.file_path is None
    assert list(tmp_path.iterdir()) == []
    assert "audit storage internals" not in persisted.error_message


def test_atomic_publish_failure_removes_temporary_artifact(
    monkeypatch, test_db, admin_user, tmp_path
):
    job = _job(test_db, admin_user)
    _worker_session(monkeypatch, test_db)
    monkeypatch.setattr(analytics_service, "EXPORT_DIR", Path(tmp_path))
    monkeypatch.setattr(
        analytics_service,
        "compute_report_preview",
        lambda *args, **kwargs: SimpleNamespace(sample_data=[{"Metric": "x"}], kpis=[]),
    )
    monkeypatch.setattr(
        analytics_service.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("rename failed")),
    )

    analytics_service.process_export_job(job.id)

    test_db.expire_all()
    assert test_db.get(models.ExportJob, job.id).status == models.ExportStatus.FAILED
    assert list(tmp_path.iterdir()) == []


def test_durable_sweeper_recovers_pending_and_stale_processing(
    monkeypatch, test_db, admin_user
):
    pending = _job(test_db, admin_user)
    stale = _job(
        test_db,
        admin_user,
        status=models.ExportStatus.PROCESSING,
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    fresh = _job(
        test_db,
        admin_user,
        status=models.ExportStatus.PROCESSING,
        started_at=datetime.now(timezone.utc),
    )
    worker_session = type(test_db)(bind=test_db.bind)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: worker_session)
    published = []
    monkeypatch.setattr(
        export_tasks.run_analytics_export_job,
        "delay",
        lambda job_id: published.append(job_id),
    )

    result = export_tasks.dispatch_pending_analytics_exports.run()

    test_db.expire_all()
    assert result == {"found": 2, "recovered": 1, "published": 2}
    assert published == [pending.id, stale.id]
    assert test_db.get(models.ExportJob, stale.id).status == models.ExportStatus.PENDING
    assert test_db.get(models.ExportJob, fresh.id).status == models.ExportStatus.PROCESSING


def test_export_status_never_exposes_server_file_path(test_db, admin_user, tmp_path):
    export_path = tmp_path / "private" / "analytics.csv"
    export_path.parent.mkdir()
    export_path.write_bytes(b"Metric,Value\nattendance,95\n")
    job = _job(test_db, admin_user, status=models.ExportStatus.COMPLETED)
    job.file_path = str(export_path)
    job.file_size = export_path.stat().st_size
    test_db.commit()

    result = analytics_service.get_export_status(job.id, admin_user, test_db)

    assert result.file_path == f"/api/analytics/export/{job.id}/file"
    assert str(tmp_path) not in result.file_path


def test_export_status_sanitizes_legacy_internal_error(test_db, admin_user):
    job = _job(test_db, admin_user, status=models.ExportStatus.FAILED)
    job.error_message = "connection refused for postgres://secret@internal-host"
    test_db.commit()

    result = analytics_service.get_export_status(job.id, admin_user, test_db)

    assert result.error == "EXPORT_FAILED"


def test_download_read_failure_does_not_claim_download(
    test_db, admin_user, tmp_path
):
    job = _job(test_db, admin_user, status=models.ExportStatus.COMPLETED)
    job.file_path = str(tmp_path)
    test_db.commit()

    try:
        analytics_service.download_export_file(job.id, admin_user, test_db)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("directory cannot be downloaded as an export file")

    assert (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_DOWNLOADED)
        .count()
        == 0
    )


def test_request_persists_before_durable_dispatch(
    monkeypatch, test_db, admin_user
):
    observed = []

    def observe(job_id):
        test_db.expire_all()
        observed.append(test_db.get(models.ExportJob, job_id).status)

    monkeypatch.setattr(analytics_service, "_enqueue_export_job", observe)
    result = analytics_service.request_export(
        request_body=analytics_service.ExportRequest(
            report_type="overview", export_format="CSV", filters={}
        ),
        background_tasks=BackgroundTasks(),
        current_user=admin_user,
        db=test_db,
        request=SimpleNamespace(
            headers={"x-csrf-token": "token"},
            cookies={settings.CSRF_COOKIE_NAME: "token"},
        ),
    )

    assert observed == [models.ExportStatus.PENDING]
    assert result.status == models.ExportStatus.PENDING.value


def test_broker_publish_failure_leaves_durable_pending_outbox(
    monkeypatch, test_db, admin_user
):
    def broker_unavailable(_job_id):
        raise ConnectionError("broker topology is private")

    monkeypatch.setattr(
        export_tasks.run_analytics_export_job,
        "delay",
        broker_unavailable,
    )

    result = analytics_service.request_export(
        request_body=analytics_service.ExportRequest(
            report_type="overview", export_format="CSV", filters={}
        ),
        background_tasks=BackgroundTasks(),
        current_user=admin_user,
        db=test_db,
        request=SimpleNamespace(
            headers={"x-csrf-token": "token"},
            cookies={settings.CSRF_COOKIE_NAME: "token"},
        ),
    )

    test_db.expire_all()
    assert result.status == models.ExportStatus.PENDING.value
    assert test_db.get(models.ExportJob, result.job_id).status == models.ExportStatus.PENDING
    assert (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_REQUESTED)
        .count()
        == 1
    )


def test_sync_export_does_not_claim_completion_when_row_build_fails(
    monkeypatch, test_db, admin_user, sample_kindergarten
):
    def fail_metric(*args, **kwargs):
        raise RuntimeError("warehouse password super-secret")

    monkeypatch.setattr(
        analytics_service.KPIService,
        "compute_attendance_rate",
        fail_metric,
    )

    with pytest.raises(HTTPException) as exc_info:
        analytics_service.export_analytics_data(
            request_body=analytics_service.ExportRequest(
                report_type="attendance",
                export_format="CSV",
                filters={},
            ),
            current_user=admin_user,
            db=test_db,
            request=SimpleNamespace(
                headers={"x-csrf-token": "token"},
                cookies={settings.CSRF_COOKIE_NAME: "token"},
            ),
        )

    assert exc_info.value.status_code == 500
    assert "super-secret" not in str(exc_info.value.detail)
    assert (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_SYNC)
        .count()
        == 0
    )
    failure = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_SYNC_FAILED)
        .one()
    )
    assert "super-secret" not in (failure.details or "")
    assert "EXPORT_FAILED:" in (failure.details or "")


def test_celery_analytics_worker_tasks_are_registered():
    from celery_app import celery_app

    assert "export_tasks.run_analytics_export_job" in celery_app.tasks
    assert "export_tasks.dispatch_pending_analytics_exports" in celery_app.tasks
