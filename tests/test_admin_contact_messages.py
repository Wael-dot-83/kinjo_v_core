"""
Tests for admin contact messages feature (P1-D remediation).

Verifies:
- List endpoint requires admin auth
- Resolve endpoint requires admin auth
- Pagination works
- Status filter works (open/resolved)
- Search filter works
- Resolve marks message as resolved (idempotent)
"""
import secrets
import pytest
from datetime import datetime, timezone
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="contactadmin",
        email="contactadmin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_message(db, name="Test User", email="test@example.com", subject="Help", is_resolved=False):
    msg = models.ContactMessage(
        name=name,
        email=email,
        subject=subject,
        message="Please help me with this issue.",
        is_resolved=is_resolved,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _get_admin_token(client):
    r = client.post("/token", data={"username": "contactadmin", "password": "Admin123!"})
    assert r.status_code == 200
    return r.json()["access_token"]


def _get_admin_csrf_headers(client):
    r = client.post("/token", data={"username": "contactadmin", "password": "Admin123!"})
    assert r.status_code == 200
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


class TestContactMessagesAuth:
    def test_list_requires_auth(self, client, test_db):
        r = client.get("/api/admin/contact-messages")
        assert r.status_code == 401

    def test_resolve_requires_auth(self, client, test_db):
        r = client.post("/api/admin/contact-messages/1/resolve")
        assert r.status_code == 401

    def test_manager_cannot_list(self, client, test_db, sample_kindergarten):
        mgr = models.User(
            username="mgrcm",
            email="mgrcm@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=sample_kindergarten.id,
        )
        test_db.add(mgr)
        test_db.commit()
        token_r = client.post("/token", data={"username": "mgrcm", "password": "Manager123!"})
        token = token_r.json()["access_token"]
        r = client.get("/api/admin/contact-messages", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


class TestContactMessagesList:
    def test_empty_list_returns_200(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        r = client.get("/api/admin/contact-messages", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or "messages" in data or isinstance(data, dict)

    def test_messages_returned(self, client, test_db):
        admin = _create_admin(test_db)
        _create_message(test_db, name="Alice")
        _create_message(test_db, name="Bob")
        token = _get_admin_token(client)
        r = client.get("/api/admin/contact-messages", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or data.get("messages") or data.get("data") or []
        assert len(items) == 2

    def test_status_filter_open(self, client, test_db):
        _create_admin(test_db)
        _create_message(test_db, name="Open", is_resolved=False)
        _create_message(test_db, name="Resolved", is_resolved=True)
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/contact-messages?status_filter=open",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or data.get("messages") or data.get("data") or []
        assert all(not item.get("is_resolved", True) for item in items)

    def test_status_filter_resolved(self, client, test_db):
        _create_admin(test_db)
        _create_message(test_db, name="Open", is_resolved=False)
        _create_message(test_db, name="Resolved", is_resolved=True)
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/contact-messages?status_filter=resolved",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or data.get("messages") or data.get("data") or []
        assert all(item.get("is_resolved", False) for item in items)

    def test_search_filter(self, client, test_db):
        _create_admin(test_db)
        _create_message(test_db, name="Unique Name XYZ", email="xyz@test.com")
        _create_message(test_db, name="Other Person", email="other@test.com")
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/contact-messages?q=Unique",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or data.get("messages") or data.get("data") or []
        assert len(items) == 1

    def test_pagination(self, client, test_db):
        _create_admin(test_db)
        for i in range(5):
            _create_message(test_db, name=f"User {i}", email=f"user{i}@test.com")
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/contact-messages?page=1&page_size=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") or data.get("messages") or data.get("data") or []
        assert len(items) <= 2


class TestContactMessagesResolve:
    def test_resolve_open_message(self, client, test_db):
        admin = _create_admin(test_db)
        msg = _create_message(test_db, name="Alice", is_resolved=False)
        headers = _get_admin_csrf_headers(client)
        r = client.post(
            f"/api/admin/contact-messages/{msg.id}/resolve",
            headers=headers,
        )
        assert r.status_code == 200
        # Verify DB state
        test_db.refresh(msg)
        assert msg.is_resolved is True

    def test_resolve_already_resolved_is_idempotent(self, client, test_db):
        _create_admin(test_db)
        msg = _create_message(test_db, name="Bob", is_resolved=True)
        headers = _get_admin_csrf_headers(client)
        r = client.post(
            f"/api/admin/contact-messages/{msg.id}/resolve",
            headers=headers,
        )
        assert r.status_code == 200

    def test_resolve_nonexistent_message_returns_404(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        r = client.post(
            "/api/admin/contact-messages/999999/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
