"""Contract tests for GET /api/admin/dashboard/activity filters.

These lock down two production failures found in the admin activity feed:

1. `permission_change` was offered by the UI but mapped to no backend action, so
   `_ACTIVITY_MAP` lookups produced an empty `IN ()` list and the filter returned
   zero rows even when role changes existed.
2. `module=governance` was offered by the UI but no audit action is classified into
   the `governance` module, so it too could only ever return zero rows.

The invariant worth protecting is broader than either bug: *every* filter value the
UI offers must be answerable by the backend, and every returned item's rendered
`type` must equal the requested `activity_type`.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import admin_endpoints
import models
from audit_actions import AuditAction

_JORDAN_TZ = timezone(timedelta(hours=3))

ACTIVITY_URL = "/api/admin/dashboard/activity"


def _audit(db, action, *, user_id, old_data=None, new_data=None, entity_type="User"):
    row = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=user_id,
        old_data=old_data,
        new_data=new_data,
        created_at=datetime.now(_JORDAN_TZ),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def activity_rows(test_db, admin_user):
    """One genuine role change, one non-role user update, one unrelated action."""
    _audit(
        test_db,
        AuditAction.USER_UPDATED,
        user_id=admin_user.id,
        old_data={"role": "SUPERVISOR", "email": "a@test.com"},
        new_data={"role": "MANAGER", "email": "a@test.com"},
    )
    _audit(
        test_db,
        AuditAction.USER_UPDATED,
        user_id=admin_user.id,
        old_data={"role": "MANAGER", "email": "old@test.com"},
        new_data={"role": "MANAGER", "email": "new@test.com"},
    )
    _audit(test_db, AuditAction.USER_CREATED, user_id=admin_user.id)
    return test_db


class TestPermissionChangeFilter:
    def test_permission_change_returns_the_role_change_row(
        self, client, activity_rows, auth_headers_admin
    ):
        """Regression: this filter previously returned zero rows because no
        AuditAction maps to `permission_change` in _ACTIVITY_MAP."""
        r = client.get(
            ACTIVITY_URL, params={"activity_type": "permission_change"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1, f"expected exactly the role change, got {body['total']}"
        assert body["items"][0]["type"] == "permission_change"

    def test_permission_change_does_not_return_every_user_update(
        self, client, activity_rows, auth_headers_admin
    ):
        """Mapping the derived type to bare `action == USER_UPDATED` would return
        the email-only update too — wrong rows instead of no rows."""
        r = client.get(
            ACTIVITY_URL, params={"activity_type": "permission_change"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_user_update_excludes_role_changes(
        self, client, activity_rows, auth_headers_admin
    ):
        """Role changes render as `permission_change`, so they must not come back
        under `user_update` — otherwise the filter disagrees with the item type."""
        r = client.get(
            ACTIVITY_URL, params={"activity_type": "user_update"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["type"] == "user_update"

    def test_returned_item_type_always_matches_requested_filter(
        self, client, activity_rows, auth_headers_admin
    ):
        for activity_type in ("permission_change", "user_update", "user_create"):
            r = client.get(
                ACTIVITY_URL, params={"activity_type": activity_type},
                headers=auth_headers_admin,
            )
            assert r.status_code == 200, r.text
            for item in r.json()["items"]:
                assert item["type"] == activity_type, (
                    f"filter {activity_type!r} returned an item typed {item['type']!r}"
                )

    def test_pagination_total_counts_only_matching_rows(
        self, client, activity_rows, auth_headers_admin
    ):
        """`total` is computed in SQL; if the derived type were post-filtered in
        Python, total would count non-role updates and paginate wrongly."""
        r = client.get(
            ACTIVITY_URL, params={"activity_type": "permission_change", "page_size": 1},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1


class TestRoleChangeClassifierParity:
    """The SQL clause and the Python classifier must agree, or the feed shows one
    thing and the filter selects another."""

    @pytest.mark.parametrize(
        "old_data,new_data,expected",
        [
            ({"role": "SUPERVISOR"}, {"role": "MANAGER"}, True),
            ({"role": "MANAGER"}, {"role": "MANAGER"}, False),
            (None, {"role": "MANAGER"}, False),
            ({"role": "MANAGER"}, None, False),
            ({}, {}, False),
            ({"email": "x"}, {"email": "y"}, False),
        ],
    )
    def test_python_classifier(self, old_data, new_data, expected):
        assert admin_endpoints._is_role_change(old_data, new_data) is expected

    def test_sql_clause_matches_python_classifier(self, test_db, admin_user):
        """Proves the JSON predicate actually executes on the configured DB and
        selects exactly the rows the Python classifier calls a role change."""
        cases = [
            ({"role": "SUPERVISOR"}, {"role": "MANAGER"}),
            ({"role": "MANAGER"}, {"role": "MANAGER"}),
            (None, {"role": "MANAGER"}),
            ({"role": "MANAGER"}, None),
            ({}, {}),
            ({"email": "x"}, {"email": "y"}),
        ]
        created = []
        for old_data, new_data in cases:
            created.append(
                _audit(
                    test_db, AuditAction.USER_UPDATED, user_id=admin_user.id,
                    old_data=old_data, new_data=new_data,
                )
            )

        sql_ids = {
            r.id
            for r in test_db.query(models.AuditLog)
            .filter(admin_endpoints._role_change_clause())
            .all()
        }
        python_ids = {
            row.id
            for row in created
            if admin_endpoints._is_role_change(row.old_data, row.new_data)
        }
        assert sql_ids == python_ids, "SQL role-change clause disagrees with the Python classifier"


class TestUiFilterOptionsAreAnswerable:
    """Every value the filter bar offers must be answerable by the backend.

    This is the check that would have caught both `permission_change` and
    `governance` before release.
    """

    @staticmethod
    def _js_option_values(const_name):
        js = Path("static/js/admin_activity_filters.js").read_text(encoding="utf-8")
        block = re.search(const_name + r"\s*=\s*\[(.*?)\];", js, re.S)
        assert block, f"{const_name} not found in admin_activity_filters.js"
        return re.findall(r'value:\s*"([^"]+)"', block.group(1))

    def test_every_ui_activity_type_is_backed(self):
        backend_types = {m[2] for m in admin_endpoints._ACTIVITY_MAP.values()}
        backend_types.add(admin_endpoints.PERMISSION_CHANGE_TYPE)  # derived, not an action
        unbacked = set(self._js_option_values("ACTIVITY_TYPE_OPTIONS")) - backend_types
        assert not unbacked, f"UI offers activity_type values the backend cannot return: {sorted(unbacked)}"

    def test_every_ui_module_is_backed(self):
        backend_modules = {m[3] for m in admin_endpoints._ACTIVITY_MAP.values()}
        unbacked = set(self._js_option_values("MODULE_OPTIONS")) - backend_modules
        assert not unbacked, f"UI offers module values the backend cannot return: {sorted(unbacked)}"
