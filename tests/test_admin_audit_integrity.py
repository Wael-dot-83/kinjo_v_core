"""Regression coverage for Admin audit durability and transaction atomicity."""

from datetime import date

import pytest
from starlette.requests import Request

import audit_service
import charts_api
import classification_service
import models
from admin_security import APIError
from audit_actions import AuditAction
from config import settings
from heatmap.backend import admin_router as heatmap_admin
from heatmap.backend import pipeline as heatmap_pipeline


def _original(function):
    """Strip route/rate-limit wrappers for transaction-focused unit tests."""
    while hasattr(function, "__wrapped__"):
        function = function.__wrapped__
    return function


def _request(path: str = "/", *, csrf: bool = False) -> Request:
    headers = []
    if csrf:
        headers = [
            (b"x-csrf-token", b"audit-integrity-token"),
            (
                b"cookie",
                f"{settings.CSRF_COOKIE_NAME}=audit-integrity-token".encode(),
            ),
        ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers,
            "client": ("127.0.0.1", 12345),
        }
    )


def _count_commits(monkeypatch, db):
    commits = 0
    original_commit = db.commit

    def tracking_commit():
        nonlocal commits
        commits += 1
        return original_commit()

    monkeypatch.setattr(db, "commit", tracking_commit)
    return lambda: commits


def _audit_count(db, action: str) -> int:
    return db.query(models.AuditLog).filter(models.AuditLog.action == action).count()


def test_audit_log_export_event_is_durable(test_db, admin_user):
    response = audit_service._export_audit_logs(
        format="json",
        period="all",
        action=None,
        entity_type=None,
        user=None,
        date=None,
        current_user=admin_user,
        db=test_db,
    )

    assert response.status_code == 200
    test_db.rollback()
    assert _audit_count(test_db, AuditAction.AUDIT_LOG_EXPORT) == 1


def test_scheduled_export_create_and_audit_use_one_commit(
    monkeypatch, test_db, admin_user
):
    commit_count = _count_commits(monkeypatch, test_db)
    payload = charts_api.ScheduledExportIn(
        source="attendance",
        recipient_email="schedule@example.com",
    )

    result = _original(charts_api.create_scheduled_export)(
        request=_request("/api/admin/charts/scheduled-exports"),
        payload=payload,
        db=test_db,
        current_user=admin_user,
    )

    assert result["id"]
    assert commit_count() == 1
    test_db.rollback()
    assert test_db.query(models.ScheduledChartExport).count() == 1
    assert _audit_count(test_db, AuditAction.SCHEDULED_EXPORT_CREATED) == 1
    audit = test_db.query(models.AuditLog).filter_by(
        action=AuditAction.SCHEDULED_EXPORT_CREATED
    ).one()
    assert "schedule@example.com" not in (audit.details or "")


def test_scheduled_export_create_rolls_back_when_audit_fails(
    monkeypatch, test_db, admin_user
):
    payload = charts_api.ScheduledExportIn(
        source="attendance",
        recipient_email="schedule@example.com",
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(charts_api, "log_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit insert failed"):
        _original(charts_api.create_scheduled_export)(
            request=_request("/api/admin/charts/scheduled-exports"),
            payload=payload,
            db=test_db,
            current_user=admin_user,
        )

    test_db.rollback()
    assert test_db.query(models.ScheduledChartExport).count() == 0


def test_scheduled_export_delete_rolls_back_when_audit_fails(
    monkeypatch, test_db, admin_user
):
    schedule = models.ScheduledChartExport(
        user_id=admin_user.id,
        source="attendance",
        recipient_email="schedule@example.com",
        frequency="WEEKLY",
        export_format="CSV",
        hour_utc=6,
    )
    test_db.add(schedule)
    test_db.commit()
    schedule_id = schedule.id

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(charts_api, "log_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit insert failed"):
        _original(charts_api.delete_scheduled_export)(
            request=_request(f"/api/admin/charts/scheduled-exports/{schedule_id}"),
            schedule_id=schedule_id,
            db=test_db,
            current_user=admin_user,
        )

    test_db.rollback()
    assert test_db.get(models.ScheduledChartExport, schedule_id) is not None


@pytest.mark.parametrize(
    ("endpoint_name", "action"),
    [
        ("warm_admin_classification_cache", AuditAction.CLASSIFICATION_CACHE_WARM),
        (
            "invalidate_admin_classification_cache",
            AuditAction.CLASSIFICATION_CACHE_INVALIDATE,
        ),
    ],
)
def test_classification_cache_audits_are_durable(
    monkeypatch, test_db, admin_user, endpoint_name, action
):
    monkeypatch.setattr(
        classification_service.BenchmarkingService,
        "_get_kindergarten_scope",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        classification_service.dashboard_cache,
        "clear_prefix",
        lambda prefix: 3,
    )

    endpoint = _original(getattr(classification_service, endpoint_name))
    kwargs = {
        "request": _request(f"/api/admin/classification/cache/{endpoint_name}"),
        "db": test_db,
        "current_user": admin_user,
    }
    if endpoint_name == "warm_admin_classification_cache":
        kwargs.update(period_start=None, period_end=None)
    endpoint(**kwargs)

    test_db.rollback()
    assert _audit_count(test_db, action) == 1


def test_heatmap_alert_acknowledgement_and_audit_use_one_commit(
    monkeypatch, test_db, admin_user
):
    alert = models.MapAlertHistory(
        snapshot_date=date(2026, 8, 16),
        governorate_code="JO-AM",
        sub_indicator="incident_rate",
        rule="high_incident_rate",
        severity="high",
        message="threshold exceeded",
    )
    test_db.add(alert)
    test_db.commit()
    alert_id = alert.id
    commit_count = _count_commits(monkeypatch, test_db)

    result = _original(heatmap_admin.acknowledge_alert)(
        request=_request(
            f"/api/admin/heat-map/alerts/{alert_id}/acknowledge",
            csrf=True,
        ),
        alert_id=alert_id,
        current_user=admin_user,
        db=test_db,
    )

    assert result["status"] == "acknowledged"
    assert commit_count() == 1
    test_db.rollback()
    assert test_db.get(models.MapAlertHistory, alert_id).acknowledged_by == admin_user.id
    assert _audit_count(test_db, AuditAction.ALERT_ACKNOWLEDGED) == 1


def test_heatmap_alert_acknowledgement_rolls_back_when_audit_fails(
    monkeypatch, test_db, admin_user
):
    alert = models.MapAlertHistory(
        snapshot_date=date(2026, 8, 16),
        governorate_code="JO-IR",
        sub_indicator="incident_rate",
        rule="high_incident_rate",
        severity="high",
        message="threshold exceeded",
    )
    test_db.add(alert)
    test_db.commit()
    alert_id = alert.id

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(heatmap_admin, "log_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit insert failed"):
        _original(heatmap_admin.acknowledge_alert)(
            request=_request(
                f"/api/admin/heat-map/alerts/{alert_id}/acknowledge",
                csrf=True,
            ),
            alert_id=alert_id,
            current_user=admin_user,
            db=test_db,
        )

    test_db.rollback()
    restored = test_db.get(models.MapAlertHistory, alert_id)
    assert restored.acknowledged_at is None
    assert restored.acknowledged_by is None


def test_heatmap_refresh_and_actor_audit_use_one_final_commit(
    monkeypatch, test_db, admin_user
):
    monkeypatch.setattr(
        heatmap_admin.heatmap_service,
        "load_jordan_geojson",
        lambda **kwargs: {},
    )

    def stage_pipeline(db, snapshot_date=None, commit=True):
        assert commit is False
        run = models.MapDailyRunLog(run_id="audit-refresh-run", status="success")
        db.add(run)
        db.flush()
        return {
            "status": "success",
            "run_id": run.run_id,
            "snapshot_date": "2026-08-16",
            "governorates": 12,
            "rows_processed": 336,
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(heatmap_pipeline, "run_daily_pipeline", stage_pipeline)
    commit_count = _count_commits(monkeypatch, test_db)

    result = _original(heatmap_admin.refresh_heat_map)(
        request=_request("/api/admin/heat-map/refresh", csrf=True),
        snapshot_date=None,
        current_user=admin_user,
        db=test_db,
    )

    assert result["status"] == "success"
    assert commit_count() == 1
    test_db.rollback()
    assert test_db.query(models.MapDailyRunLog).filter_by(
        run_id="audit-refresh-run"
    ).count() == 1
    audit = test_db.query(models.AuditLog).filter_by(
        action=AuditAction.HEATMAP_DATASET_REGENERATED
    ).one()
    assert audit.user_id == admin_user.id


def test_heatmap_refresh_failure_redacts_internal_exception(
    monkeypatch, test_db, admin_user
):
    monkeypatch.setattr(
        heatmap_admin.heatmap_service,
        "load_jordan_geojson",
        lambda **kwargs: {},
    )

    def fail_pipeline(*args, **kwargs):
        raise RuntimeError("postgresql://operator:secret@internal-db/kinjo")

    monkeypatch.setattr(heatmap_pipeline, "run_daily_pipeline", fail_pipeline)

    with pytest.raises(APIError) as caught:
        _original(heatmap_admin.refresh_heat_map)(
            request=_request("/api/admin/heat-map/refresh", csrf=True),
            snapshot_date=None,
            current_user=admin_user,
            db=test_db,
        )

    error = caught.value
    assert error.status_code == 500
    assert error.details is None
    assert "secret" not in error.detail


def test_heatmap_refresh_summary_redacts_pipeline_issues(
    monkeypatch, test_db, admin_user
):
    secret = "postgresql://operator:secret@internal-db/kinjo"
    monkeypatch.setattr(
        heatmap_admin.heatmap_service,
        "load_jordan_geojson",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        heatmap_pipeline,
        "run_daily_pipeline",
        lambda *args, **kwargs: {
            "status": "failed",
            "run_id": "redacted-refresh-run",
            "snapshot_date": "2026-08-16",
            "governorates": 0,
            "rows_processed": 0,
            "errors": [{"step": "pipeline", "error": secret, "tb": secret}],
            "warnings": [{"step": "database", "error": secret}],
        },
    )

    result = _original(heatmap_admin.refresh_heat_map)(
        request=_request("/api/admin/heat-map/refresh", csrf=True),
        snapshot_date=None,
        current_user=admin_user,
        db=test_db,
    )

    assert secret not in str(result)
    assert result["errors"][0]["step"] == "pipeline"
    assert result["warnings"][0]["step"] == "database"


def test_heatmap_run_history_redacts_persisted_exception_text(test_db, admin_user):
    secret = "postgresql://operator:secret@internal-db/kinjo"
    test_db.add(
        models.MapDailyRunLog(
            run_id="redacted-history-run",
            status="failed",
            errors=[{"step": "pipeline", "error": secret, "tb": secret}],
            warnings=[{"step": "database", "error": secret}],
        )
    )
    test_db.commit()

    result = _original(heatmap_admin.list_runs)(
        request=_request("/api/admin/heat-map/runs"),
        limit=20,
        current_user=admin_user,
        db=test_db,
    )

    assert secret not in str(result)
    assert result["runs"][0]["errors"][0]["step"] == "pipeline"
    assert result["runs"][0]["warnings"][0]["step"] == "database"


def test_pipeline_commit_false_never_commits_its_partial_work(
    monkeypatch, test_db
):
    commit_count = _count_commits(monkeypatch, test_db)

    summary = heatmap_pipeline.run_daily_pipeline(
        test_db,
        snapshot_date=date(2026, 8, 16),
        commit=False,
    )

    assert summary["status"] == "success"
    assert commit_count() == 0
    assert test_db.query(models.MapDailyRunLog).count() == 1
    test_db.rollback()
    assert test_db.query(models.MapDailyRunLog).count() == 0
