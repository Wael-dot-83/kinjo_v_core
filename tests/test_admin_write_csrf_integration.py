"""End-to-end proof that a valid Admin write passes every gate AND persists.

A prior verification used "write with valid CSRF -> 404" as evidence that CSRF
succeeds. A 404 proves the opposite of what was claimed: the request reached the
not-found branch, which for PUT /users/{id} sits AFTER _validate_csrf_token but
means no business operation ran and nothing was written.

This exercises PUT /api/admin/users/{id} against a REAL existing target and
asserts the update reaches the business logic, returns 200, and changes the row
in the database. The CSRF-negative cases use the SAME valid target so a 400 can
only come from the CSRF gate, never from a missing resource.
"""
import secrets

import pytest

import models
from auth import get_password_hash
from conftest import CSRF_COOKIE_NAME, bearer_headers, csrf_pair


def _admin(db):
    u = models.User(
        username="wr_admin",
        email="wr_admin@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _supervisor(db, kg, username="wr_target"):
    u = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Pass123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg.id,
        full_name="Original Name",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _token(client, username="wr_admin", password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class TestValidAdminWriteContract:
    def test_valid_csrf_write_succeeds_and_persists(
        self, client, test_db, sample_kindergarten
    ):
        """The positive proof: 200, correct body, and a real DB mutation."""
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten)
        original_email = target.email

        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Updated By Admin", "phone_number": "+962790000123"},
            headers=bearer_headers(_token(client)),
        )
        # Reached the business operation and returned the documented success code.
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == target.id
        assert body["full_name"] == "Updated By Admin"
        assert body["phone_number"] == "+962790000123"

        # The change is persisted, not just echoed. Re-read from a fresh query.
        test_db.expire_all()
        reloaded = test_db.query(models.User).filter(models.User.id == target.id).one()
        assert reloaded.full_name == "Updated By Admin"
        assert reloaded.phone_number == "+962790000123"
        assert reloaded.email == original_email  # untouched fields preserved

    def test_missing_csrf_header_is_rejected_on_a_real_target(
        self, client, test_db, sample_kindergarten
    ):
        """400 here can only be CSRF: the target exists, so it is not a 404."""
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten, "wr_no_header")
        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Should Not Apply"},
            headers=bearer_headers(_token(client), with_csrf=False),
        )
        assert r.status_code == 400, r.text
        assert "CSRF" in r.text
        # And nothing was written.
        test_db.expire_all()
        still = test_db.query(models.User).filter(models.User.id == target.id).one()
        assert still.full_name == "Original Name"

    def test_missing_csrf_cookie_is_rejected(self, client, test_db, sample_kindergarten):
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten, "wr_no_cookie")
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["X-CSRF-Token"] = secrets.token_hex(32)  # header only, no cookie
        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Should Not Apply"},
            headers=headers,
        )
        assert r.status_code == 400, r.text
        assert "CSRF" in r.text

    def test_mismatched_csrf_pair_is_rejected(self, client, test_db, sample_kindergarten):
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten, "wr_mismatch")
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["X-CSRF-Token"] = secrets.token_hex(32)
        headers["Cookie"] = f"{CSRF_COOKIE_NAME}={secrets.token_hex(32)}"
        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Should Not Apply"},
            headers=headers,
        )
        assert r.status_code == 400, r.text
        assert "CSRF" in r.text

    def test_unauthenticated_write_is_rejected(self, client, test_db, sample_kindergarten):
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten, "wr_anon")
        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Should Not Apply"},
            headers=csrf_pair(),  # valid CSRF but no bearer token
        )
        assert r.status_code in (401, 403), r.text

    def test_non_admin_role_is_rejected(
        self, client, test_db, sample_kindergarten, supervisor_token
    ):
        """A supervisor holds a valid token and CSRF but lacks the admin role."""
        _admin(test_db)
        target = _supervisor(test_db, sample_kindergarten, "wr_rbac")
        r = client.put(
            f"/api/admin/users/{target.id}",
            json={"full_name": "Should Not Apply"},
            headers=bearer_headers(supervisor_token),
        )
        assert r.status_code == 403, r.text

    def test_nonexistent_target_is_404_separately_from_csrf(self, client, test_db):
        """404 is a resource concern, proven only WITH a valid CSRF pair.

        This is the case the prior report mistook for CSRF success — pinned here
        as its own contract so the two can never be conflated again.
        """
        _admin(test_db)
        r = client.put(
            "/api/admin/users/999999",
            json={"full_name": "No Such User"},
            headers=bearer_headers(_token(client)),
        )
        assert r.status_code == 404, r.text
        assert "CSRF" not in r.text
