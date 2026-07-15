"""End-to-end proof that the `permission_change` filter matches real audit rows.

The unit tests for this filter build AuditLog rows by hand, which only proves the
predicate works against the shape the *test* writes. The filter reads
`old_data`/`new_data`, which in production are written by `log_audit_event` via
`model_to_dict` + `redact_sensitive_data` — so the contract that actually matters
is between the real update endpoint and the real filter.

This drives a genuine role change through `PUT /api/admin/users/{id}` and asserts
the feed and the filter agree about it.
"""
from datetime import date

import models
from audit_actions import AuditAction

ACTIVITY_URL = "/api/admin/dashboard/activity"
USERS_URL = "/api/admin/users"


def _make_supervisor(test_db, kindergarten):
    from auth import get_password_hash

    user = models.User(
        username="role_change_target",
        email="role_change_target@test.com",
        hashed_password=get_password_hash("Target123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten.id,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_real_role_change_is_matched_by_the_permission_change_filter(
    client, test_db, admin_user, sample_kindergarten, supervisor_user, auth_headers_admin
):
    # `supervisor_user` is a second supervisor for the same kindergarten: promoting
    # the only supervisor is refused, because it would leave the KG uncovered.
    target = _make_supervisor(test_db, sample_kindergarten)

    # A non-role edit first: it must NOT be classified as a permission change.
    r = client.put(
        f"{USERS_URL}/{target.id}",
        json={"email": "renamed@test.com"},
        headers=auth_headers_admin,
    )
    assert r.status_code == 200, r.text

    # The real role change.
    r = client.put(
        f"{USERS_URL}/{target.id}",
        json={"role": "MANAGER"},
        headers=auth_headers_admin,
    )
    assert r.status_code == 200, r.text

    # Sanity: the audit rows really carry role in old_data/new_data as plain
    # strings — this is what the SQL predicate depends on.
    rows = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == AuditAction.USER_UPDATED)
        .all()
    )
    assert rows, "the update endpoint wrote no USER_UPDATED audit row"
    role_rows = [
        r_ for r_ in rows
        if (r_.old_data or {}).get("role") != (r_.new_data or {}).get("role")
    ]
    assert len(role_rows) == 1, f"expected exactly one role-change row, got {len(role_rows)}"
    assert role_rows[0].old_data["role"] == "SUPERVISOR"
    assert role_rows[0].new_data["role"] == "MANAGER"

    # The filter must find exactly that row.
    r = client.get(
        ACTIVITY_URL, params={"activity_type": "permission_change"},
        headers=auth_headers_admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1, (
        f"permission_change filter returned {body['total']} rows for one real role change"
    )
    assert body["items"][0]["type"] == "permission_change"

    # And the non-role edit must still be reachable under user_update, without
    # the role change leaking into it.
    r = client.get(
        ACTIVITY_URL, params={"activity_type": "user_update"}, headers=auth_headers_admin
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(i["type"] == "user_update" for i in body["items"])
