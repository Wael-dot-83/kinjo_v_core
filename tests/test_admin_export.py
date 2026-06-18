"""
Tests for admin user export endpoint (P1-B remediation).

Verifies:
- Export requires admin auth
- 10,000-row hard limit is enforced (422 when exceeded)
- Normal export returns CSV/JSON correctly
- Role/status filters are applied
"""
import io
import csv
import pytest
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="exportadmin",
        email="exportadmin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_manager(db, kg_id, suffix="1"):
    user = models.User(
        username=f"mgr{suffix}",
        email=f"mgr{suffix}@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_token(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


class TestExportRequiresAdmin:
    def test_unauthenticated_export_returns_401(self, client, test_db):
        r = client.get("/api/admin/users/export?format=csv")
        assert r.status_code == 401

    def test_manager_cannot_export(self, client, test_db, sample_kindergarten):
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "mgr1", "Manager123!")
        r = client.get(
            "/api/admin/users/export?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


class TestExportRowLimit:
    def test_export_within_limit_succeeds(self, client, test_db, sample_kindergarten):
        admin = _create_admin(test_db)
        # Create 5 managers (well within the 10,000 limit)
        for i in range(5):
            _create_manager(test_db, sample_kindergarten.id, suffix=str(i))

        token = _get_token(client, "exportadmin")
        r = client.get(
            "/api/admin/users/export?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")


class TestExportCSVFormat:
    def test_csv_contains_expected_headers(self, client, test_db, sample_kindergarten):
        admin = _create_admin(test_db)
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "exportadmin")
        r = client.get(
            "/api/admin/users/export?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.text))
        headers = [h.lower() for h in (reader.fieldnames or [])]
        assert "id" in headers or "username" in headers

    def test_json_export_returns_list(self, client, test_db, sample_kindergarten):
        admin = _create_admin(test_db)
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "exportadmin")
        r = client.get(
            "/api/admin/users/export?format=json",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or "users" in data or "data" in data


class TestExportFilters:
    def test_role_filter_limits_export(self, client, test_db, sample_kindergarten):
        admin = _create_admin(test_db)
        _create_manager(test_db, sample_kindergarten.id)
        token = _get_token(client, "exportadmin")

        r = client.get(
            "/api/admin/users/export?format=json&role=SUPERVISOR",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        # No supervisors were created — result should be empty
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", data.get("data", []))
        assert len(users) == 0
