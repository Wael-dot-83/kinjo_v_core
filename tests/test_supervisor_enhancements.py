from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone

import models
import pytest
from datetime import date
import pyotp

from audit_actions import AuditAction
from mfa_service import decrypt_secret


def test_supervisor_kpi_compare_mode_returns_previous_rates(
    client,
    test_db,
    auth_headers_supervisor,
    supervisor_user,
    sample_supervisor_assignment,
    sample_child,
    sample_enrollment,
):
    today = date.today()
    test_db.add_all(
        [
            models.DailyReport(
                child_id=sample_child.id,
                date=today,
                status=models.DailyReportStatus.SUBMITTED,
                submitted_by=supervisor_user.id,
                submitted_at=datetime.now(timezone.utc),
                kindergarten_id=supervisor_user.kindergarten_id,
                arrival_time="08:00",
                leave_time="14:00",
                activities="current range activities",
                notes="current range notes",
            ),
            models.DailyReport(
                child_id=sample_child.id,
                date=today - timedelta(days=7),
                status=models.DailyReportStatus.SUBMITTED,
                submitted_by=supervisor_user.id,
                submitted_at=datetime.now(timezone.utc) - timedelta(days=7),
                kindergarten_id=supervisor_user.kindergarten_id,
                arrival_time="08:00",
                leave_time="14:00",
                activities="previous range activities",
                notes="previous range notes",
            ),
        ]
    )
    test_db.commit()

    response = client.get(
        f"/api/supervisor/kpi?from_date={today.isoformat()}&to_date={today.isoformat()}&compare=true",
        headers=auth_headers_supervisor,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["previous_completion_rate"] is not None
    assert payload["previous_on_time_rate"] is not None
    assert payload["avg_report_length"] >= 1
    assert len(payload["heatmap"]) == 28


def test_supervisor_message_unread_count_and_soft_delete(
    client,
    test_db,
    auth_headers_supervisor,
    manager_user,
    supervisor_user,
):
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=manager_user.id,
        recipient_id=supervisor_user.id,
        kindergarten_id=supervisor_user.kindergarten_id,
        subject="Need update",
        message_body="Please update attendance.",
    )
    test_db.add(message)
    test_db.commit()
    test_db.refresh(message)

    unread_before = client.get("/api/supervisor/messages/unread-count", headers=auth_headers_supervisor)
    assert unread_before.status_code == 200
    assert unread_before.json()["unread"] >= 1

    delete_response = client.delete(f"/api/supervisor/messages/{message.id}", headers=auth_headers_supervisor)
    assert delete_response.status_code == 200

    unread_after = client.get("/api/supervisor/messages/unread-count", headers=auth_headers_supervisor)
    assert unread_after.status_code == 200
    assert unread_after.json()["unread"] == 0

    audit = test_db.query(models.AuditLog).filter(
        models.AuditLog.entity_type == "message",
        models.AuditLog.entity_id == message.id,
        models.AuditLog.action == AuditAction.MESSAGE_DELETED,
    ).first()
    assert audit is not None


def test_supervisor_notification_preferences_round_trip(
    client,
    auth_headers_supervisor,
):
    update_response = client.put(
        "/api/supervisor/notification-preferences",
        headers=auth_headers_supervisor,
        json={
            "in_app": False,
            "email": True,
            "new_messages": {"in_app": False, "email": True},
            "report_approved": {"in_app": True, "email": False},
            "incident_update": {"in_app": True, "email": True},
        },
    )
    assert update_response.status_code == 200, update_response.text

    read_response = client.get("/api/supervisor/notification-preferences", headers=auth_headers_supervisor)
    assert read_response.status_code == 200
    assert read_response.json()["in_app"] is False
    assert read_response.json()["email"] is True
    assert read_response.json()["new_messages"]["in_app"] is False
    assert read_response.json()["report_approved"]["email"] is False
    assert read_response.json()["incident_update"]["email"] is True


def test_supervisor_can_enable_and_disable_2fa(
    client,
    test_db,
    auth_headers_supervisor,
    supervisor_user,
):
    enable_response = client.post("/api/supervisor/2fa/enable", headers=auth_headers_supervisor)
    assert enable_response.status_code == 200, enable_response.text
    enable_payload = enable_response.json()
    assert enable_payload["status"] == "enabled"
    assert enable_payload["qr_code_data_url"].startswith("data:image/png;base64,")
    assert len(enable_payload["backup_codes"]) == 6

    test_db.refresh(supervisor_user)
    assert supervisor_user.mfa_enabled is True
    assert supervisor_user.mfa_secret
    assert supervisor_user.totp_secret

    disable_without_code = client.post(
        "/api/supervisor/2fa/disable",
        headers=auth_headers_supervisor,
        json={"code": "000000"},
    )
    assert disable_without_code.status_code == 400

    secret = decrypt_secret(supervisor_user.totp_secret)
    assert secret is not None
    valid_code = pyotp.TOTP(secret).now()

    disable_response = client.post(
        "/api/supervisor/2fa/disable",
        headers=auth_headers_supervisor,
        json={"code": valid_code},
    )
    assert disable_response.status_code == 200, disable_response.text
    test_db.refresh(supervisor_user)
    assert supervisor_user.mfa_enabled is False
    assert supervisor_user.mfa_secret is None


def test_supervisor_change_password_requires_confirmation(
    client,
    auth_headers_supervisor,
):
    response = client.post(
        "/api/supervisor/change-password",
        headers=auth_headers_supervisor,
        json={
            "current_password": "Supervisor123!",
            "new_password": "NewPassword123!",
            "confirm_password": "DifferentPassword123!",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "New password confirmation does not match."


def test_supervisor_daily_report_duplicate_requires_force_and_overwrites_existing(
    client,
    test_db,
    auth_headers_supervisor,
    sample_child,
    sample_daily_report,
    sample_supervisor_assignment,
    sample_enrollment,
):
    sample_daily_report.status = models.DailyReportStatus.RETURNED
    sample_daily_report.class_id = sample_enrollment.class_id
    test_db.commit()
    payload = {
        "child_id": sample_child.id,
        "date": sample_daily_report.date.isoformat(),
        "status": "SUBMITTED",
        "activities": "updated forced activities",
        "notes": "updated forced notes",
    }

    reject_response = client.post(
        "/api/supervisor/daily-reports",
        headers=auth_headers_supervisor,
        json=payload,
    )
    assert reject_response.status_code == 409, reject_response.text
    reject_payload = reject_response.json()
    assert reject_payload["detail"]["can_force"] is True
    assert reject_payload["detail"]["existing_id"] == sample_daily_report.id

    force_response = client.post(
        "/api/supervisor/daily-reports?force=true",
        headers=auth_headers_supervisor,
        json=payload,
    )
    assert force_response.status_code == 200, force_response.text
    assert force_response.json()["forced"] is True
    assert force_response.json()["id"] == sample_daily_report.id

    test_db.refresh(sample_daily_report)
    assert sample_daily_report.activities == "updated forced activities"
    assert sample_daily_report.notes == "updated forced notes"
    assert test_db.query(models.DailyReport).filter(
        models.DailyReport.child_id == sample_child.id,
        models.DailyReport.date == sample_daily_report.date,
    ).count() == 1


def test_manager_can_create_and_send_report_from_shared_form_contract(
    client, test_db, auth_headers_manager, sample_child, active_enrollment, monkeypatch
):
    """The rendered manager form has a real, scoped create-and-send endpoint."""
    monkeypatch.setattr("routers.manager.validators.is_working_day", lambda *args: True)
    response = client.post(
        "/api/manager/daily-reports/create-and-send",
        headers=auth_headers_manager,
        json={
            "child_id": sample_child.id,
            "date": date.today().isoformat(),
            "arrival_time": "08:00",
            "leave_time": "14:00",
            "activities": "Art",
        },
    )
    assert response.status_code == 201, response.text
    report = test_db.query(models.DailyReport).filter(
        models.DailyReport.id == response.json()["id"]
    ).one()
    assert report.kindergarten_id == active_enrollment.kindergarten_id
    assert report.status == models.DailyReportStatus.SENT_TO_PARENT


def test_admin_can_use_shared_report_form_endpoint(
    client, test_db, auth_headers_admin, sample_child, active_enrollment, monkeypatch
):
    monkeypatch.setattr("routers.manager.validators.is_working_day", lambda *args: True)
    response = client.post(
        "/api/manager/daily-reports/create-and-send",
        headers=auth_headers_admin,
        json={"child_id": sample_child.id, "date": date.today().isoformat(), "arrival_time": "08:00"},
    )
    assert response.status_code == 201, response.text


def test_canonical_daily_report_invalid_date_returns_422(
    client, auth_headers_supervisor, sample_child
):
    response = client.post(
        "/api/daily-reports/create",
        headers=auth_headers_supervisor,
        json={"child_id": sample_child.id, "date": "not-a-date", "arrival_time": "08:00"},
    )
    assert response.status_code == 422


def test_safety_incident_invalid_timestamp_returns_422(
    client, auth_headers_supervisor, sample_child, sample_supervisor_assignment, sample_enrollment
):
    response = client.post(
        "/api/supervisor/safety-incidents",
        headers=auth_headers_supervisor,
        json={
            "child_id": sample_child.id,
            "type": "INJURY",
            "severity_level": "LOW",
            "description": "Test",
            "occurred_at": "not-a-timestamp",
        },
    )
    assert response.status_code == 422


def test_manager_shared_report_form_rejects_invalid_time(
    client, auth_headers_manager, sample_child, active_enrollment
):
    response = client.post(
        "/api/manager/daily-reports/create-and-send",
        headers=auth_headers_manager,
        json={"child_id": sample_child.id, "date": date.today().isoformat(), "arrival_time": "99:99"},
    )
    assert response.status_code == 422


def test_supervisor_can_resolve_incident_with_put_and_attachment(
    client,
    test_db,
    auth_headers_supervisor,
    sample_incident,
    sample_supervisor_assignment,
    sample_enrollment,
):
    response = client.put(
        f"/api/supervisor/safety-incidents/{sample_incident.id}/resolve",
        headers={k: v for k, v in auth_headers_supervisor.items() if k != "Content-Type"},
        data={"resolution_notes": "Handled and documented"},
        files={"attachment": ("incident-note.jpg", io.BytesIO(b"resolved"), "image/jpeg")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "resolved"
    assert payload["attachment_url"]

    test_db.refresh(sample_incident)
    assert sample_incident.closed_at is not None
    assert sample_incident.resolution_notes == "Handled and documented"
    assert sample_incident.attachment_url


def test_supervisor_child_observations_pagination_exposes_total_count(
    client,
    test_db,
    auth_headers_supervisor,
    supervisor_user,
    sample_child,
    sample_supervisor_assignment,
    sample_enrollment,
):
    test_db.add_all(
        [
            models.Observation(
                child_id=sample_child.id,
                observed_by=supervisor_user.id,
                domain=models.LearningDomain.COGNITIVE,
                observation_text=f"Observation {index}",
                observed_at=datetime.now(timezone.utc) - timedelta(minutes=index),
            )
            for index in range(3)
        ]
    )
    test_db.commit()

    response = client.get(
        f"/api/children/{sample_child.id}/observations?limit=2&offset=0",
        headers=auth_headers_supervisor,
    )

    assert response.status_code == 200, response.text
    assert response.headers.get("X-Total-Count") == "3"
    assert response.headers.get("X-Limit") == "2"
    assert response.headers.get("X-Offset") == "0"

    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 2


@pytest.mark.parametrize(
    "path",
    [
        "/supervisor/attendance",
        "/supervisor/daily-reports",
        "/supervisor/messages",
        "/supervisor/profile",
        "/supervisor/safety",
        "/supervisor/settings",
    ],
)
def test_all_supervisor_pages_are_registered(client, auth_headers_supervisor, path):
    response = client.get(path, headers=auth_headers_supervisor)
    assert response.status_code == 200
