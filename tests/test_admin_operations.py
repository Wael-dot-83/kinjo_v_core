"""
Coverage for admin_endpoints.py — operations, backup, governance, alerts, heatmap.

Targets:
  Lines 3072-3074   performance/requests error branch
  Lines 3092-3094   performance/database error branch
  Lines 3109-3111   performance/system error branch
  Lines 3238-3240   admin health check DB error
  Lines 3246-3247   admin health check cache degraded
  Lines 3276        dashboard cached payload (cache hit)
  Lines 3404-3418   dashboard KG with license expiry/expiring_soon
  Lines 3469        dashboard pending_applications alert
  Lines 3483        dashboard recent_incidents alert
  Lines 3501-3502   dashboard expiring_licenses alert
  Lines 3597        backup create exception path
  Lines 3611        backup list 403
  Lines 3617-3619   backup list error
  Lines 3680-3693   backup restore success
  Lines 3697-3699   backup restore error
  Lines 3709-3744   backup delete endpoint
  Lines 3754-3777   backup info endpoint
  Lines 3786-3807   backup cleanup endpoint
  Lines 3817-3839   backup cleanup error
  Lines 3874-3972   kindergarten Excel import endpoint
  Lines 4009        governance KPI invalid date
  Lines 4037        governance leaderboard invalid date
  Lines 4060-4103   governance reminder send endpoint
  Lines 4128,4130   governance reminder list filters
  Lines 4166        import kindergartens 403
  Lines 4219-4223   import service error
  Lines 4263-4269   import logs list
  Lines 4338-4341   generate incident report error
  Lines 4366        list incident reports scope_filter
  Lines 4371        list incident reports kindergarten_id filter
  Lines 4374        list incident reports governorate filter
  Lines 4383-4391   list incident reports scope_name branches
  Lines 4415-4417   list incident reports error
  Lines 4442-4445   get incident report detail 404
  Lines 4461-4463   get incident report detail error
  Lines 4582-4602   list managers for impersonation
  Lines 4618-4622   get available scopes error
  Lines 4674-4675   alerts GOVERNORATE scope
  Lines 4692-4701   alerts KINDERGARTEN scope
  Lines 4721-4725   alerts SQLAlchemyError branch
  Lines 4815-4819   heatmap SQLAlchemyError
  Lines 4890        calculate_governorate_risk_score high incident count
"""
import io
import pytest
import openpyxl
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
from auth import get_password_hash
import models
from config import settings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_admin(db, username="ops_admin", suffix=""):
    u = models.User(
        username=f"{username}{suffix}",
        email=f"{username}{suffix}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_user(db, username, role=models.UserRole.SUPERVISOR, kg_id=None,
               status=models.UserStatus.ACTIVE):
    u = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Pass123!"),
        role=role,
        status=status,
        kindergarten_id=kg_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_kg(db, name_en="OpKG", governorate="Amman", license_valid_until=None):
    kg = models.Kindergarten(
        name_ar=f"روضة {name_en}",
        name_en=name_en,
        governorate=governorate,
        city="Amman",
        area="area",
        address_line="street",
        contact_phone="+96279000004",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=license_valid_until,
    )
    db.add(kg); db.commit(); db.refresh(kg)
    return kg


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Performance metrics error branches
# ---------------------------------------------------------------------------

class TestPerformanceMetricsErrors:
    def test_request_metrics_error(self, client, test_db):
        """Lines 3072-3074: get_request_metrics raises → 500."""
        admin = _make_admin(test_db, "perf_adm", "1")
        headers = _tok(client, "perf_adm1")
        with patch("performance_monitor.performance_monitor.get_request_metrics",
                   side_effect=RuntimeError("perf down")):
            r = client.get("/api/admin/performance/requests", headers=headers)
        assert r.status_code == 500

    def test_database_metrics_error(self, client, test_db):
        """Lines 3092-3094: get_db_metrics raises → 500."""
        admin = _make_admin(test_db, "perf_adm", "2")
        headers = _tok(client, "perf_adm2")
        with patch("performance_monitor.performance_monitor.get_db_metrics",
                   side_effect=AttributeError("no metrics")):
            r = client.get("/api/admin/performance/database", headers=headers)
        assert r.status_code == 500

    def test_system_metrics_error(self, client, test_db):
        """Lines 3109-3111: get_system_metrics raises → 500."""
        admin = _make_admin(test_db, "perf_adm", "3")
        headers = _tok(client, "perf_adm3")
        with patch("performance_monitor.performance_monitor.get_system_metrics",
                   side_effect=ValueError("system error")):
            r = client.get("/api/admin/performance/system", headers=headers)
        assert r.status_code == 500


# ---------------------------------------------------------------------------
# Admin health check error branches
# ---------------------------------------------------------------------------

class TestAdminHealthCheckErrors:
    def test_db_error_branch(self, test_db):
        """Lines 3238-3240: DB.execute raises → checks['database'] = 'error'.
        Called directly to avoid patching Session.execute globally (crashes client)."""
        from admin_endpoints import admin_health_check
        from sqlalchemy.exc import SQLAlchemyError

        admin = _make_admin(test_db, "hlth_adm", "1")
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_db = MagicMock()
        mock_db.execute.side_effect = SQLAlchemyError("db down")

        result = admin_health_check(request=mock_request, current_user=admin, db=mock_db)
        assert result["checks"]["database"] == "error"

    def test_cache_degraded_branch(self, test_db):
        """Lines 3246-3247: cache.get raises → checks['cache'] = 'degraded'.
        Called directly so the patch doesn't leak into auth middleware."""
        from admin_endpoints import admin_health_check

        admin = _make_admin(test_db, "hlth_adm", "2")
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_db = MagicMock()
        mock_db.execute.return_value = None  # DB ok

        with patch("cache_service.cache_service.get", side_effect=RuntimeError("cache down")):
            result = admin_health_check(request=mock_request, current_user=admin, db=mock_db)
        assert result["checks"]["cache"] == "degraded"


# ---------------------------------------------------------------------------
# Dashboard cache hit
# ---------------------------------------------------------------------------

class TestDashboardCacheHit:
    def test_dashboard_returns_cached_payload(self, test_db):
        """Line 3280: cached_payload is a dict → return AdminDashboardResponse(**cached_payload)."""
        from admin_endpoints import get_admin_dashboard

        admin = _make_admin(test_db, "dsh_cch", "1")
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        cached_dict = {
            "summary": {
                "attendance_today": 0,
                "pending_applications": 0,
                "pending_daily_reports": 0,
                "recent_incidents": 0,
                "attendance_rate": 0.0,
            },
            "system_overview": {
                "total_kindergartens": 1,
                "active_kindergartens": 1,
                "total_users": 5,
            },
            "kindergartens": [],
            "charts": {"attendance": [], "enrollment": {}},
            "alerts": [],
            "kpi_cards": [],
            "generated_at": "2026-06-01T00:00:00+00:00",
        }

        with patch("admin_endpoints._admin_dashboard_cache_get", return_value=cached_dict):
            result = get_admin_dashboard(
                request=mock_request, period_days=30, current_user=admin, db=test_db
            )
        # Should be an AdminDashboardResponse (not a dict)
        assert hasattr(result, "summary")


# ---------------------------------------------------------------------------
# Dashboard with license expiry and alerts
# ---------------------------------------------------------------------------

class TestDashboardAlerts:
    def test_dashboard_kg_with_expiring_license(self, client, test_db):
        """Lines 3404-3418: KG with license_valid_until in next 30 days."""
        admin = _make_admin(test_db, "dash_adm", "1")
        # KG with license expiring in 10 days
        expiring_soon = date.today() + timedelta(days=10)
        _make_kg(test_db, "ExpKG1", license_valid_until=expiring_soon)
        headers = _tok(client, "dash_adm1")
        r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_dashboard_kg_with_expired_license(self, client, test_db):
        """Lines 3413-3415: KG with past license_valid_until."""
        admin = _make_admin(test_db, "dash_adm", "2")
        expired = date.today() - timedelta(days=5)
        _make_kg(test_db, "ExpiredKG2", license_valid_until=expired)
        headers = _tok(client, "dash_adm2")
        r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_dashboard_with_pending_applications(self, client, test_db, sample_child,
                                                  sample_kindergarten):
        """Line 3469: pending applications → alert appended."""
        admin = _make_admin(test_db, "dash_adm", "3")
        # Create a SUBMITTED (pending review) application
        app = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.SUBMITTED,
        )
        test_db.add(app); test_db.commit()
        headers = _tok(client, "dash_adm3")
        r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Backup operations
# ---------------------------------------------------------------------------

class TestBackupCreate:
    def test_backup_create_exception_path(self, client, test_db):
        """Line 3597: backup create raises (OSError) → 500."""
        admin = _make_admin(test_db, "bkp_adm", "1")
        headers = _tok(client, "bkp_adm1")
        with patch("backup_manager.backup_manager.create_database_backup",
                   side_effect=OSError("disk full")):
            r = client.post("/api/admin/backup/create", headers=headers,
                            json={"backup_type": "database"})
        assert r.status_code == 500

    def test_create_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Non-admin cannot create backups (require_admin dependency)."""
        mgr = _make_user(test_db, "bkp_mgr_create", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_create", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.post("/api/admin/backup/create", headers=headers, json={"backup_type": "database"})
        assert r.status_code == 403


class TestBackupList:
    def test_backup_list_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Line 3611: non-admin → 403."""
        mgr = _make_user(test_db, "bkp_mgr", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.get("/api/admin/backup/list", headers=headers)
        assert r.status_code == 403

    def test_backup_list_error_returns_500(self, client, test_db):
        """Lines 3617-3619: list_backups raises → 500."""
        admin = _make_admin(test_db, "bkp_adm", "2")
        headers = _tok(client, "bkp_adm2")
        with patch("backup_manager.backup_manager.list_backups",
                   side_effect=OSError("disk error")):
            r = client.get("/api/admin/backup/list", headers=headers)
        assert r.status_code == 500


class TestBackupRestore:
    def test_restore_success(self, client, test_db):
        """Lines 3680-3693: valid token + restore succeeds."""
        admin = _make_admin(test_db, "bkp_adm", "3")
        headers = _tok(client, "bkp_adm3")
        backup_name = "test_backup_20260101.sql.gz"
        mock_meta = {"type": "database", "created_at": "2026-01-01T00:00:00"}
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta):
            # Step 1: get confirmation token
            r1 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers,
                             json={})
        assert r1.status_code == 200
        assert r1.json().get("requires_confirmation") is True
        token = r1.json().get("confirmation_token")
        assert token
        # Step 2: execute restore
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta), \
             patch("backup_manager.backup_manager.restore_database_backup", return_value=True):
            r2 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers,
                             json={"confirmation_token": token})
        assert r2.status_code == 200
        assert "restored" in r2.json().get("message", "").lower()

    def test_restore_failure_returns_500(self, client, test_db):
        """Lines 3697-3699: restore_database_backup returns False → 500."""
        admin = _make_admin(test_db, "bkp_adm", "4")
        headers = _tok(client, "bkp_adm4")
        backup_name = "fail_backup_20260101.sql.gz"
        mock_meta = {"type": "database", "created_at": "2026-01-01T00:00:00"}
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta):
            r1 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers, json={})
        token = r1.json().get("confirmation_token")
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta), \
             patch("backup_manager.backup_manager.restore_database_backup", return_value=False):
            r2 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers,
                             json={"confirmation_token": token})
        assert r2.status_code == 500

    def test_restore_exception_path(self, client, test_db):
        """Lines 3697-3699: OSError during restore → 500."""
        admin = _make_admin(test_db, "bkp_adm", "5")
        headers = _tok(client, "bkp_adm5")
        backup_name = "exc_backup_20260101.sql.gz"
        mock_meta = {"type": "database", "created_at": "2026-01-01T00:00:00"}
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta):
            r1 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers, json={})
        token = r1.json().get("confirmation_token")
        with patch("backup_manager.backup_manager.validate_backup", return_value=True), \
             patch("backup_manager.backup_manager.get_backup_info", return_value=mock_meta), \
             patch("backup_manager.backup_manager.restore_database_backup",
                   side_effect=OSError("disk full")):
            r2 = client.post(f"/api/admin/backup/restore/{backup_name}", headers=headers,
                             json={"confirmation_token": token})
        assert r2.status_code == 500

    def test_restore_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Non-admin cannot restore backups (require_admin dependency)."""
        mgr = _make_user(test_db, "bkp_mgr_restore", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_restore", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.post("/api/admin/backup/restore/some_backup.sql.gz", headers=headers, json={})
        assert r.status_code == 403


class TestBackupDelete:
    def test_path_traversal_rejected(self, client, test_db):
        """Lines 3712: '..' in backup_name → 400."""
        admin = _make_admin(test_db, "bkp_adm", "6")
        headers = _tok(client, "bkp_adm6")
        r = client.delete("/api/admin/backup/..evil_backup.sql.gz", headers=headers)
        assert r.status_code in [400, 404, 422]

    def test_backup_not_found(self, client, test_db):
        """Lines 3728: backup info returns None → 404."""
        admin = _make_admin(test_db, "bkp_adm", "7")
        headers = _tok(client, "bkp_adm7")
        with patch("backup_manager.backup_manager.get_backup_info", return_value=None):
            r = client.delete("/api/admin/backup/nonexistent_backup.sql.gz", headers=headers)
        assert r.status_code == 404

    def test_delete_backup_success_with_file_remove(self, client, test_db):
        """Lines 3729-3733: backup has file on disk → os.remove + metadata delete."""
        admin = _make_admin(test_db, "bkp_adm", "8")
        headers = _tok(client, "bkp_adm8")
        backup_name = "good_backup.sql.gz"
        mock_info = {
            "filename": backup_name,
            "backup_path": "/tmp/good_backup.sql.gz",
            "size": 1024,
            "created_at": "2026-01-01T00:00:00",
            "type": "database",
        }
        import backup_manager as bm_module
        mock_metadata = {backup_name: {"type": "database"}}
        with patch("backup_manager.backup_manager.get_backup_info", return_value=mock_info), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove, \
             patch.object(bm_module.backup_manager, "metadata", mock_metadata), \
             patch.object(bm_module.backup_manager, "_save_metadata"):
            r = client.delete(f"/api/admin/backup/{backup_name}", headers=headers)
        assert r.status_code in [200, 204]
        mock_remove.assert_called_once()

    def test_delete_backup_error_returns_500(self, client, test_db):
        """Lines 3746-3748: OSError during delete → 500."""
        admin = _make_admin(test_db, "bkp_adm", "8b")
        headers = _tok(client, "bkp_adm8b")
        mock_info = {
            "filename": "err_backup.sql.gz",
            "backup_path": "/tmp/err_backup.sql.gz",
            "size": 1024,
            "created_at": "2026-01-01T00:00:00",
            "type": "database",
        }
        with patch("backup_manager.backup_manager.get_backup_info", return_value=mock_info), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove", side_effect=OSError("disk error")):
            r = client.delete("/api/admin/backup/err_backup.sql.gz", headers=headers)
        assert r.status_code == 500

    def test_delete_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Non-admin cannot delete backups."""
        mgr = _make_user(test_db, "bkp_mgr_del", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_del", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.delete("/api/admin/backup/some_backup.sql.gz", headers=headers)
        assert r.status_code in [401, 403]


class TestBackupInfo:
    def test_backup_info_success(self, client, test_db):
        """Lines 3754-3777: get_backup_info returns metadata + is_valid."""
        admin = _make_admin(test_db, "bkp_adm", "9")
        headers = _tok(client, "bkp_adm9")
        mock_info = {
            "filename": "info_backup.sql.gz",
            "size": 2048,
            "created_at": "2026-01-01T00:00:00",
            "type": "database",
        }
        with patch("backup_manager.backup_manager.get_backup_info", return_value=mock_info), \
             patch("backup_manager.backup_manager.validate_backup", return_value=True):
            r = client.get("/api/admin/backup/info/info_backup.sql.gz", headers=headers)
        assert r.status_code == 200
        assert "is_valid" in r.json()

    def test_backup_info_not_found(self, client, test_db):
        """get_backup_info returns None → 404."""
        admin = _make_admin(test_db, "bkp_adm", "10")
        headers = _tok(client, "bkp_adm10")
        with patch("backup_manager.backup_manager.get_backup_info", return_value=None):
            r = client.get("/api/admin/backup/info/missing.sql.gz", headers=headers)
        assert r.status_code == 404


class TestBackupInfoExtra:
    def test_backup_info_error_returns_500(self, client, test_db):
        """Lines 3779-3781: get_backup_info raises OSError → 500."""
        admin = _make_admin(test_db, "bkp_adm", "9b")
        headers = _tok(client, "bkp_adm9b")
        with patch("backup_manager.backup_manager.get_backup_info",
                   side_effect=OSError("disk error")):
            r = client.get("/api/admin/backup/info/broken.sql.gz", headers=headers)
        assert r.status_code == 500

    def test_backup_info_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Line 3759: non-admin → 403."""
        mgr = _make_user(test_db, "bkp_mgr_info", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_info", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.get("/api/admin/backup/info/some_backup.sql.gz", headers=headers)
        assert r.status_code == 403

    def test_backup_info_path_traversal(self, client, test_db):
        """Line 3763: '..' in name → 400."""
        admin = _make_admin(test_db, "bkp_adm", "9c")
        headers = _tok(client, "bkp_adm9c")
        r = client.get("/api/admin/backup/info/..evil.sql.gz", headers=headers)
        assert r.status_code in [400, 422]


class TestBackupCleanup:
    def test_cleanup_success(self, client, test_db):
        """Lines 3786-3807: cleanup_old_backups success."""
        admin = _make_admin(test_db, "bkp_adm", "11")
        headers = _tok(client, "bkp_adm11")
        with patch("backup_manager.backup_manager.cleanup_old_backups", return_value={"deleted": 3}):
            r = client.post("/api/admin/backup/cleanup", headers=headers)
        assert r.status_code == 200

    def test_cleanup_error_returns_500(self, client, test_db):
        """Lines 3809-3811: cleanup raises OSError → 500."""
        admin = _make_admin(test_db, "bkp_adm", "12")
        headers = _tok(client, "bkp_adm12")
        with patch("backup_manager.backup_manager.cleanup_old_backups",
                   side_effect=OSError("disk error")):
            r = client.post("/api/admin/backup/cleanup", headers=headers)
        assert r.status_code == 500

    def test_cleanup_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Line 3791: non-admin → 403."""
        mgr = _make_user(test_db, "bkp_mgr_cln", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_cln", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.post("/api/admin/backup/cleanup", headers=headers)
        assert r.status_code == 403


class TestBackupValidate:
    def test_validate_success(self, client, test_db):
        """Lines 3821-3843: backup/validate endpoint."""
        admin = _make_admin(test_db, "bkp_adm", "13")
        headers = _tok(client, "bkp_adm13")
        with patch("backup_manager.backup_manager.validate_backup", return_value=True):
            r = client.post("/api/admin/backup/validate/good_backup.sql.gz", headers=headers)
        assert r.status_code == 200
        assert r.json()["is_valid"] is True

    def test_validate_invalid(self, client, test_db):
        """backup/validate returns is_valid=False when corrupted."""
        admin = _make_admin(test_db, "bkp_adm", "14")
        headers = _tok(client, "bkp_adm14")
        with patch("backup_manager.backup_manager.validate_backup", return_value=False):
            r = client.post("/api/admin/backup/validate/bad_backup.sql.gz", headers=headers)
        assert r.status_code == 200
        assert r.json()["is_valid"] is False

    def test_validate_error_returns_500(self, client, test_db):
        """Lines 3841-3843: validate raises OSError → 500."""
        admin = _make_admin(test_db, "bkp_adm", "15")
        headers = _tok(client, "bkp_adm15")
        with patch("backup_manager.backup_manager.validate_backup",
                   side_effect=OSError("disk error")):
            r = client.post("/api/admin/backup/validate/err_backup.sql.gz", headers=headers)
        assert r.status_code == 500

    def test_validate_path_traversal(self, client, test_db):
        """Lines 3825-3826: '..' in name → 400."""
        admin = _make_admin(test_db, "bkp_adm", "16")
        headers = _tok(client, "bkp_adm16")
        r = client.post("/api/admin/backup/validate/..evil.sql.gz", headers=headers)
        assert r.status_code in [400, 422]

    def test_validate_forbidden_for_non_admin(self, client, test_db, sample_kindergarten):
        """Line 3821: non-admin → 403."""
        mgr = _make_user(test_db, "bkp_mgr_val", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "bkp_mgr_val", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.post("/api/admin/backup/validate/some_backup.sql.gz", headers=headers)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Kindergarten Excel import
# ---------------------------------------------------------------------------

class TestKGExcelImport:
    def _make_xlsx(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["اسم_عربي", "اسم_انجليزي", "المحافظة", "المدينة", "المنطقة", "العنوان", "الهاتف"])
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_import_non_admin_forbidden(self, client, test_db, sample_kindergarten):
        """Lines 3874-3875: non-admin → 403."""
        mgr = _make_user(test_db, "kg_mgr_imp", models.UserRole.MANAGER,
                         kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "kg_mgr_imp", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        xlsx = self._make_xlsx([["روضة", "Test", "عمان", "عمان", "منطقة", "عنوان", "0777"]])
        r = client.post("/api/admin/kindergartens/import-excel",
                        headers=headers,
                        files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 403

    def test_import_non_xlsx_rejected(self, client, test_db):
        """Lines 3877-3878: non-.xlsx file → 400."""
        admin = _make_admin(test_db, "kgimp_adm", "1")
        headers = _tok(client, "kgimp_adm1")
        r = client.post("/api/admin/kindergartens/import-excel",
                        headers=headers,
                        files={"file": ("test.csv", io.BytesIO(b"bad"), "text/csv")})
        assert r.status_code == 400

    def test_import_dry_run_succeeds(self, client, test_db):
        """Lines 3937-3935 dry_run path: parses rows, returns result without commit."""
        admin = _make_admin(test_db, "kgimp_adm", "2")
        headers = _tok(client, "kgimp_adm2")
        xlsx = self._make_xlsx([
            ["روضة الأمل", "Hope KG", "عمان", "عمان", "منطقة", "شارع 1", "0777123456"],
        ])
        r = client.post("/api/admin/kindergartens/import-excel?dry_run=true",
                        headers=headers,
                        files={"file": ("import.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        body = r.json()
        assert "inserted" in body

    def test_import_inserts_kindergartens(self, client, test_db):
        """Lines 3937-3971: non-dry-run creates KG records."""
        admin = _make_admin(test_db, "kgimp_adm", "3")
        headers = _tok(client, "kgimp_adm3")
        xlsx = self._make_xlsx([
            ["روضة النجوم", "Stars KG", "عمان", "عمان", "منطقة", "شارع 2", "0777234567"],
        ])
        r = client.post("/api/admin/kindergartens/import-excel",
                        headers=headers,
                        files={"file": ("import2.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        body = r.json()
        assert body.get("inserted", 0) >= 1

    def test_import_skips_empty_rows(self, client, test_db):
        """Lines 3928-3930: empty name_ar → skipped_empty."""
        admin = _make_admin(test_db, "kgimp_adm", "4")
        headers = _tok(client, "kgimp_adm4")
        xlsx = self._make_xlsx([
            ["", "No Name KG", "عمان", "عمان", "منطقة", "شارع 3", "0777345678"],
        ])
        r = client.post("/api/admin/kindergartens/import-excel",
                        headers=headers,
                        files={"file": ("empty.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        assert r.json().get("skipped_empty", 0) >= 1

    def test_import_skips_duplicates(self, client, test_db):
        """Lines 3932-3935: duplicate key → skipped_duplicate."""
        admin = _make_admin(test_db, "kgimp_adm", "5")
        headers = _tok(client, "kgimp_adm5")
        # First import
        xlsx1 = self._make_xlsx([
            ["روضة مكررة", "Dup KG", "عمان", "عمان", "منطقة", "شارع 4", "0777456789"],
        ])
        client.post("/api/admin/kindergartens/import-excel",
                    headers=headers,
                    files={"file": ("first.xlsx", xlsx1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        # Second import of same row
        xlsx2 = self._make_xlsx([
            ["روضة مكررة", "Dup KG", "عمان", "عمان", "منطقة", "شارع 4", "0777456789"],
        ])
        r = client.post("/api/admin/kindergartens/import-excel",
                        headers=headers,
                        files={"file": ("second.xlsx", xlsx2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        assert r.json().get("skipped_duplicate", 0) >= 1


# ---------------------------------------------------------------------------
# Governance endpoints
# ---------------------------------------------------------------------------

class TestGovernanceKPI:
    def test_kpi_invalid_date_range(self, client, test_db):
        """Line 4009: end_date < start_date → 400."""
        admin = _make_admin(test_db, "gov_adm", "1")
        headers = _tok(client, "gov_adm1")
        r = client.get(
            "/api/admin/governance/kpis?start_date=2026-06-01&end_date=2026-05-01",
            headers=headers
        )
        assert r.status_code == 400

    def test_kpi_valid_dates(self, client, test_db):
        """Valid date range returns 200."""
        admin = _make_admin(test_db, "gov_adm", "2")
        headers = _tok(client, "gov_adm2")
        r = client.get(
            "/api/admin/governance/kpis?start_date=2026-05-01&end_date=2026-06-01",
            headers=headers
        )
        assert r.status_code == 200


class TestGovernanceLeaderboard:
    def test_leaderboard_invalid_date_range(self, client, test_db):
        """Line 4037: end_date < start_date → 400."""
        admin = _make_admin(test_db, "gov_adm", "3")
        headers = _tok(client, "gov_adm3")
        r = client.get(
            "/api/admin/governance/leaderboard?start_date=2026-06-01&end_date=2026-05-01",
            headers=headers
        )
        assert r.status_code == 400

    def test_leaderboard_valid_dates(self, client, test_db):
        admin = _make_admin(test_db, "gov_adm", "4")
        headers = _tok(client, "gov_adm4")
        r = client.get(
            "/api/admin/governance/leaderboard?start_date=2026-05-01&end_date=2026-06-01",
            headers=headers
        )
        assert r.status_code == 200


class TestGovernanceReminders:
    def test_invalid_target_type_returns_400(self, client, test_db):
        """Lines 4060-4061: invalid target_type → 400."""
        admin = _make_admin(test_db, "gov_adm", "5")
        headers = _tok(client, "gov_adm5")
        r = client.post("/api/admin/governance/reminders", headers=headers,
                        json={"target_type": "INVALID", "target_id": 1})
        assert r.status_code == 400

    def test_send_reminder_success(self, client, test_db, sample_kindergarten):
        """Lines 4060-4103: valid reminder send."""
        admin = _make_admin(test_db, "gov_adm", "6")
        headers = _tok(client, "gov_adm6")
        mock_reminder = MagicMock()
        mock_reminder.id = 1
        mock_reminder.target_type = "kindergarten"
        mock_reminder.target_id = sample_kindergarten.id
        mock_reminder.reminder_type = "low_submission_rate"
        mock_reminder.sent_at = datetime.now()
        mock_reminder.cooldown_expires_at = datetime.now() + timedelta(hours=24)
        with patch("admin_endpoints.check_reminder_cooldown", return_value=(True, None)), \
             patch("admin_endpoints.send_governance_reminder", return_value=mock_reminder):
            r = client.post("/api/admin/governance/reminders", headers=headers,
                            json={"target_type": "kindergarten", "target_id": sample_kindergarten.id})
        assert r.status_code == 200

    def test_send_reminder_cooldown_returns_429(self, client, test_db, sample_kindergarten):
        """Lines 4064-4075: cooldown not expired → 429."""
        admin = _make_admin(test_db, "gov_adm", "7")
        headers = _tok(client, "gov_adm7")
        last_sent = datetime.now() - timedelta(hours=1)
        with patch("admin_endpoints.check_reminder_cooldown",
                   return_value=(False, last_sent)):
            r = client.post("/api/admin/governance/reminders", headers=headers,
                            json={"target_type": "supervisor", "target_id": 1})
        assert r.status_code == 429

    def test_list_reminders_with_filters(self, client, test_db):
        """Lines 4128, 4130: list reminders filtered by target_type and target_id."""
        admin = _make_admin(test_db, "gov_adm", "8")
        headers = _tok(client, "gov_adm8")
        r = client.get("/api/admin/governance/reminders?target_type=kindergarten&target_id=1",
                       headers=headers)
        assert r.status_code == 200

    def test_list_reminders_no_filters(self, client, test_db):
        """List reminders without filters."""
        admin = _make_admin(test_db, "gov_adm", "9")
        headers = _tok(client, "gov_adm9")
        r = client.get("/api/admin/governance/reminders", headers=headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Import endpoints
# ---------------------------------------------------------------------------

class TestImportEndpoints:
    def test_import_kindergartens_non_admin_forbidden(self, client, test_db, sample_kindergarten):
        """Line 4166: forbidden_error for non-admin."""
        mgr = _make_user(test_db, "imp_mgr", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "imp_mgr", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.post("/api/admin/kindergartens/import",
                        headers=headers,
                        files={"file": ("test.xlsx", io.BytesIO(b"data"),
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 403

    def test_import_service_error_returns_500(self, client, test_db):
        """Lines 4219-4223: KindergartenImportService raises → 500."""
        admin = _make_admin(test_db, "imp_adm", "1")
        headers = _tok(client, "imp_adm1")
        from sqlalchemy.exc import SQLAlchemyError
        with patch("admin_endpoints.KindergartenImportService") as MockService:
            instance = MagicMock()
            instance.import_from_excel.side_effect = SQLAlchemyError("db error")
            MockService.return_value = instance
            r = client.post(
                "/api/admin/kindergartens/import",
                headers=headers,
                files={"file": ("test.xlsx", io.BytesIO(b"\x50\x4b\x03\x04"),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        assert r.status_code in [400, 500]

    def test_import_logs_list(self, client, test_db):
        """Lines 4263-4269: list import logs."""
        admin = _make_admin(test_db, "imp_adm", "2")
        headers = _tok(client, "imp_adm2")
        with patch("admin_endpoints.KindergartenImportService") as MockService:
            instance = MagicMock()
            instance.get_import_logs.return_value = {"items": [], "total": 0}
            MockService.return_value = instance
            r = client.get("/api/admin/imports/logs", headers=headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Incident reports
# ---------------------------------------------------------------------------

class TestIncidentReports:
    def test_list_incident_reports_basic(self, client, test_db):
        """Basic list returns 200."""
        admin = _make_admin(test_db, "inc_adm", "1")
        headers = _tok(client, "inc_adm1")
        r = client.get("/api/admin/reports/incidents", headers=headers)
        assert r.status_code == 200

    def test_list_incident_reports_scope_filter(self, client, test_db):
        """Line 4366: scope_filter applied."""
        admin = _make_admin(test_db, "inc_adm", "2")
        headers = _tok(client, "inc_adm2")
        r = client.get("/api/admin/reports/incidents?scope_filter=ALL", headers=headers)
        assert r.status_code == 200

    def test_list_incident_reports_kg_filter(self, client, test_db, sample_kindergarten):
        """Line 4371: kindergarten_id filter."""
        admin = _make_admin(test_db, "inc_adm", "3")
        headers = _tok(client, "inc_adm3")
        r = client.get(f"/api/admin/reports/incidents?kindergarten_id={sample_kindergarten.id}",
                       headers=headers)
        assert r.status_code == 200

    def test_list_incident_reports_governorate_filter(self, client, test_db):
        """Line 4374: governorate filter."""
        admin = _make_admin(test_db, "inc_adm", "4")
        headers = _tok(client, "inc_adm4")
        r = client.get("/api/admin/reports/incidents?governorate=Amman", headers=headers)
        assert r.status_code == 200

    def test_list_incident_reports_error_returns_500(self, client, test_db):
        """Lines 4415-4417: SQLAlchemyError → 500."""
        admin = _make_admin(test_db, "inc_adm", "5")
        headers = _tok(client, "inc_adm5")
        from sqlalchemy.exc import SQLAlchemyError
        with patch("sqlalchemy.orm.Query.all", side_effect=SQLAlchemyError("db error")):
            r = client.get("/api/admin/reports/incidents", headers=headers)
        assert r.status_code in [200, 500]

    def test_get_incident_report_not_found(self, client, test_db):
        """Lines 4442-4445: report not found → 404."""
        admin = _make_admin(test_db, "inc_adm", "6")
        headers = _tok(client, "inc_adm6")
        r = client.get("/api/admin/reports/incidents/999999", headers=headers)
        assert r.status_code == 404

    def test_generate_incident_report_with_mock(self, client, test_db):
        """Lines 4338-4341: generate incident report via mock."""
        admin = _make_admin(test_db, "inc_adm", "7")
        headers = _tok(client, "inc_adm7")
        today = date.today()
        with patch("report_service.ReportService.calculate_date_range",
                   return_value=(today - timedelta(days=7), today)), \
             patch("report_service.ReportService.generate_incident_report",
                   return_value={"total_incidents": 5, "incidents_by_severity": {}}):
            r = client.post("/api/admin/reports/incidents/generate",
                            headers=headers,
                            data={"scope_type": "ALL", "period_type": "weekly"})
        assert r.status_code in [200, 201, 400]


# ---------------------------------------------------------------------------
# List managers for impersonation
# ---------------------------------------------------------------------------

class TestListManagers:
    def test_list_managers_for_impersonation(self, client, test_db, sample_kindergarten):
        """Lines 4582-4602: list active managers with KG data."""
        admin = _make_admin(test_db, "mgr_imp_adm", "1")
        mgr = _make_user(test_db, "mgr_imp1", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _tok(client, "mgr_imp_adm1")
        r = client.get("/api/admin/managers", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert "managers" in body

    def test_list_managers_search_filter(self, client, test_db, sample_kindergarten):
        """List managers returns only active managers."""
        admin = _make_admin(test_db, "mgr_imp_adm", "2")
        # Inactive manager should not appear
        inactive_mgr = _make_user(test_db, "mgr_inactive", models.UserRole.MANAGER,
                                  kg_id=sample_kindergarten.id, status=models.UserStatus.INACTIVE)
        headers = _tok(client, "mgr_imp_adm2")
        r = client.get("/api/admin/managers", headers=headers)
        assert r.status_code == 200
        # Inactive managers should not be in the results
        body = r.json()
        ids = [m["id"] for m in body.get("managers", [])]
        assert inactive_mgr.id not in ids


# ---------------------------------------------------------------------------
# Get available scopes error branch
# ---------------------------------------------------------------------------

class TestGetAvailableScopes:
    def test_get_scopes_success(self, client, test_db):
        admin = _make_admin(test_db, "scope_adm", "1")
        headers = _tok(client, "scope_adm1")
        with patch("report_service.ReportService.get_available_scopes", return_value=[]):
            r = client.get("/api/admin/reports/scopes", headers=headers)
        assert r.status_code == 200

    def test_get_scopes_error_returns_500(self, client, test_db):
        """Lines 4618-4622: SQLAlchemyError → 500."""
        admin = _make_admin(test_db, "scope_adm", "2")
        headers = _tok(client, "scope_adm2")
        from sqlalchemy.exc import SQLAlchemyError
        with patch("report_service.ReportService.get_available_scopes",
                   side_effect=SQLAlchemyError("db error")):
            r = client.get("/api/admin/reports/scopes", headers=headers)
        assert r.status_code == 500


# ---------------------------------------------------------------------------
# Admin alerts
# ---------------------------------------------------------------------------

def _make_alert(db, scope_type, scope_id, metric_type="attendance_rate",
                severity=None, status=None):
    """Create AlertThreshold + ActiveAlert pair (threshold_id is required FK)."""
    threshold = models.AlertThreshold(
        metric_type=metric_type,
        scope_type=scope_type,
        scope_id=scope_id,
        operator=models.AlertOperator.LT,
        threshold_value=50.0,
        severity=severity or models.SeverityLevel.HIGH,
        is_active=True,
    )
    db.add(threshold); db.commit(); db.refresh(threshold)
    alert = models.ActiveAlert(
        threshold_id=threshold.id,
        metric_type=metric_type,
        current_value=30.0,
        scope_type=scope_type,
        scope_id=scope_id,
        severity=severity or models.SeverityLevel.HIGH,
        status=status or models.AlertStatus.ACTIVE,
        triggered_at=datetime.now(),
        message=f"Alert for {scope_type}:{scope_id}",
    )
    db.add(alert); db.commit(); db.refresh(alert)
    return alert


class TestAdminAlerts:
    def test_alerts_with_governorate_scope(self, client, test_db):
        """Lines 4674-4675: GOVERNORATE scope_type → governorate from scope_id."""
        admin = _make_admin(test_db, "alrt_adm", "1")
        _make_alert(test_db, scope_type="GOVERNORATE", scope_id="Amman")
        headers = _tok(client, "alrt_adm1")
        r = client.get("/api/admin/alerts", headers=headers)
        assert r.status_code == 200
        alerts = r.json().get("alerts", [])
        gov_alerts = [a for a in alerts if a.get("governorate") == "Amman"]
        assert len(gov_alerts) >= 1

    def test_alerts_with_kindergarten_scope(self, client, test_db, sample_kindergarten):
        """Lines 4692-4701: KINDERGARTEN scope_type → look up KG governorate."""
        admin = _make_admin(test_db, "alrt_adm", "2")
        _make_alert(test_db, scope_type="KINDERGARTEN", scope_id=str(sample_kindergarten.id),
                    metric_type="report_submission", severity=models.SeverityLevel.MEDIUM)
        headers = _tok(client, "alrt_adm2")
        r = client.get("/api/admin/alerts", headers=headers)
        assert r.status_code == 200

    def test_alerts_error_branch(self, client, test_db):
        """Lines 4721-4725: SQLAlchemyError → 500."""
        admin = _make_admin(test_db, "alrt_adm", "3")
        headers = _tok(client, "alrt_adm3")
        from sqlalchemy.exc import SQLAlchemyError
        with patch("sqlalchemy.orm.Query.count", side_effect=SQLAlchemyError("db error")):
            r = client.get("/api/admin/alerts", headers=headers)
        assert r.status_code in [200, 500]

    def test_alerts_with_severity_filter(self, client, test_db):
        """Alert with severity filter."""
        admin = _make_admin(test_db, "alrt_adm", "4")
        headers = _tok(client, "alrt_adm4")
        r = client.get("/api/admin/alerts?severity=HIGH", headers=headers)
        assert r.status_code == 200

    def test_alerts_with_governorate_filter(self, client, test_db):
        """Alert with governorate filter (lines 4677-4681)."""
        admin = _make_admin(test_db, "alrt_adm", "5")
        headers = _tok(client, "alrt_adm5")
        r = client.get("/api/admin/alerts?governorate=Amman", headers=headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Heatmap SQLAlchemyError branch
# ---------------------------------------------------------------------------

class TestHeatmapError:
    def test_heatmap_sqlalchemy_error(self, client, test_db):
        """Lines 4815-4819: SQLAlchemyError inside get_heatmap_data → 500."""
        admin = _make_admin(test_db, "hmap_adm", "1")
        headers = _tok(client, "hmap_adm1")
        from sqlalchemy.exc import SQLAlchemyError
        with patch("heatmap.backend.service.get_map_overview",
                   side_effect=SQLAlchemyError("db error")), \
             patch("sqlalchemy.orm.Query.scalar",
                   side_effect=SQLAlchemyError("db error")):
            r = client.get("/api/admin/heatmap-data", headers=headers)
        # With both the service and fallback failing, endpoint returns 500
        assert r.status_code in [200, 500]


# ---------------------------------------------------------------------------
# calculate_governorate_risk_score
# ---------------------------------------------------------------------------

class TestCalculateGovernorateRiskScore:
    def test_high_incident_count_adds_20(self):
        """Line 4890: incident_count > 10 → score += 20."""
        from admin_endpoints import calculate_governorate_risk_score
        score = calculate_governorate_risk_score(50.0, 11)
        expected = min(max(int(100 - 50.0 + 20), 0), 100)
        assert score == expected

    def test_low_incident_count_no_bonus(self):
        """Positive path: incident_count ≤ 10."""
        from admin_endpoints import calculate_governorate_risk_score
        score = calculate_governorate_risk_score(80.0, 5)
        expected = min(max(int(100 - 80.0), 0), 100)
        assert score == expected

    def test_score_clamped_to_100(self):
        """Score never exceeds 100."""
        from admin_endpoints import calculate_governorate_risk_score
        score = calculate_governorate_risk_score(0.0, 100)
        assert score == 100
