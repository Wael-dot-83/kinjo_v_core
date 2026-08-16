"""Exploit-focused coverage for server-side access-token session lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.websockets import WebSocketDisconnect
from jose import jwt
from redis.exceptions import RedisError

import models
import session_service
from api.auth.password_reset_service import issue_password_reset_token
from config import settings


@pytest.fixture(autouse=True)
def isolated_local_sessions(monkeypatch):
    monkeypatch.setattr(session_service, "_redis_client", lambda: None)
    session_service.clear_local_sessions()
    yield
    session_service.clear_local_sessions()


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/token", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _csrf_bearer_headers(client, token: str) -> dict[str, str]:
    csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
    }


def _me(client, token: str):
    return client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {token}"}
    )


def test_access_tokens_carry_unique_jti_and_iat(client, admin_user):
    first = _login(client, admin_user.username, "Admin123!")
    second = _login(client, admin_user.username, "Admin123!")

    first_claims = jwt.get_unverified_claims(first)
    second_claims = jwt.get_unverified_claims(second)
    assert first_claims["jti"] != second_claims["jti"]
    assert isinstance(first_claims["iat"], int)
    assert isinstance(second_claims["iat"], int)


def test_missing_session_record_is_rejected_and_never_recreated(
    client, admin_user
):
    token = _login(client, admin_user.username, "Admin123!")
    claims = jwt.get_unverified_claims(token)
    session_service.revoke_access_session(admin_user.username, claims["jti"])

    assert _me(client, token).status_code == 401
    # A second request remains rejected; validation cannot recreate the key.
    assert _me(client, token).status_code == 401


def test_idle_expired_session_is_rejected(client, admin_user, monkeypatch):
    token = _login(client, admin_user.username, "Admin123!")
    real_now = session_service.time.time()
    monkeypatch.setattr(
        session_service.time,
        "time",
        lambda: real_now + settings.SESSION_TIMEOUT_MINUTES * 60 + 1,
    )

    assert _me(client, token).status_code == 401


def test_production_redis_failure_returns_503_instead_of_failing_open(
    client, admin_user, monkeypatch
):
    token = _login(client, admin_user.username, "Admin123!")

    class BrokenRedis:
        def eval(self, *_args, **_kwargs):
            raise RedisError("redis unavailable")

    monkeypatch.setattr(session_service, "_redis_client", lambda: BrokenRedis())
    monkeypatch.setattr(session_service.settings, "TESTING", False)
    monkeypatch.setattr(session_service.settings, "ENVIRONMENT", "production")

    response = _me(client, token)
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication security store is unavailable."
    }


def test_production_does_not_issue_token_when_session_store_is_down(monkeypatch):
    from auth import create_access_token

    class BrokenRedis:
        def setex(self, *_args, **_kwargs):
            raise RedisError("redis unavailable")

    monkeypatch.setattr(session_service, "_redis_client", lambda: BrokenRedis())
    monkeypatch.setattr(session_service.settings, "TESTING", False)
    monkeypatch.setattr(session_service.settings, "ENVIRONMENT", "production")

    with pytest.raises(session_service.SessionStoreUnavailable):
        create_access_token({"sub": "never-issued", "role": "ADMIN"})


def test_logout_revokes_bearer_but_not_an_independent_session(client, admin_user):
    first = _login(client, admin_user.username, "Admin123!")
    second = _login(client, admin_user.username, "Admin123!")

    response = client.post(
        "/api/auth/logout", headers=_csrf_bearer_headers(client, first)
    )
    assert response.status_code == 200
    assert _me(client, first).status_code == 401
    assert _me(client, second).status_code == 200


def test_revoked_bearer_cannot_open_dashboard_websocket(
    client, test_db, admin_user, monkeypatch
):
    import main

    token = _login(client, admin_user.username, "Admin123!")
    claims = jwt.get_unverified_claims(token)
    session_service.revoke_access_session(admin_user.username, claims["jti"])
    monkeypatch.setattr(main, "get_db", lambda: iter((test_db,)))

    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(f"/ws/dashboard?token={token}"):
            pass
    assert closed.value.code == 4001


def test_self_service_reset_revokes_existing_bearer_and_updates_lifecycle(
    client, test_db, parent_user
):
    old_token = _login(client, parent_user.username, "Parent123!")
    reset_token = issue_password_reset_token(test_db, parent_user)

    response = client.post(
        "/api/users/reset-password",
        json={"token": reset_token, "new_password": "ResetParent123!"},
        headers=_csrf_bearer_headers(client, old_token),
    )
    assert response.status_code == 200, response.text
    test_db.refresh(parent_user)
    assert parent_user.password_changed_at is not None
    assert parent_user.updated_at is not None
    assert parent_user.must_change_password is False
    assert _me(client, old_token).status_code == 401
    assert _login(client, parent_user.username, "ResetParent123!")


def test_admin_reset_uses_canonical_lifecycle_and_revokes_target_sessions(
    client, test_db, admin_user, parent_user
):
    target_token = _login(client, parent_user.username, "Parent123!")
    admin_token = _login(client, admin_user.username, "Admin123!")
    parent_user.must_change_password = True
    parent_user.password_changed_at = None
    test_db.commit()

    response = client.post(
        f"/api/admin/users/{parent_user.id}/admin-reset-password",
        json={
            "admin_password": "Admin123!",
            "new_password": "AdminReset123!",
        },
        headers=_csrf_bearer_headers(client, admin_token),
    )
    assert response.status_code == 200, response.text
    test_db.refresh(parent_user)
    assert parent_user.password_changed_at is not None
    assert parent_user.updated_at is not None
    assert parent_user.must_change_password is False
    assert _me(client, target_token).status_code == 401


@pytest.mark.parametrize(
    ("role_fixture", "username", "old_password", "path", "payload"),
    [
        (
            "parent_user",
            "testparent@test.com",
            "Parent123!",
            "/api/users/change-password",
            {
                "current_password": "Parent123!",
                "new_password": "UsersPath123!",
                "confirm_password": "UsersPath123!",
            },
        ),
        (
            "parent_user",
            "testparent@test.com",
            "Parent123!",
            "/api/me/password",
            {
                "current_password": "Parent123!",
                "new_password": "MePathParent123!",
                "confirm_password": "MePathParent123!",
            },
        ),
        (
            "parent_user",
            "testparent@test.com",
            "Parent123!",
            "/api/users/me/password",
            {
                "current_password": "Parent123!",
                "new_password": "CompatPath123!",
            },
        ),
        (
            "supervisor_user",
            "testsupervisor",
            "Supervisor123!",
            "/api/supervisor/change-password",
            {
                "current_password": "Supervisor123!",
                "new_password": "SupervisorPath123!",
                "confirm_password": "SupervisorPath123!",
            },
        ),
        (
            "admin_user",
            "testadmin",
            "Admin123!",
            "/api/admin/profile/password",
            {
                "current_password": "Admin123!",
                "new_password": "AdminPath123!",
                "confirm_password": "AdminPath123!",
            },
        ),
    ],
)
def test_each_live_self_service_password_path_revokes_its_presented_token(
    request,
    client,
    test_db,
    role_fixture,
    username,
    old_password,
    path,
    payload,
):
    user = request.getfixturevalue(role_fixture)
    old_token = _login(client, username, old_password)

    request_method = client.put if path == "/api/users/me/password" else client.post
    response = request_method(
        path,
        json=payload,
        headers=_csrf_bearer_headers(client, old_token),
    )
    assert response.status_code == 200, response.text
    test_db.refresh(user)
    assert user.password_changed_at is not None
    assert user.updated_at is not None
    assert _me(client, old_token).status_code == 401


def test_session_registry_never_uses_plaintext_identity_or_token(client, admin_user):
    token = _login(client, admin_user.username, "Admin123!")
    claims = jwt.get_unverified_claims(token)
    keys = list(session_service._memory_sessions)
    assert keys
    for key in keys:
        assert admin_user.username not in key
        assert claims["jti"] not in key
        assert token not in key


def test_password_change_timestamp_invalidates_session_even_if_prefix_delete_races(
    client, test_db, admin_user, monkeypatch
):
    token = _login(client, admin_user.username, "Admin123!")
    # Simulate a concurrent token registration that lands immediately after a
    # prefix scan.  The trusted high-resolution issue time remains older than
    # the committed credential change and must independently reject replay.
    monkeypatch.setattr(session_service, "revoke_all_user_sessions", lambda _u: None)
    admin_user.password_changed_at = datetime.now(timezone.utc)
    test_db.commit()

    assert _me(client, token).status_code == 401
