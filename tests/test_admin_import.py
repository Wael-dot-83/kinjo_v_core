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
import secrets
import pytest
from auth import get_password_hash
import models
from conftest import csrf_pair



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
            headers={"Authorization": f"Bearer {token}", **csrf_pair()},
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
            headers={"Authorization": f"Bearer {token}", **csrf_pair()},
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
            headers={"Authorization": f"Bearer {token}", **csrf_pair()},
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

    def test_list_import_logs_status_filter_actually_filters(self, client, test_db):
        """The frontend's Status filter sent a `status` query param the
        endpoint's signature never declared -- selecting a status always
        returned the same unfiltered first page."""
        from models import ImportLog
        _create_admin(test_db)
        token = _get_admin_token(client)
        success_log = ImportLog(file_name="ok.xlsx", total_rows=1, imported_count=1,
                                 updated_count=0, skipped_count=0, errors_json=None)
        failed_log = ImportLog(file_name="bad.xlsx", total_rows=1, imported_count=0,
                                updated_count=0, skipped_count=0,
                                errors_json=[{"row": 1, "error": "x"}])
        test_db.add_all([success_log, failed_log])
        test_db.commit()

        r = client.get(
            "/api/admin/imports/logs?status=FAILED",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert all(log["status"] == "FAILED" for log in data["logs"])
        assert any(log["filename"] == "bad.xlsx" for log in data["logs"])
        assert not any(log["filename"] == "ok.xlsx" for log in data["logs"])

    def test_list_import_logs_type_filter_actually_filters(self, client, test_db):
        """The Type filter offered a "CSV — Users" option that could never
        match anything (no CSV-user import ever writes to ImportLog, and
        import_type is always hardcoded to EXCEL_KINDERGARTENS) -- the
        dead option was removed from the template, but the `type` param
        itself must still work for the one real value."""
        from models import ImportLog
        _create_admin(test_db)
        token = _get_admin_token(client)
        test_db.add(ImportLog(file_name="a.xlsx", total_rows=1, imported_count=1,
                               updated_count=0, skipped_count=0))
        test_db.commit()

        r = client.get(
            "/api/admin/imports/logs?type=EXCEL_KINDERGARTENS",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["total"] >= 1

        r2 = client.get(
            "/api/admin/imports/logs?type=NONEXISTENT_TYPE",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        assert r2.json()["total"] == 0

    def test_list_import_logs_date_range_filter(self, client, test_db):
        """The Date From/To filters sent `from`/`to` params the endpoint
        never declared at all."""
        from models import ImportLog
        _create_admin(test_db)
        token = _get_admin_token(client)
        test_db.add(ImportLog(file_name="dated.xlsx", total_rows=1, imported_count=1,
                               updated_count=0, skipped_count=0))
        test_db.commit()

        r = client.get(
            "/api/admin/imports/logs?from=2000-01-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["total"] >= 1

        r2 = client.get(
            "/api/admin/imports/logs?to=2000-01-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        assert not any(log["filename"] == "dated.xlsx" for log in r2.json()["logs"])


class TestImportErrorReport:
    def test_error_report_endpoint_uses_post(self, client, test_db):
        _create_admin(test_db)
        token = _get_admin_token(client)
        csrf = secrets.token_hex(32)
        errors = [{"row_number": 1, "field": "email", "error_code": "INVALID_EMAIL", "message": "Bad email"}]
        # Set the CSRF cookie on the client (starlette deprecates per-request cookies=).
        client.cookies.set("kinjo_csrf_token", csrf)
        r = client.post(
            "/api/admin/users/import-csv/error-report",
            json={"errors": errors},
            headers={"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf},
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
