from datetime import date, timedelta

import pytest

import analytics_service
import models
from audit_actions import AuditAction
from conftest import csrf_pair
from dependencies import get_current_user
from main import app
from conftest import csrf_pair

pytestmark = [pytest.mark.integration, pytest.mark.p1]


@pytest.fixture
def auth_user():
    def _set(user):
        app.dependency_overrides[get_current_user] = lambda: user

    yield _set
    app.dependency_overrides.clear()


@pytest.fixture
def stub_process_export_job(monkeypatch):
    monkeypatch.setattr(analytics_service, "process_export_job", lambda job_id: None)


def _date_filters():
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
    }


def test_export_sync_admin_csv(client, admin_user, auth_user, sample_kindergarten, test_db):
    auth_user(admin_user)
    payload = {
        "report_type": "attendance",
        "export_format": "CSV",
        "filters": _date_filters(),
    }
    response = client.post("/api/analytics/export/sync", json=payload, headers=csrf_pair())
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")
    assert "Content-Disposition" in response.headers

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_SYNC)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id


def test_export_async_request_admin(client, admin_user, auth_user, stub_process_export_job, test_db):
    auth_user(admin_user)
    payload = {
        "report_type": "overview",
        "export_format": "CSV",
        "filters": {},
    }
    response = client.post("/api/analytics/export", json=payload, headers=csrf_pair())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == models.ExportStatus.PENDING.value
    assert "job_id" in data

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_REQUESTED)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.entity_id == data["job_id"]


def test_export_async_request_invalid_format_logs_failure(client, admin_user, auth_user, test_db):
    auth_user(admin_user)
    payload = {
        "report_type": "overview",
        "export_format": "DOCX",
        "filters": {},
    }
    response = client.post("/api/analytics/export", json=payload, headers=csrf_pair())
    assert response.status_code == 400

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_REQUEST_FAILED)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id


def test_export_status_for_owner(client, admin_user, auth_user, test_db):
    auth_user(admin_user)
    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=models.ExportStatus.PENDING,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)

    response = client.get(f"/api/analytics/export/{job.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job.id
    assert data["status"] == models.ExportStatus.PENDING.value


def test_export_file_missing_returns_404(client, admin_user, auth_user, test_db):
    auth_user(admin_user)
    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters={},
        status=models.ExportStatus.COMPLETED,
        file_path="data/exports/missing_export.csv",
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)

    response = client.get(f"/api/analytics/export/{job.id}/file")
    assert response.status_code == 404


def test_export_sync_invalid_date_logs_failure(client, admin_user, auth_user, sample_kindergarten, test_db):
    auth_user(admin_user)
    payload = {
        "report_type": "attendance",
        "export_format": "CSV",
        "filters": {
            "period_start": "2026-13-01",
            "period_end": "2026-01-31",
        },
    }
    response = client.post("/api/analytics/export/sync", json=payload, headers=csrf_pair())
    assert response.status_code == 400

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_SYNC_FAILED)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id


def test_export_file_download_logs_audit(client, admin_user, auth_user, test_db, tmp_path):
    auth_user(admin_user)
    export_file = tmp_path / "analytics_export.csv"
    export_file.write_text("Metric,Value\nattendance,95\n", encoding="utf-8")

    job = models.ExportJob(
        user_id=admin_user.id,
        export_format=models.ExportFormat.CSV,
        report_type="overview",
        filters=_date_filters(),
        status=models.ExportStatus.COMPLETED,
        file_path=str(export_file),
        file_size=export_file.stat().st_size,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)

    response = client.get(f"/api/analytics/export/{job.id}/file")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")
    assert "Content-Disposition" in response.headers

    audit_log = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.ANALYTICS_EXPORT_DOWNLOADED)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.entity_id == job.id
