"""tests/test_audit_old_new_data.py — old_data/new_data population + legacy-null safety.

Verifies two things added/confirmed during the 2026-06 audit-trail hardening pass:

1. `validators.log_audit_action()` now accepts optional `old_data`/`new_data` dict
   params and persists them on `AuditLog.old_data`/`new_data` (JSON columns added by
   migration c1a2b3d4e5f6, already present before this change). Call sites updated to
   populate real before/after state: the admin role-change endpoint
   (api/users.py::update_user), the manager enrollment accept/reject decision
   (api/enrollment.py::review_enrollment), the class-assignment endpoint
   (api/classes.py::assign_child_to_class), and the attendance status correction
   endpoint. This test covers the role-change case as the representative "sensitive
   write" example the audit explicitly asked for.

2. Legacy audit rows written before this change (old_data=None, new_data=None) must not
   break the admin Audit Logs list/export views. In practice neither
   audit_service.py::list_audit_logs nor export_audit_logs ever reads old_data/new_data
   today, so this is currently moot by construction — but this test pins that behavior
   so a future change that starts surfacing those columns is forced to handle the null
   case explicitly instead of crashing on legacy rows.
"""
import models
from main import app
from dependencies import get_current_user


def test_user_role_change_captures_old_and_new_data(client, test_db, admin_user, manager_user):
    """PUT /api/users/{id} changing role should write old_data/new_data on the audit row."""
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = client.put(
            f"/api/users/{manager_user.id}",
            json={"role": "SUPERVISOR"},
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()

    audit_row = (
        test_db.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "USER_UPDATED",
            models.AuditLog.entity_id == manager_user.id,
        )
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    assert audit_row is not None, "Expected a USER_UPDATED audit row"
    assert audit_row.old_data is not None
    assert audit_row.new_data is not None
    assert audit_row.old_data["role"] == "MANAGER"
    assert audit_row.new_data["role"] == "SUPERVISOR"


def test_legacy_null_audit_row_renders_safely_in_list_and_export(client, test_db, admin_user):
    """A pre-existing audit row with old_data/new_data left NULL must not break the views."""
    legacy_row = models.AuditLog(
        user_id=admin_user.id,
        action="LEGACY_ACTION",
        entity_type="User",
        entity_id=admin_user.id,
        details="Row written before old_data/new_data existed",
        old_data=None,
        new_data=None,
        sensitivity_level=1,
    )
    test_db.add(legacy_row)
    test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        list_resp = client.get("/api/audit-logs", params={"action": "LEGACY_ACTION"})
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert any(log["action"] == "LEGACY_ACTION" for log in body["logs"])

        export_resp = client.get(
            "/api/audit-logs/export",
            params={"format": "json", "action": "LEGACY_ACTION", "period": "all"},
        )
        assert export_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
