"""Contract tests for double-submit CSRF on admin write endpoints.

These exist because ~103 test failures were once traced to auth-only headers
hitting `_validate_csrf_token`, and the tempting "fix" was to bypass the
validator under TESTING. That would have deleted a real security boundary.

These tests pin the boundary in place instead: a matching pair succeeds, and
every way of failing to present one is rejected. If someone later adds a
TESTING/env bypass to `_validate_csrf_token`, the negative cases below start
returning 2xx and fail.
"""
import secrets

import pytest

import models
from auth import get_password_hash
from conftest import CSRF_COOKIE_NAME, bearer_headers, csrf_pair

# A state-changing admin endpoint guarded by _validate_csrf_token.
WRITE_URL = "/api/admin/users/{user_id}"


@pytest.fixture
def csrf_admin(test_db):
    user = models.User(
        username="csrf_contract_admin",
        email="csrf_contract_admin@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def csrf_target(test_db, sample_kindergarten):
    user = models.User(
        username="csrf_contract_target",
        email="csrf_contract_target@example.com",
        hashed_password=get_password_hash("Pass123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=sample_kindergarten.id,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _token(client) -> str:
    r = client.post(
        "/token",
        data={"username": "csrf_contract_admin", "password": "Admin123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class TestDoubleSubmitContract:
    """Header and cookie must both be present and must match."""

    def test_matching_pair_is_accepted(self, client, csrf_admin, csrf_target):
        """The happy path: a matching header/cookie pair passes the validator."""
        r = client.delete(
            WRITE_URL.format(user_id=csrf_target.id),
            headers=bearer_headers(_token(client)),
        )
        # Any non-CSRF outcome proves the validator let the request through.
        assert r.status_code != 400, r.text
        assert "CSRF" not in r.text

    def test_missing_both_is_rejected(self, client, csrf_admin, csrf_target):
        r = client.delete(
            WRITE_URL.format(user_id=csrf_target.id),
            headers=bearer_headers(_token(client), with_csrf=False),
        )
        assert r.status_code == 400
        assert "CSRF" in r.text

    def test_header_without_cookie_is_rejected(self, client, csrf_admin, csrf_target):
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["X-CSRF-Token"] = secrets.token_hex(32)
        r = client.delete(WRITE_URL.format(user_id=csrf_target.id), headers=headers)
        assert r.status_code == 400
        assert "CSRF" in r.text

    def test_cookie_without_header_is_rejected(self, client, csrf_admin, csrf_target):
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["Cookie"] = f"{CSRF_COOKIE_NAME}={secrets.token_hex(32)}"
        r = client.delete(WRITE_URL.format(user_id=csrf_target.id), headers=headers)
        assert r.status_code == 400
        assert "CSRF" in r.text

    def test_mismatched_pair_is_rejected(self, client, csrf_admin, csrf_target):
        """A forged header cannot be paired with an unrelated cookie."""
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["X-CSRF-Token"] = secrets.token_hex(32)
        headers["Cookie"] = f"{CSRF_COOKIE_NAME}={secrets.token_hex(32)}"
        r = client.delete(WRITE_URL.format(user_id=csrf_target.id), headers=headers)
        assert r.status_code == 400
        assert "CSRF" in r.text

    def test_empty_values_are_rejected(self, client, csrf_admin, csrf_target):
        """Empty strings compare equal — they must not count as a valid pair."""
        headers = bearer_headers(_token(client), with_csrf=False)
        headers["X-CSRF-Token"] = ""
        headers["Cookie"] = f"{CSRF_COOKIE_NAME}="
        r = client.delete(WRITE_URL.format(user_id=csrf_target.id), headers=headers)
        assert r.status_code == 400
        assert "CSRF" in r.text


class TestValidatorHasNoBypass:
    """Static guarantees about the validator itself."""

    def test_validators_use_constant_time_comparison(self):
        import inspect

        from admin_endpoints import _validate_csrf_token as admin_validator
        from heatmap.backend.admin_router import _validate_csrf_token as heatmap_validator

        for validator in (admin_validator, heatmap_validator):
            source = inspect.getsource(validator)
            assert "compare_digest" in source, (
                f"{validator.__module__}._validate_csrf_token must compare in "
                "constant time"
            )

    def test_validators_contain_no_environment_bypass(self):
        """No TESTING/DEBUG escape hatch may short-circuit the check."""
        import inspect

        from admin_endpoints import _validate_csrf_token as admin_validator
        from heatmap.backend.admin_router import _validate_csrf_token as heatmap_validator

        forbidden = ("TESTING", "DEBUG", "is_production", "ENVIRONMENT")
        for validator in (admin_validator, heatmap_validator):
            source = inspect.getsource(validator)
            for token in forbidden:
                assert token not in source, (
                    f"{validator.__module__}._validate_csrf_token references "
                    f"{token!r} — CSRF must not be conditional on environment"
                )

    def test_csrf_pair_helper_matches_production_cookie_name(self):
        """The canonical helper must target the cookie the app actually reads."""
        from config import settings

        pair = csrf_pair()
        assert pair["Cookie"].startswith(f"{settings.CSRF_COOKIE_NAME}=")
        assert pair["X-CSRF-Token"] == pair["Cookie"].split("=", 1)[1]
