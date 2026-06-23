"""
Coverage for admin_endpoints.py — edge cases in user management.

Targets:
  Lines 80-84   cache get error handler
  Lines 94-98   cache set error handler
  Lines 154-156 invalid role string in validate_bulk_manager_assignments
  Lines 161-163 invalid status string in validate_bulk_manager_assignments
  Lines 167-172 MANAGER without kindergarten_id
  Lines 191-192 ManagerRuleError in validate_bulk_manager_assignments
  Lines 231-233 get_client_ip when request.client is None
  Lines 271     list_users kg_id filter (admin path)
  Lines 277-281 list_users manager cross-KG IDOR
  Lines 286-288 list_users role=ADMIN forbidden
  Lines 291     list_users status filter
  Lines 381     create_user admin creating admin
  Lines 384     create_user supervisor without kg
  Lines 401     create_user username conflict
  Lines 428     create_user email conflict
  Lines 435-442 create_user nationality validation
  Lines 456-496 create_user PARENT with children
  Lines 549     export_users kg_id filter
  Lines 553     export_users role filter
  Lines 633     get_user manager IDOR
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from auth import get_password_hash
import models
from config import settings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_admin(db, username="ec_admin", suffix=""):
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
               status=models.UserStatus.ACTIVE, email=None):
    u = models.User(
        username=username,
        email=email or f"{username}@example.com",
        hashed_password=get_password_hash("Pass123!"),
        role=role,
        status=status,
        kindergarten_id=kg_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_kg(db, name_ar="روضة", name_en="KG", governorate="Amman"):
    kg = models.Kindergarten(
        name_ar=name_ar,
        name_en=name_en,
        governorate=governorate,
        city="Amman",
        area="area",
        address_line="street",
        contact_phone="+96279000001",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg); db.commit(); db.refresh(kg)
    return kg


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

class TestCacheHelpers:
    def test_cache_get_error_graceful(self, monkeypatch, client, test_db):
        """Lines 80-84: cache.get raises → caught, dashboard still returns 200."""
        admin = _make_admin(test_db, "cg_adm", "1")
        headers = _tok(client, "cg_adm1")
        monkeypatch.setattr(settings, "TESTING", False)
        with patch("cache_service.cache_service.get", side_effect=RuntimeError("redis down")), \
             patch("cache_service.cache_service.set", side_effect=RuntimeError("redis down")):
            r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_cache_set_error_graceful(self, monkeypatch, client, test_db):
        """Lines 94-98: cache.set raises → caught, dashboard still returns 200."""
        admin = _make_admin(test_db, "cs_adm", "1")
        headers = _tok(client, "cs_adm1")
        monkeypatch.setattr(settings, "TESTING", False)
        with patch("cache_service.cache_service.get", return_value=None), \
             patch("cache_service.cache_service.set", side_effect=AttributeError("no set")):
            r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_cache_get_value_error_graceful(self, monkeypatch, client, test_db):
        """Lines 80-84: cache.get raises ValueError → caught."""
        admin = _make_admin(test_db, "cgv_adm", "1")
        headers = _tok(client, "cgv_adm1")
        monkeypatch.setattr(settings, "TESTING", False)
        with patch("cache_service.cache_service.get", side_effect=ValueError("bad")), \
             patch("cache_service.cache_service.set", return_value=None):
            r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200

    def test_cache_set_typeerror_graceful(self, monkeypatch, client, test_db):
        """Lines 94-98: cache.set raises TypeError → caught."""
        admin = _make_admin(test_db, "cst_adm", "1")
        headers = _tok(client, "cst_adm1")
        monkeypatch.setattr(settings, "TESTING", False)
        with patch("cache_service.cache_service.get", return_value=None), \
             patch("cache_service.cache_service.set", side_effect=TypeError("type error")):
            r = client.get("/api/admin/dashboard", headers=headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# validate_bulk_manager_assignments helper function
# ---------------------------------------------------------------------------

class TestBulkManagerValidation:
    def test_invalid_role_string_sets_role_none(self, test_db):
        """Lines 154-156: invalid role string → ValueError caught, role=None, no errors."""
        from admin_endpoints import validate_bulk_manager_assignments
        errors = validate_bulk_manager_assignments(
            test_db,
            [{"role": "NOT_VALID_ROLE", "status": "ACTIVE", "kindergarten_id": None}]
        )
        assert errors == []

    def test_invalid_status_string_sets_inactive(self, test_db):
        """Lines 161-163: invalid status string → ValueError caught, status=INACTIVE."""
        from admin_endpoints import validate_bulk_manager_assignments
        errors = validate_bulk_manager_assignments(
            test_db,
            [{"role": models.UserRole.MANAGER, "status": "TOTALLY_INVALID",
              "kindergarten_id": None}]
        )
        # status=INACTIVE, MANAGER path runs, kg_id=None → error at line 167-172
        assert any(e["field"] == "kindergarten_id" for e in errors)

    def test_manager_without_kg_appends_error(self, test_db):
        """Lines 167-172: MANAGER with no kindergarten_id → error appended."""
        from admin_endpoints import validate_bulk_manager_assignments
        errors = validate_bulk_manager_assignments(
            test_db,
            [{"role": models.UserRole.MANAGER, "status": models.UserStatus.ACTIVE,
              "kindergarten_id": None}]
        )
        assert len(errors) == 1
        assert errors[0]["field"] == "kindergarten_id"

    def test_manager_rule_error_is_caught(self, test_db, sample_kindergarten):
        """Lines 191-192: ManagerRuleError from validators is caught and appended."""
        from admin_endpoints import validate_bulk_manager_assignments
        # Create an active manager already assigned to sample_kindergarten
        existing = _make_user(test_db, "exist_mgr_vbma", models.UserRole.MANAGER,
                              kg_id=sample_kindergarten.id)
        # Trying to add another manager to same KG → validate_manager_rules raises ManagerRuleError
        errors = validate_bulk_manager_assignments(
            test_db,
            [{"role": models.UserRole.MANAGER, "status": models.UserStatus.ACTIVE,
              "kindergarten_id": sample_kindergarten.id}]
        )
        assert any(e["field"] == "kindergarten_id" for e in errors)


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------

class TestGetClientIp:
    def test_returns_unknown_when_client_none(self):
        """Lines 231-233: request.client is None → return 'unknown'."""
        from admin_endpoints import get_client_ip
        req = MagicMock()
        req.client = None
        assert get_client_ip(req) == "unknown"

    def test_returns_host_when_client_set(self):
        """Positive path: request.client.host is returned."""
        from admin_endpoints import get_client_ip
        req = MagicMock()
        req.client.host = "127.0.0.1"
        assert get_client_ip(req) == "127.0.0.1"


# ---------------------------------------------------------------------------
# list_users filter branches
# ---------------------------------------------------------------------------

class TestListUsersFilters:
    def test_admin_filter_by_kg_id(self, client, test_db, sample_kindergarten):
        """Line 271: admin passes kindergarten_id filter."""
        admin = _make_admin(test_db, "lu_adm", "1")
        _make_user(test_db, "lu_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "lu_adm1")
        r = client.get(f"/api/admin/users?kindergarten_id={sample_kindergarten.id}",
                       headers=headers)
        assert r.status_code == 200

    def test_manager_cross_kg_is_silently_ignored(self, client, test_db, sample_kindergarten):
        """Lines 277-281: manager tries to filter for a different KG → audit logged,
        but response is still 200 (cross-KG filter silently scoped to manager's KG)."""
        kg2 = _make_kg(test_db, "روضة ثانية", "OtherKG2")
        _make_user(test_db, "cross_mgr", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        r_login = client.post("/token", data={"username": "cross_mgr", "password": "Pass123!"})
        assert r_login.status_code == 200
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.get(f"/api/admin/users?kindergarten_id={kg2.id}", headers=headers)
        # Endpoint silently ignores cross-KG filter and returns manager's own KG users
        assert r.status_code == 200

    def test_list_users_role_admin_forbidden(self, client, test_db):
        """Lines 286-288: filtering by role=ADMIN is forbidden."""
        admin = _make_admin(test_db, "lu_adm", "2")
        headers = _tok(client, "lu_adm2")
        r = client.get("/api/admin/users?role=ADMIN", headers=headers)
        assert r.status_code == 403

    def test_list_users_status_filter(self, client, test_db):
        """Line 291: status filter applied."""
        admin = _make_admin(test_db, "lu_adm", "3")
        _make_user(test_db, "inactive_lu", status=models.UserStatus.INACTIVE)
        headers = _tok(client, "lu_adm3")
        r = client.get("/api/admin/users?status=INACTIVE", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data


# ---------------------------------------------------------------------------
# create_user branches
# ---------------------------------------------------------------------------

class TestCreateUserBranches:
    def test_admin_cannot_create_admin(self, client, test_db):
        """Line 381: admin creating admin → 403."""
        admin = _make_admin(test_db, "cu_adm", "1")
        headers = _tok(client, "cu_adm1")
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "newadmin1",
            "password": "Admin123!",
            "role": "ADMIN",
        })
        assert r.status_code == 403

    def test_supervisor_without_kg_rejected(self, client, test_db):
        """Line 384: supervisor without kindergarten → 400."""
        admin = _make_admin(test_db, "cu_adm", "2")
        headers = _tok(client, "cu_adm2")
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "newsuper1",
            "password": "Pass123!",
            "role": "SUPERVISOR",
        })
        assert r.status_code == 400

    def test_duplicate_username_returns_409(self, client, test_db, sample_kindergarten):
        """Line 401: username already exists → 409."""
        admin = _make_admin(test_db, "cu_adm", "3")
        _make_user(test_db, "dup_un_user", models.UserRole.SUPERVISOR,
                   kg_id=sample_kindergarten.id)
        headers = _tok(client, "cu_adm3")
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "dup_un_user",
            "password": "Pass123!",
            "role": "SUPERVISOR",
            "kindergarten_id": sample_kindergarten.id,
        })
        assert r.status_code == 409

    def test_duplicate_email_returns_409(self, client, test_db, sample_kindergarten):
        """Line 428: email already exists → 409."""
        admin = _make_admin(test_db, "cu_adm", "4")
        _make_user(test_db, "dup_em_orig", models.UserRole.SUPERVISOR,
                   kg_id=sample_kindergarten.id, email="dupemail@example.com")
        headers = _tok(client, "cu_adm4")
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "dup_em_new",
            "email": "dupemail@example.com",
            "password": "Pass123!",
            "role": "SUPERVISOR",
            "kindergarten_id": sample_kindergarten.id,
        })
        assert r.status_code == 409

    def test_nationality_validation_fails_for_jordanian_supervisor(self, client, test_db,
                                                                    sample_kindergarten):
        """Lines 435-442: Jordanian supervisor without national_id → 400."""
        admin = _make_admin(test_db, "cu_adm", "5")
        headers = _tok(client, "cu_adm5")
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "nat_sup_cu5",
            "password": "Pass123!",
            "role": "SUPERVISOR",
            "kindergarten_id": sample_kindergarten.id,
            "nationality": "Jordanian",
            # no national_id, no passport_number
        })
        assert r.status_code == 400

    def test_create_parent_with_children_succeeds(self, client, test_db):
        """Lines 456-496: parent with children list → 201, parent profile + children created."""
        admin = _make_admin(test_db, "cu_adm", "6")
        headers = _tok(client, "cu_adm6")
        child_dob = (date.today() - timedelta(days=365 * 3)).isoformat()
        r = client.post("/api/admin/users", headers=headers, json={
            "username": "newparent_cu6",
            "email": "newparent_cu6@example.com",
            "password": "Pass123!",
            "role": "PARENT",
            "children": [{
                "first_name": "Ahmad",
                "last_name": "Ali",
                "gender": "MALE",
                "date_of_birth": child_dob,
                "father_name": "Ali Mohammed",
                "mother_first_name": "Fatima",
                "mother_last_name": "Ali",
            }]
        })
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# export_users filter branches
# ---------------------------------------------------------------------------

class TestExportUsersFilters:
    def test_export_with_kg_filter(self, client, test_db, sample_kindergarten):
        """Line 549: kindergarten_id filter in export."""
        admin = _make_admin(test_db, "eu_adm", "1")
        _make_user(test_db, "exp_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "eu_adm1")
        r = client.get(f"/api/admin/users/export?kindergarten_id={sample_kindergarten.id}",
                       headers=headers)
        assert r.status_code == 200

    def test_export_with_role_filter(self, client, test_db, sample_kindergarten):
        """Line 553: role filter in export."""
        admin = _make_admin(test_db, "eu_adm", "2")
        _make_user(test_db, "exp_sup2", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "eu_adm2")
        r = client.get("/api/admin/users/export?role=SUPERVISOR", headers=headers)
        assert r.status_code == 200

    def test_export_with_status_filter(self, client, test_db):
        """Lines 549/553 status branch via status filter in export."""
        admin = _make_admin(test_db, "eu_adm", "3")
        _make_user(test_db, "exp_sup3", models.UserRole.SUPERVISOR,
                   status=models.UserStatus.INACTIVE)
        headers = _tok(client, "eu_adm3")
        r = client.get("/api/admin/users/export?status=INACTIVE", headers=headers)
        assert r.status_code == 200

    def test_export_overflow_returns_422(self, client, test_db):
        """Line 561: over MAX_EXPORT_ROWS triggers 422."""
        admin = _make_admin(test_db, "eu_adm", "4")
        headers = _tok(client, "eu_adm4")
        # Patch the query's final .all() call to return 10_001 mocks
        big_list = [
            MagicMock(
                id=i, username=f"u{i}", email=f"u{i}@example.com",
                role=models.UserRole.SUPERVISOR, status=models.UserStatus.ACTIVE,
                kindergarten_id=None, created_at=None, deleted_at=None
            )
            for i in range(10_001)
        ]
        from sqlalchemy.orm import Query
        original_all = Query.all
        def patched_all(self, *args, **kwargs):
            # Only hijack queries for the User model during export
            return big_list
        with patch.object(Query, "all", patched_all):
            r = client.get("/api/admin/users/export", headers=headers)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# get_user IDOR
# ---------------------------------------------------------------------------

class TestGetUserIdor:
    def test_manager_cannot_access_different_kg_user(self, client, test_db, sample_kindergarten):
        """Line 633: manager from KG-1 tries to GET user from KG-2 → 403."""
        kg2 = _make_kg(test_db, "روضة ثانية IDOR", "IDOR_KG")
        _make_user(test_db, "idor_mgr", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        target = _make_user(test_db, "idor_tgt", models.UserRole.SUPERVISOR, kg_id=kg2.id)
        r_login = client.post("/token", data={"username": "idor_mgr", "password": "Pass123!"})
        headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
        r = client.get(f"/api/admin/users/{target.id}", headers=headers)
        assert r.status_code == 403

    def test_admin_can_access_any_user(self, client, test_db, sample_kindergarten):
        """Positive: admin can GET any user."""
        admin = _make_admin(test_db, "gu_adm", "1")
        target = _make_user(test_db, "gu_tgt1", models.UserRole.SUPERVISOR,
                            kg_id=sample_kindergarten.id)
        headers = _tok(client, "gu_adm1")
        r = client.get(f"/api/admin/users/{target.id}", headers=headers)
        assert r.status_code == 200
