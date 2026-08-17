"""Regression tests for final manager-module production blockers."""
import secrets
from datetime import date, datetime, timedelta, timezone

import pytest

import models
import manager_assignment_service
from auth import get_password_hash
from messaging_permissions import AudienceDefinition, resolve_recipients


def _bearer(token: str) -> dict[str, str]:
    # Admin write endpoints enforce double-submit CSRF (_validate_csrf_token),
    # so the token pair must accompany every request. Harmless on safe methods.
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


def test_active_kindergarten_manager_cannot_be_deleted(
    client, admin_token, manager_user
):
    response = client.delete(
        f"/api/admin/users/{manager_user.id}", headers=_bearer(admin_token)
    )
    assert response.status_code == 409
    assert "active_kindergarten_requires_manager" in response.text


def test_managerless_frozen_kindergarten_cannot_be_activated(
    client, admin_token, sample_kindergarten, test_db
):
    sample_kindergarten.status = models.KindergartenStatus.FROZEN
    test_db.commit()

    response = client.patch(
        f"/api/admin/kindergartens/{sample_kindergarten.id}/activate",
        headers=_bearer(admin_token),
    )
    assert response.status_code == 409


def test_soft_deleted_user_cannot_be_assigned_as_manager(
    client, admin_token, parent_user, sample_kindergarten, test_db
):
    from datetime import datetime, timezone

    parent_user.deleted_at = datetime.now(timezone.utc)
    test_db.commit()

    response = client.post(
        f"/api/admin/kindergartens/{sample_kindergarten.id}/assign-manager",
        headers=_bearer(admin_token),
        json={"user_id": parent_user.id, "replace": True},
    )
    assert response.status_code == 404
    test_db.refresh(parent_user)
    assert parent_user.role == models.UserRole.PARENT


def test_admin_account_cannot_be_assigned_as_kindergarten_manager(
    client, admin_token, admin_user, sample_kindergarten, test_db
):
    response = client.post(
        f"/api/admin/kindergartens/{sample_kindergarten.id}/assign-manager",
        headers=_bearer(admin_token),
        json={"user_id": admin_user.id, "replace": True},
    )
    assert response.status_code == 409
    test_db.refresh(admin_user)
    assert admin_user.role == models.UserRole.ADMIN


@pytest.mark.parametrize(
    ("kindergarten_status", "expected_status"),
    [
        (models.KindergartenStatus.FROZEN, 409),
        (models.KindergartenStatus.DELETED, 404),
    ],
)
def test_manager_cannot_be_assigned_to_non_operational_kindergarten(
    client,
    admin_token,
    parent_user,
    sample_kindergarten,
    test_db,
    kindergarten_status,
    expected_status,
):
    sample_kindergarten.status = kindergarten_status
    test_db.commit()

    response = client.post(
        f"/api/admin/kindergartens/{sample_kindergarten.id}/assign-manager",
        headers=_bearer(admin_token),
        json={"user_id": parent_user.id, "replace": True},
    )
    assert response.status_code == expected_status
    test_db.refresh(parent_user)
    assert parent_user.role == models.UserRole.PARENT


def test_canonical_user_creation_rejects_manager_for_frozen_kindergarten(
    client, admin_token, sample_kindergarten, test_db
):
    sample_kindergarten.status = models.KindergartenStatus.FROZEN
    test_db.commit()

    response = client.post(
        "/api/admin/users",
        headers=_bearer(admin_token),
        json={
            "username": "frozen_kg_manager",
            "email": "frozen_kg_manager@example.com",
            "password": "SecurePass123!",
            "role": "MANAGER",
            "kindergarten_id": sample_kindergarten.id,
        },
    )
    assert response.status_code == 409


def test_legacy_user_api_cannot_bypass_manager_lifecycle(
    client, admin_token, manager_user, sample_kindergarten, test_db
):
    headers = _bearer(admin_token)

    update = client.put(
        f"/api/users/{manager_user.id}",
        headers=headers,
        json={"status": "INACTIVE"},
    )
    assert update.status_code == 409

    delete = client.delete(f"/api/users/{manager_user.id}", headers=headers)
    assert delete.status_code == 409

    bulk_status = client.post(
        "/api/users/bulk-status-update",
        headers=headers,
        json={"user_ids": [manager_user.id], "new_status": "INACTIVE"},
    )
    assert bulk_status.status_code == 409

    bulk_delete = client.post(
        "/api/users/bulk-delete",
        headers=headers,
        json={"user_ids": [manager_user.id], "confirmation_text": "DELETE"},
    )
    assert bulk_delete.status_code == 409

    create = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "legacy_manager_blocked",
            "email": "legacy_manager_blocked@example.test",
            "password": "SecurePass123!",
            "role": "MANAGER",
            "kindergarten_id": sample_kindergarten.id,
        },
    )
    assert create.status_code == 409

    test_db.refresh(manager_user)
    assert manager_user.status == models.UserStatus.ACTIVE
    assert manager_user.deleted_at is None


def test_legacy_user_list_and_export_hide_soft_deleted_users(
    client, admin_token, parent_user, sample_kindergarten, test_db
):
    from datetime import datetime, timezone

    parent_user.kindergarten_id = sample_kindergarten.id
    parent_user.deleted_at = datetime.now(timezone.utc)
    test_db.commit()
    headers = _bearer(admin_token)

    listed = client.get("/api/users", headers=headers)
    assert listed.status_code == 200
    assert parent_user.id not in {user["id"] for user in listed.json()}

    exported = client.get("/api/users/export", headers=headers)
    assert exported.status_code == 200
    assert parent_user.username not in exported.text


def test_parent_cannot_apply_to_non_operational_kindergarten(
    client, parent_token, parent_user, sample_kindergarten, test_db
):
    sample_kindergarten.status = models.KindergartenStatus.DRAFT
    test_db.commit()
    response = client.post(
        "/api/enrollment/apply",
        headers=_bearer(parent_token),
        json={
            "first_name": "Draft",
            "last_name": parent_user.parent_profile.last_name,
            "gender": "FEMALE",
            "date_of_birth": (date.today() - timedelta(days=365 * 3)).isoformat(),
            "father_name": "Parent Father",
            "mother_first_name": "Parent Mother",
            "mother_last_name": "Family",
            "mother_nationality": "Jordanian",
            "mother_national_id": "9000000011",
            "kindergarten_id": sample_kindergarten.id,
        },
    )
    assert response.status_code == 404


def test_forced_password_change_blocks_manager_api_but_allows_replacement(
    client, manager_token, manager_user, test_db
):
    manager_user.must_change_password = True
    test_db.commit()

    blocked = client.get("/api/manager/dashboard", headers=_bearer(manager_token))
    assert blocked.status_code == 403
    assert blocked.headers["X-Password-Change-Required"] == "true"

    changed = client.post(
        "/api/users/change-password",
        headers=_bearer(manager_token),
        json={
            "current_password": "Manager123!",
            "new_password": "Manager456!",
            "confirm_password": "Manager456!",
        },
    )
    assert changed.status_code == 200

    relogin = client.post(
        "/token",
        data={"username": manager_user.username, "password": "Manager456!"},
    )
    assert relogin.status_code == 200
    allowed = client.get(
        "/api/manager/dashboard",
        headers=_bearer(relogin.json()["access_token"]),
    )
    assert allowed.status_code == 200


def test_expired_password_blocks_manager_api_but_allows_replacement(
    client, manager_token, manager_user, test_db, monkeypatch
):
    """Age-based expiry must be enforced for already-issued sessions too."""
    from config import settings

    monkeypatch.setattr(settings, "PASSWORD_MAX_AGE_DAYS", 1)
    manager_user.must_change_password = False
    manager_user.password_changed_at = datetime.now(timezone.utc) - timedelta(days=2)
    test_db.commit()

    blocked = client.get("/api/manager/dashboard", headers=_bearer(manager_token))
    assert blocked.status_code == 403
    assert blocked.headers["X-Password-Change-Required"] == "true"

    changed = client.post(
        "/api/users/change-password",
        headers=_bearer(manager_token),
        json={
            "current_password": "Manager123!",
            "new_password": "Manager456!",
            "confirm_password": "Manager456!",
        },
    )
    assert changed.status_code == 200

    relogin = client.post(
        "/token",
        data={"username": manager_user.username, "password": "Manager456!"},
    )
    assert relogin.status_code == 200
    allowed = client.get(
        "/api/manager/dashboard",
        headers=_bearer(relogin.json()["access_token"]),
    )
    assert allowed.status_code == 200


def test_accepted_enrollment_becomes_active_when_class_is_assigned(
    client, manager_token, sample_enrollment, sample_class, sample_child, test_db
):
    sample_enrollment.status = models.EnrollmentStatus.ACCEPTED
    sample_enrollment.class_id = None
    sample_child.profile_complete = True
    test_db.commit()

    response = client.post(
        f"/api/enrollments/{sample_enrollment.id}/assign-class",
        params={"class_id": sample_class.id},
        headers=_bearer(manager_token),
    )
    assert response.status_code == 200, response.text
    test_db.refresh(sample_enrollment)
    assert sample_enrollment.class_id == sample_class.id
    assert sample_enrollment.status == models.EnrollmentStatus.ACTIVE


def test_manager_audience_rejects_explicit_cross_tenant_recipient(
    test_db, manager_user
):
    other_kg = models.Kindergarten(
        name_ar="روضة أخرى",
        name_en="Other KG",
        governorate="Irbid",
        district="Irbid",
        area="Center",
        address_line="1 Main Street",
        contact_phone="+962790009999",
        status=models.KindergartenStatus.DRAFT,
    )
    test_db.add(other_kg)
    test_db.flush()
    outsider = models.User(
        username="outside_supervisor",
        email="outside-supervisor@example.test",
        hashed_password=get_password_hash("Outside123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=other_kg.id,
    )
    test_db.add(outsider)
    test_db.commit()

    audience = AudienceDefinition(
        scope="GLOBAL",
        include_roles=["SUPERVISOR"],
        include_user_ids=[outsider.id],
    )
    with pytest.raises(Exception):
        resolve_recipients(test_db, audience, manager_user)


def test_supervisor_cannot_edit_child_identity(
    client, supervisor_token, sample_child, active_enrollment
):
    response = client.put(
        f"/api/children/{sample_child.id}",
        headers=_bearer(supervisor_token),
        json={"first_name": "Unauthorized"},
    )
    assert response.status_code == 403


def test_approved_report_is_hidden_until_explicit_parent_delivery(
    client, parent_token, sample_daily_report, sample_child, test_db
):
    sample_daily_report.status = models.DailyReportStatus.APPROVED
    test_db.commit()

    detail = client.get(
        f"/api/daily-reports/{sample_daily_report.id}",
        headers=_bearer(parent_token),
    )
    assert detail.status_code == 403

    listing = client.get(
        f"/api/daily-reports/child/{sample_child.id}",
        headers=_bearer(parent_token),
    )
    assert listing.status_code == 200
    assert listing.json()["reports"] == []


def test_report_filter_rejects_inverted_date_range(client, manager_token):
    response = client.get(
        "/api/manager/daily-reports",
        params={"from_date": date(2026, 7, 2), "to_date": date(2026, 7, 1)},
        headers=_bearer(manager_token),
    )
    assert response.status_code == 422


def test_manager_assignment_routes_reject_supervisor_overlap(
    client, manager_token, supervisor_user, sample_kindergarten, sample_class, test_db
):
    existing = models.SupervisorAssignment(
        class_id=sample_class.id,
        supervisor_id=supervisor_user.id,
        start_date=date.today() + timedelta(days=1),
        is_primary=True,
    )
    other_class = models.Class(
        kindergarten_id=sample_kindergarten.id,
        name_ar="صف ثان",
        name_en="Second Class",
        class_code="BLOCKER-2",
        age_group="AGE_2_4",
        capacity_total=5,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add_all([existing, other_class])
    test_db.commit()

    assigned = client.post(
        "/api/manager/classes/assign-supervisor",
        headers=_bearer(manager_token),
        json={"class_id": other_class.id, "supervisor_id": supervisor_user.id},
    )
    assert assigned.status_code == 409

    swapped = client.put(
        f"/api/manager/classes/{other_class.id}/swap-supervisor",
        headers=_bearer(manager_token),
        json={"supervisor_id": supervisor_user.id},
    )
    assert swapped.status_code == 409

    canonical = client.put(
        f"/api/classes/{other_class.id}",
        headers=_bearer(manager_token),
        json={"supervisor_id": supervisor_user.id},
    )
    assert canonical.status_code == 409

    legacy = client.post(
        "/api/supervisor/assign",
        headers=_bearer(manager_token),
        json={
            "class_id": other_class.id,
            "supervisor_id": supervisor_user.id,
            "start_date": date.today().isoformat(),
        },
    )
    assert legacy.status_code == 409

    supervisor_user.status = models.UserStatus.INACTIVE
    test_db.commit()
    inactive_existing = client.post(
        "/api/manager/classes/assign-supervisor",
        headers=_bearer(manager_token),
        json={"class_id": sample_class.id, "supervisor_id": supervisor_user.id},
    )
    assert inactive_existing.status_code == 404


def test_legacy_assignment_rejects_inactive_class_and_invalid_date(
    client, manager_token, supervisor_user, sample_class, test_db
):
    sample_class.is_active = False
    test_db.commit()
    inactive = client.post(
        "/api/supervisor/assign",
        headers=_bearer(manager_token),
        json={
            "class_id": sample_class.id,
            "supervisor_id": supervisor_user.id,
            "start_date": date.today().isoformat(),
        },
    )
    assert inactive.status_code == 404

    manager_assign = client.post(
        "/api/manager/classes/assign-supervisor",
        headers=_bearer(manager_token),
        json={"class_id": sample_class.id, "supervisor_id": supervisor_user.id},
    )
    assert manager_assign.status_code == 404

    manager_swap = client.put(
        f"/api/manager/classes/{sample_class.id}/swap-supervisor",
        headers=_bearer(manager_token),
        json={"supervisor_id": supervisor_user.id},
    )
    assert manager_swap.status_code == 404

    shared_update = client.put(
        f"/api/classes/{sample_class.id}",
        headers=_bearer(manager_token),
        json={"supervisor_id": supervisor_user.id},
    )
    assert shared_update.status_code == 409

    invalid_date = client.post(
        "/api/supervisor/assign",
        headers=_bearer(manager_token),
        json={
            "class_id": sample_class.id,
            "supervisor_id": supervisor_user.id,
            "start_date": "not-a-date",
        },
    )
    assert invalid_date.status_code == 422


def test_manager_replacement_rolls_back_outgoing_manager_on_failure(
    manager_user, parent_user, sample_kindergarten, test_db, monkeypatch
):
    def fail_after_outgoing_audit(*args, **kwargs):
        raise RuntimeError("simulated downstream assignment failure")

    monkeypatch.setattr(
        manager_assignment_service, "strip_supervisor_role", fail_after_outgoing_audit
    )
    with pytest.raises(RuntimeError):
        manager_assignment_service.assign_user_as_manager(
            test_db,
            parent_user,
            sample_kindergarten.id,
            actor_id=None,
            allow_replace=True,
        )
    test_db.rollback()
    test_db.refresh(manager_user)
    assert manager_user.status == models.UserStatus.ACTIVE
