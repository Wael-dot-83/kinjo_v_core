"""Service-level tests for realtime dashboard and predictive analytics."""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from data_quality_service import data_quality_service
from predictive_analytics import ModelType, predictive_analytics


@pytest.mark.asyncio
async def test_realtime_dashboard_data_is_db_backed(
    test_db,
    manager_user,
    sample_class,
    sample_child,
    active_enrollment,
):
    today = date.today()
    test_db.add(
        models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=today,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager_user.id,
        )
    )
    test_db.add(
        models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=manager_user.kindergarten_id,
            date=today,
            status=models.DailyReportStatus.DRAFT,
            submitted_by=manager_user.id,
            arrival_time="08:00",
            leave_time="13:00",
        )
    )
    test_db.add(
        models.Incident(
            child_id=sample_child.id,
            kindergarten_id=manager_user.kindergarten_id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="Minor test incident",
            occurred_at=datetime.now(timezone.utc),
        )
    )
    test_db.commit()

    payload = await data_quality_service.get_realtime_dashboard_data(
        db=test_db,
        kindergarten_id=manager_user.kindergarten_id,
        user_role=manager_user.role.value,
    )

    assert payload["scope"]["kindergarten_id"] == manager_user.kindergarten_id
    assert payload["system_overview"]["present_today"] >= 1
    assert payload["system_overview"]["pending_reports"] >= 1
    assert "overall_quality" in payload["data_quality"]
    assert payload["validation_status"] in {"passed", "warning", "critical"}


@pytest.mark.asyncio
async def test_predictive_attendance_uses_historical_points(
    test_db,
    manager_user,
    sample_class,
    sample_child,
    active_enrollment,
):
    start_day = date.today() - timedelta(days=20)
    for i in range(21):
        status = models.AttendanceStatus.PRESENT if i % 2 == 0 else models.AttendanceStatus.ABSENT
        test_db.add(
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=start_day + timedelta(days=i),
                status=status,
                recorded_by=manager_user.id,
            )
        )
    test_db.commit()

    prediction = await predictive_analytics.predict_attendance_rate(
        db=test_db,
        kindergarten_id=manager_user.kindergarten_id,
        days_ahead=7,
    )

    assert prediction.model_used == ModelType.LINEAR
    assert prediction.historical_data_points >= 14
    assert 0 <= prediction.predicted_value <= 100


@pytest.mark.asyncio
async def test_predictive_attendance_requires_active_children(test_db, sample_kindergarten):
    with pytest.raises(ValueError):
        await predictive_analytics.predict_attendance_rate(
            db=test_db,
            kindergarten_id=sample_kindergarten.id,
            days_ahead=7,
        )
