"""Gate B closure: runtime authorization for account-lifecycle states and
forged/altered identity claims.

Design fact this suite pins down (dependencies.get_current_user):
  * the JWT carries only ``sub`` (username) + ``exp`` — NOT the role;
  * every request re-fetches the user from the DB filtering ``deleted_at IS NULL``;
  * a non-ACTIVE ``status`` is rejected with 403;
  * role authority is therefore read from trusted DB state, so a role claim
    smuggled into a token is inert.

Each test mutates the *already-authenticated* admin's DB row (or mints a crafted
token) and reuses the token, proving the change takes effect WITHOUT the user
logging out — i.e. there is no stale-authorization window across these states
beyond natural token expiry.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

import models
from auth import create_access_token
from config import settings

# Representative admin surfaces: a JSON API route (require_admin) and an HTML
# page route (redirect-on-failure).
API_ROUTE = "/api/admin/dashboard"
HTML_ROUTE = "/admin/dashboard"

# Substrings that only appear in a *successful* admin dashboard payload/page;
# their absence proves no protected content leaked on denial.
API_LEAK_MARKERS = ("kpis", "enrollment", "data_quality")
HTML_LEAK_MARKERS = ("لوحة", "dashboard-", "kpi")


def _bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _assert_api_denied(resp):
    assert resp.status_code in (401, 403), (
        f"expected 401/403, got {resp.status_code}: {resp.text[:200]}"
    )
    low = resp.text.lower()
    for marker in API_LEAK_MARKERS:
        assert marker not in low, f"protected marker {marker!r} leaked on denial"


class TestLifecycleStates:
    def test_active_admin_baseline_allowed(self, client, admin_token):
        """Sanity: the token works BEFORE any lifecycle mutation."""
        resp = client.get(API_ROUTE, headers=_bearer(admin_token))
        assert resp.status_code == 200, resp.text[:300]

    def test_soft_deleted_admin_rejected(self, client, admin_user, admin_token, test_db):
        admin_user.deleted_at = datetime.now(timezone.utc)
        test_db.commit()
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(admin_token)))

    def test_inactive_admin_rejected(self, client, admin_user, admin_token, test_db):
        admin_user.status = models.UserStatus.INACTIVE
        test_db.commit()
        resp = client.get(API_ROUTE, headers=_bearer(admin_token))
        assert resp.status_code == 403
        _assert_api_denied(resp)

    def test_suspended_admin_rejected(self, client, admin_user, admin_token, test_db):
        admin_user.status = models.UserStatus.SUSPENDED
        test_db.commit()
        resp = client.get(API_ROUTE, headers=_bearer(admin_token))
        assert resp.status_code == 403
        _assert_api_denied(resp)

    def test_role_removed_admin_rejected(self, client, admin_user, admin_token, test_db):
        """Demote the admin to PARENT after the token was issued → require_admin
        must reject, because role is resolved from the DB, not the token."""
        admin_user.role = models.UserRole.PARENT
        test_db.commit()
        resp = client.get(API_ROUTE, headers=_bearer(admin_token))
        assert resp.status_code == 403
        _assert_api_denied(resp)

    def test_html_route_soft_deleted_no_content_leak(self, client, admin_user, admin_token, test_db):
        admin_user.deleted_at = datetime.now(timezone.utc)
        test_db.commit()
        resp = client.get(HTML_ROUTE, headers=_bearer(admin_token), follow_redirects=False)
        # HTML routes redirect to login (3xx) or 401 — never a 200 dashboard.
        assert resp.status_code in (301, 302, 303, 307, 401, 403), resp.status_code
        low = resp.text.lower()
        for marker in HTML_LEAK_MARKERS:
            assert marker not in low, f"protected HTML marker {marker!r} leaked"


class TestForgedAndTamperedTokens:
    def test_wrong_signature_rejected(self, client, admin_user):
        forged = jwt.encode(
            {"sub": admin_user.username, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "not-the-real-secret-key-000000000000000",
            algorithm=settings.ALGORITHM,
        )
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(forged)))

    def test_expired_token_rejected(self, client, admin_user):
        expired = create_access_token(
            {"sub": admin_user.username}, expires_delta=timedelta(minutes=-5)
        )
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(expired)))

    def test_nonexistent_user_token_rejected(self, client):
        ghost = create_access_token({"sub": "no-such-user-zzz"})
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(ghost)))

    def test_role_claim_in_token_is_ignored(self, client, parent_user):
        """A PARENT token carrying a forged role=ADMIN claim must still be denied
        — the server never reads role from the token."""
        forged = create_access_token({"sub": parent_user.username, "role": "ADMIN"})
        resp = client.get(API_ROUTE, headers=_bearer(forged))
        assert resp.status_code == 403
        _assert_api_denied(resp)

    def test_tenant_claim_in_token_is_ignored(self, client, parent_user):
        forged = create_access_token(
            {"sub": parent_user.username, "role": "ADMIN", "kindergarten_id": 1, "is_admin": True}
        )
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(forged)))

    def test_reset_purpose_token_rejected(self, client, admin_user):
        """Password-reset tokens carry a ``purpose`` claim and must never
        authenticate an ordinary request."""
        reset = create_access_token({"sub": admin_user.username, "purpose": "password_reset"})
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer(reset)))

    def test_garbage_token_rejected(self, client):
        _assert_api_denied(client.get(API_ROUTE, headers=_bearer("not.a.jwt")))


class TestMutationSafetyOnDenial:
    """A denied WRITE by a deactivated admin must not mutate any state."""

    def test_deactivated_admin_write_creates_no_row(self, client, admin_user, admin_token, test_db):
        before = test_db.query(models.Kindergarten).count()
        admin_user.status = models.UserStatus.INACTIVE
        test_db.commit()
        # Attempt an admin create; auth is decided in the dependency, before the
        # handler, so this is 401/403 (not 422) and no row is written.
        resp = client.post(
            "/api/admin/kindergartens",
            headers=_bearer(admin_token),
            json={"name_ar": "IDOR_should_not_exist", "governorate": "العاصمة"},
        )
        assert resp.status_code in (401, 403), resp.status_code
        test_db.expire_all()
        after = test_db.query(models.Kindergarten).count()
        assert after == before, "a denied write mutated the kindergartens table"
