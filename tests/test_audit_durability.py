"""
Regression tests: audit events must survive the request's transaction boundary.

`log_audit_event()` only does `db.add()` + `db.flush()`. A flush makes the row visible
inside the current session but does NOT commit it, and `get_db()` ends every request with
`db.close()` — which rolls back anything still uncommitted. So any endpoint whose final
`db.commit()` runs BEFORE its audit call persists the business change and silently loses
the audit record.

The existing suite cannot catch this: `conftest.override_get_db` yields one long-lived
session and never closes it, so a flushed-but-uncommitted row stays readable for the whole
test and naive "the audit row exists" assertions pass.

These tests therefore assert durability across a real transaction boundary — `rollback()`
discards exactly what a production `close()` would discard, so a row that survives it is
genuinely committed.
"""
import models
from audit_actions import AuditAction


def _assert_durable(test_db, action: str):
    """Fail unless an audit row for `action` survives a transaction rollback."""
    flushed = (
        test_db.query(models.AuditLog).filter(models.AuditLog.action == action).count()
    )
    assert flushed > 0, f"{action} was never even written (endpoint skipped the audit call)"

    # Discard everything the request left uncommitted — production's db.close() does this.
    test_db.rollback()

    durable = (
        test_db.query(models.AuditLog).filter(models.AuditLog.action == action).count()
    )
    assert durable > 0, (
        f"{action} audit row was flushed but never committed — it is discarded when the "
        f"request's session closes, so it never reaches the database."
    )


class TestAuditDurability:
    """State-changing admin endpoints must leave a durable audit trail."""

    def test_user_created_audit_is_committed(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        resp = client.post(
            "/api/admin/users",
            headers=auth_headers_admin,
            json={
                "username": "audit_probe_user",
                "email": "audit_probe@test.com",
                "password": "Probe@12345",
                "full_name": "Audit Probe",
                "role": "SUPERVISOR",
                "kindergarten_id": sample_kindergarten.id,
            },
        )
        assert resp.status_code == 201, resp.text

        _assert_durable(test_db, AuditAction.USER_CREATED)

    def test_user_deleted_audit_is_committed(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        created = client.post(
            "/api/admin/users",
            headers=auth_headers_admin,
            json={
                "username": "audit_delete_probe",
                "email": "audit_delete_probe@test.com",
                "password": "Probe@12345",
                "full_name": "Audit Delete Probe",
                "role": "SUPERVISOR",
                "kindergarten_id": sample_kindergarten.id,
            },
        )
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]

        resp = client.delete(f"/api/admin/users/{user_id}", headers=auth_headers_admin)
        assert resp.status_code in (200, 204), resp.text

        _assert_durable(test_db, AuditAction.USER_DELETED)

    def test_password_reset_audit_is_committed(
        self, client, test_db, admin_user, auth_headers_admin, sample_kindergarten
    ):
        created = client.post(
            "/api/admin/users",
            headers=auth_headers_admin,
            json={
                "username": "audit_pwd_probe",
                "email": "audit_pwd_probe@test.com",
                "password": "Probe@12345",
                "full_name": "Audit Pwd Probe",
                "role": "SUPERVISOR",
                "kindergarten_id": sample_kindergarten.id,
            },
        )
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]

        # admin_user fixture password; the endpoint re-verifies the actor's own password.
        resp = client.post(
            f"/api/admin/users/{user_id}/admin-reset-password",
            headers=auth_headers_admin,
            json={"new_password": "Reset@12345", "admin_password": "Admin123!"},
        )
        assert resp.status_code in (200, 204), resp.text

        _assert_durable(test_db, "ADMIN_PASSWORD_RESET")
