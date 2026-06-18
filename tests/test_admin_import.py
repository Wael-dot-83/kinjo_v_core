"""
Tests for admin CSV import endpoint (P1-C remediation).

Verifies:
- Import requires admin auth
- 20 MB file size limit is enforced
- Valid CSV is processed correctly
- Invalid CSV rows produce per-row errors
- Dry-run mode works
"""
import io
import pytest
from auth import get_password_hash
import models


def _create_admin(db):
    user = models.User(
        username="importadmin",
        email="importadmin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_admin_token(client):
    r = client.post("/token", data={"username": "importadmin", "password": "Admin123!"})
    assert r.status_code == 200
    return r.json()["access_token"]


def _make_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    if rows:
        buf.write(",".join(rows[0].keys()) + "\n")
        for row in rows:
            buf.write(",".join(str(v) for v in row.values()) + "\n")
    return buf.getvalue().encode()


VALID_ROW = {
    "username": "newuser01",
    "email": "newuser01@example.com",
    "password": "ValidPass123!",
    "role": "SUPERVISOR",
}


class TestImportAuth:
    def test_unauthenticated_import_returns_401(self, client, test_db):
        csv_bytes = _make_csv([VALID_ROW])
        r = client.post(
            "/api/admin/users/import-csv",
            files={"file": ("users.csv", csv_bytes, "text/csv")},
        )
        assert r.status_code == 401


class TestImportSizeLimit:
    def test_oversized_file_returns_422(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        # 21 MB of data
        large_data = b"x" * (21 * 1024 * 1024)
        r = client.post(
            "/api/admin/users/import-csv",
            files={"file": ("big.csv", large_data, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code in (400, 413, 422)

    def test_valid_size_file_is_processed(self, client, test_db, sample_kindergarten):
        _create_admin(test_db)
        token = _get_admin_token(client)
        csv_bytes = _make_csv([VALID_ROW])
        r = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("users.csv", csv_bytes, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200


class TestImportDryRun:
    def test_dry_run_does_not_create_users(self, client, test_db, sample_kindergarten):
        _create_admin(test_db)
        token = _get_admin_token(client)
        csv_bytes = _make_csv([VALID_ROW])
        r = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("users.csv", csv_bytes, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("dry_run") is True
        assert data.get("created_ids", []) == []

    def test_dry_run_reports_validation_errors(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        bad_row = {"username": "", "email": "not-an-email", "password": "short", "role": "INVALID"}
        csv_bytes = _make_csv([bad_row])
        r = client.post(
            "/api/admin/users/import-csv?dry_run=true",
            files={"file": ("users.csv", csv_bytes, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("failed", 0) > 0 or len(data.get("errors", [])) > 0


class TestImportLogs:
    def test_admin_can_list_import_logs(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/imports/logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "logs" in data
        assert "total" in data

    def test_import_logs_requires_admin(self, client, test_db):
        r = client.get("/api/admin/imports/logs")
        assert r.status_code == 401

    def test_import_log_detail_not_found_returns_404(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/imports/logs/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_import_log_detail_requires_admin(self, client, test_db):
        r = client.get("/api/admin/imports/logs/1")
        assert r.status_code == 401

    def test_import_log_detail_returns_log(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        # Seed an ImportLog directly so the detail endpoint has something to return
        from models import ImportLog
        log = ImportLog(
            file_name="test_import.xlsx",
            total_rows=5,
            imported_count=4,
            updated_count=0,
            skipped_count=0,
            errors_json=[{"row": 2, "field": "email", "error": "invalid"}],
        )
        test_db.add(log)
        test_db.commit()
        test_db.refresh(log)
        r = client.get(
            f"/api/admin/imports/logs/{log.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == log.id
        assert data["filename"] == "test_import.xlsx"
        assert data["error_count"] == 1
        assert data["status"] == "PARTIAL"
        assert len(data["errors"]) == 1

    def test_serialize_import_log_status_failed(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        from models import ImportLog
        log = ImportLog(
            file_name="failed_import.xlsx",
            total_rows=3,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            errors_json=[{"row": 1, "error": "bad data"}, {"row": 2, "error": "bad data"}],
        )
        test_db.add(log)
        test_db.commit()
        test_db.refresh(log)
        r = client.get(
            f"/api/admin/imports/logs/{log.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "FAILED"


class TestImportErrorReport:
    def test_error_report_endpoint_uses_post(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        errors = [{"row_number": 1, "field": "email", "error_code": "INVALID_EMAIL", "message": "Bad email"}]
        r = client.post(
            "/api/admin/users/import-csv/error-report",
            json={"errors": errors},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_get_error_report_is_rejected(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        r = client.get(
            "/api/admin/users/import-csv/error-report?errors=[]",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 405
