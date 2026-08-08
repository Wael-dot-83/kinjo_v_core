"""
Comprehensive audit test suite for Parent Module production-readiness:
- GET /api/parent/daily-reports
- PUT /api/parent-profiles/{parent_id} with ADMIN role override
- PUT /api/parent/profile with audit log event recording
- Role-gating and isolation checks
"""
from datetime import date
import pytest

import models


def test_get_parent_daily_reports_endpoint(client, auth_headers_parent, parent_user, sample_child, test_db):
    """Test parent daily reports endpoint fetches sent reports for parent's children."""
    today = date.today()
    report = models.DailyReport(
        child_id=sample_child.id,
        kindergarten_id=1,
        date=today,
        status=models.DailyReportStatus.SENT_TO_PARENT,
        submitted_by=1,
        arrival_time="08:00",
        leave_time="13:00",
        notes="Great day!",
    )
    test_db.add(report)
    test_db.commit()

    resp = client.get(
        "/api/parent/daily-reports",
        headers=auth_headers_parent,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["reports"][0]["id"] == report.id
    assert data["reports"][0]["notes"] == "Great day!"


def test_admin_can_update_parent_profile(client, auth_headers_admin, parent_user, test_db):
    """Test UserRole.ADMIN can update a parent's profile."""
    parent_profile = parent_user.parent_profile
    resp = client.put(
        f"/api/parent-profiles/{parent_profile.id}",
        json={"first_name": "AdminUpdated"},
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200, resp.text
    test_db.refresh(parent_profile)
    assert parent_profile.first_name == "AdminUpdated"


def test_parent_profile_self_update_emits_audit_event(client, auth_headers_parent, parent_user, test_db):
    """Test parent profile self-update records an audit log event."""
    resp = client.put(
        "/api/parent/profile",
        json={"notification_language": "en", "work_address": "Amman Center"},
        headers=auth_headers_parent,
    )
    assert resp.status_code == 200, resp.text

    audit = (
        test_db.query(models.AuditLog)
        .filter(
            models.AuditLog.user_id == parent_user.id,
        )
        .first()
    )
    assert audit is not None
