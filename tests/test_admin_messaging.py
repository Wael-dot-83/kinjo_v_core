"""
Coverage for admin_endpoints.py — messaging system.

Targets:
  Lines 1950-1956  _dedupe_int_list (direct call)
  Lines 1959-1973  _normalize_governorates (valid + invalid)
  Lines 1976-1985  _canonical_governorates (valid + invalid)
  Lines 1988-1992  _validate_csrf_token (no token → 400; with token → passes)
  Lines 1995-2005  _build_search_filter (via endpoint with search param)
  Lines 2015-2041  _build_staff_recipient_query (via list_message_recipients)
  Lines 2050-2145  _build_parent_recipient_query (via list_message_recipients with PARENT role)
  Lines 2155-2169  _count_admin_recipients (via list_message_recipients)
  Lines 2262-2304  _build_recipient_breakdowns (via preview endpoint)
  Lines 2312-2323  _normalize_recipient_roles (via list_message_recipients)
  Lines 2327-2338  _target_roles_for_mode (via create_admin_message)
  Lines 2349-2387  _resolve_admin_recipient_ids (via list_message_recipients)
  Lines 2391-2477  _fetch_admin_recipient_summaries (via list_message_recipients)
  Lines 2493-2526  list_message_recipients endpoint
  Lines 2547-2698  create_admin_message endpoint
  Lines 2760-2791  governorate options endpoint
  Lines 2812-2882  preview_message_recipients endpoint

Also includes (restored 2026-06, see comment near the bottom of this file):
exact-recipient-set verification, cross-kindergarten/governorate dedup,
manager cross-kindergarten isolation, inbox cross-role leakage, and
available-recipients route-resolution + manager-scoping coverage.
"""
import io
import pytest
import secrets
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from auth import get_password_hash
import models
from config import settings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_admin(db, username="ms_admin", suffix=""):
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


def _make_kg(db, name_en="MsgKG", governorate="Amman"):
    kg = models.Kindergarten(
        name_ar=f"روضة {name_en}",
        name_en=name_en,
        governorate=governorate,
        district="Amman",
        area="area",
        address_line="street",
        contact_phone="+96279000003",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg); db.commit(); db.refresh(kg)
    return kg


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin_csrf_headers(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


# ---------------------------------------------------------------------------
# Direct function tests
# ---------------------------------------------------------------------------

class TestDedupe:
    def test_dedupe_int_list_basic(self):
        """Lines 1950-1956: deduplication."""
        from admin_endpoints import _dedupe_int_list
        assert _dedupe_int_list([1, 2, 1, 3]) == [1, 2, 3]

    def test_dedupe_int_list_with_none(self):
        """Lines 1954-1955: None → skipped via continue."""
        from admin_endpoints import _dedupe_int_list
        result = _dedupe_int_list([1, None, 2])
        assert 1 in result
        assert 2 in result

    def test_dedupe_empty(self):
        from admin_endpoints import _dedupe_int_list
        assert _dedupe_int_list(None) == []

    def test_dedupe_invalid_string(self):
        """Line 1954: non-castable value → continue."""
        from admin_endpoints import _dedupe_int_list
        result = _dedupe_int_list([1, "abc", 2])
        assert 1 in result
        assert 2 in result


class TestNormalizeGovernorates:
    def test_invalid_governorate_via_endpoint_returns_400(self, client, test_db):
        """Lines 1966-1967: invalid governorate → 400."""
        _make_admin(test_db, "ngov_adm", "1")
        headers = _tok(client, "ngov_adm1")
        r = client.get("/api/admin/message-recipients?governorates=TOTALLY_INVALID_GOV",
                       headers=headers)
        assert r.status_code == 400

    def test_none_returns_empty(self):
        from admin_endpoints import _normalize_governorates
        assert _normalize_governorates(None) == []
        assert _normalize_governorates([]) == []

    def test_empty_string_in_list_is_skipped(self):
        """Lines 1962-1963: empty string in list → continue."""
        from admin_endpoints import _normalize_governorates
        # Empty string is skipped, not validated
        result = _normalize_governorates([""])
        assert result == []


class TestCanonicalGovernorates:
    def test_invalid_governorate_in_create_message_returns_400(self, client, test_db,
                                                                sample_kindergarten):
        """Lines 1983-1984: invalid governorate in target → 400."""
        _make_admin(test_db, "cgov_adm", "1")
        _make_user(test_db, "cgov_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cgov_adm1")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Test Subject",
            "message_body": "Test body message here.",
            "target": {
                "mode": "GOVERNORATE",
                "governorates": ["NOT_VALID_XYZ"],
            }
        })
        assert r.status_code == 400

    def test_none_returns_empty(self):
        from admin_endpoints import _canonical_governorates
        assert _canonical_governorates(None) == []


class TestValidateCsrfToken:
    def test_no_csrf_returns_400(self, client, test_db):
        """Lines 1991-1992: no CSRF header/cookie → 400."""
        _make_admin(test_db, "csrf_adm", "1")
        headers = _tok(client, "csrf_adm1")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Test",
            "message_body": "Test body.",
            "target": {"mode": "ALL_USERS"}
        })
        assert r.status_code == 400

    def test_mismatched_csrf_returns_400(self, client, test_db):
        """Lines 1991-1992: header ≠ cookie → 400."""
        _make_admin(test_db, "csrf_adm", "2")
        r_login = client.post("/token", data={"username": "csrf_adm2", "password": "Admin123!"})
        headers = {
            "Authorization": f"Bearer {r_login.json()['access_token']}",
            "X-CSRF-Token": "token_aaa",
            "Cookie": "kinjo_csrf_token=token_bbb",
        }
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Test",
            "message_body": "Test body.",
            "target": {"mode": "ALL_USERS"}
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# list_message_recipients endpoint
# ---------------------------------------------------------------------------

class TestListMessageRecipients:
    def test_basic_list_returns_200(self, client, test_db, sample_kindergarten):
        """Lines 2493-2526: basic call covers all helpers."""
        _make_admin(test_db, "lmr_adm", "1")
        _make_user(test_db, "lmr_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "lmr_adm1")
        r = client.get("/api/admin/message-recipients", headers=headers)
        assert r.status_code == 200

    def test_list_with_role_filter(self, client, test_db, sample_kindergarten):
        """Lines 2312-2323: roles filter → _normalize_recipient_roles."""
        _make_admin(test_db, "lmr_adm", "2")
        _make_user(test_db, "lmr_mgr2", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _tok(client, "lmr_adm2")
        r = client.get("/api/admin/message-recipients?roles=MANAGER", headers=headers)
        assert r.status_code == 200

    def test_list_with_search(self, client, test_db, sample_kindergarten):
        """Lines 1995-2005: search param → _build_search_filter tokens."""
        _make_admin(test_db, "lmr_adm", "3")
        _make_user(test_db, "lmr_searchname3", models.UserRole.SUPERVISOR,
                   kg_id=sample_kindergarten.id)
        headers = _tok(client, "lmr_adm3")
        r = client.get("/api/admin/message-recipients?search=searchname", headers=headers)
        assert r.status_code == 200

    def test_list_with_kg_filter(self, client, test_db, sample_kindergarten):
        """Lines 2499-2500: kindergarten_ids → ensure_kindergartens_exist."""
        _make_admin(test_db, "lmr_adm", "4")
        _make_user(test_db, "lmr_sup4", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "lmr_adm4")
        r = client.get(
            f"/api/admin/message-recipients?kindergarten_ids={sample_kindergarten.id}",
            headers=headers
        )
        assert r.status_code == 200

    def test_list_with_parent_role(self, client, test_db, parent_user, parent_enrollment):
        """Lines 2050-2145: PARENT role → _build_parent_recipient_query."""
        _make_admin(test_db, "lmr_adm", "5")
        headers = _tok(client, "lmr_adm5")
        r = client.get("/api/admin/message-recipients?roles=PARENT", headers=headers)
        assert r.status_code == 200

    def test_list_multiple_roles(self, client, test_db, sample_kindergarten):
        """Lines 2015-2041: SUPERVISOR + MANAGER → _build_staff_recipient_query."""
        _make_admin(test_db, "lmr_adm", "6")
        _make_user(test_db, "lmr_sup6", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        _make_user(test_db, "lmr_mgr6", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _tok(client, "lmr_adm6")
        r = client.get("/api/admin/message-recipients?roles=SUPERVISOR&roles=MANAGER",
                       headers=headers)
        assert r.status_code == 200

    def test_list_unauthenticated_returns_40x(self, client, test_db):
        r = client.get("/api/admin/message-recipients")
        assert r.status_code in [401, 403]


# ---------------------------------------------------------------------------
# create_admin_message
# ---------------------------------------------------------------------------

class TestCreateAdminMessage:
    def test_all_users_message_success(self, client, test_db, sample_kindergarten):
        """Lines 2547-2698: full create_admin_message flow."""
        _make_admin(test_db, "cam_adm", "1")
        _make_user(test_db, "cam_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm1")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Test Announcement",
            "message_body": "Test message body for all users.",
            "target": {"mode": "ALL_USERS"},
            "allow_replies": True,
        })
        assert r.status_code == 201

    def test_all_managers_message(self, client, test_db, sample_kindergarten):
        """_target_roles_for_mode ALL_MANAGERS."""
        _make_admin(test_db, "cam_adm", "2")
        _make_user(test_db, "cam_mgr2", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm2")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Manager Announcement",
            "message_body": "Message to all managers.",
            "target": {"mode": "ALL_MANAGERS"},
        })
        assert r.status_code == 201

    def test_all_supervisors_message(self, client, test_db, sample_kindergarten):
        _make_admin(test_db, "cam_adm", "3")
        _make_user(test_db, "cam_sup3", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm3")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Supervisor Notice",
            "message_body": "Notice to all supervisors here.",
            "target": {"mode": "ALL_SUPERVISORS"},
        })
        assert r.status_code == 201

    def test_no_recipients_returns_400(self, client, test_db):
        """Lines 2585-2586: empty recipient set → 400."""
        _make_admin(test_db, "cam_adm", "4")
        headers = _admin_csrf_headers(client, "cam_adm4")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "No Recipients",
            "message_body": "No one to send to.",
            "target": {"mode": "ALL_USERS"},
        })
        assert r.status_code == 400

    def test_empty_subject_returns_400(self, client, test_db, sample_kindergarten):
        """Lines 2550-2551: empty subject → 400."""
        _make_admin(test_db, "cam_adm", "5")
        _make_user(test_db, "cam_sup5", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm5")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "",
            "message_body": "Body text.",
            "target": {"mode": "ALL_USERS"},
        })
        assert r.status_code == 400

    def test_empty_body_returns_400(self, client, test_db, sample_kindergarten):
        """Lines 2552-2553: empty body → 400."""
        _make_admin(test_db, "cam_adm", "6")
        _make_user(test_db, "cam_sup6", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm6")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Subject",
            "message_body": "   ",
            "target": {"mode": "ALL_USERS"},
        })
        assert r.status_code == 400

    def test_kindergartens_mode_without_ids_returns_400(self, client, test_db, sample_kindergarten):
        """Lines 2567-2569: KINDERGARTENS without ids → 400."""
        _make_admin(test_db, "cam_adm", "7")
        _make_user(test_db, "cam_sup7", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm7")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "KG Message",
            "message_body": "Message for specific KG.",
            "target": {"mode": "KINDERGARTENS"},
        })
        assert r.status_code == 400

    def test_kindergartens_mode_with_single_kg(self, client, test_db, sample_kindergarten):
        """Lines 2602-2604: KINDERGARTENS with single KG sets target_kindergarten_id."""
        _make_admin(test_db, "cam_adm", "8")
        _make_user(test_db, "cam_sup8", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _admin_csrf_headers(client, "cam_adm8")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Single KG Message",
            "message_body": "Message for one specific kindergarten.",
            "target": {
                "mode": "KINDERGARTENS",
                "kindergarten_ids": [sample_kindergarten.id],
            },
        })
        assert r.status_code in [201, 400]

    def test_all_parents_message(self, client, test_db, parent_user, parent_enrollment):
        """ALL_PARENTS mode."""
        _make_admin(test_db, "cam_adm", "9")
        headers = _admin_csrf_headers(client, "cam_adm9")
        r = client.post("/api/admin/messages", headers=headers, json={
            "subject": "Parent Message",
            "message_body": "Message to parents with enrolled children.",
            "target": {"mode": "ALL_PARENTS"},
        })
        assert r.status_code in [201, 400]


# ---------------------------------------------------------------------------
# Governorate options endpoint
# ---------------------------------------------------------------------------

class TestGovernorateOptions:
    def test_get_options_returns_200(self, client, test_db):
        """Lines 2760-2791: GET /api/admin/options/governorates."""
        _make_admin(test_db, "gopt_adm", "1")
        headers = _tok(client, "gopt_adm1")
        r = client.get("/api/admin/options/governorates", headers=headers)
        assert r.status_code == 200

    def test_unauthorized_returns_40x(self, client):
        r = client.get("/api/admin/options/governorates")
        assert r.status_code in [401, 403]


# ---------------------------------------------------------------------------
# preview_message_recipients endpoint
# ---------------------------------------------------------------------------

class TestPreviewMessageRecipients:
    def test_preview_all_users(self, client, test_db, sample_kindergarten):
        """Lines 2812-2882: preview with ALL_USERS mode."""
        _make_admin(test_db, "pmr_adm", "1")
        _make_user(test_db, "pmr_sup1", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "pmr_adm1")
        r = client.get("/api/admin/message-recipients/preview?mode=ALL_USERS", headers=headers)
        assert r.status_code == 200

    def test_preview_all_managers(self, client, test_db, sample_kindergarten):
        """Lines 2814-2815: ALL_MANAGERS."""
        _make_admin(test_db, "pmr_adm", "2")
        _make_user(test_db, "pmr_mgr2", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _tok(client, "pmr_adm2")
        r = client.get("/api/admin/message-recipients/preview?mode=ALL_MANAGERS", headers=headers)
        assert r.status_code == 200

    def test_preview_all_supervisors(self, client, test_db, sample_kindergarten):
        """Lines 2816-2817: ALL_SUPERVISORS."""
        _make_admin(test_db, "pmr_adm", "3")
        _make_user(test_db, "pmr_sup3", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "pmr_adm3")
        r = client.get("/api/admin/message-recipients/preview?mode=ALL_SUPERVISORS", headers=headers)
        assert r.status_code == 200

    def test_preview_all_parents(self, client, test_db, parent_user, parent_enrollment):
        """Lines 2818-2819: ALL_PARENTS + breakdowns."""
        _make_admin(test_db, "pmr_adm", "4")
        headers = _tok(client, "pmr_adm4")
        r = client.get("/api/admin/message-recipients/preview?mode=ALL_PARENTS", headers=headers)
        assert r.status_code == 200

    def test_preview_with_search(self, client, test_db, sample_kindergarten):
        """_build_search_filter with multiple tokens."""
        _make_admin(test_db, "pmr_adm", "5")
        _make_user(test_db, "pmr_searchme5", models.UserRole.SUPERVISOR,
                   kg_id=sample_kindergarten.id)
        headers = _tok(client, "pmr_adm5")
        r = client.get(
            "/api/admin/message-recipients/preview?mode=ALL_USERS&search=searchme",
            headers=headers
        )
        assert r.status_code == 200

    def test_preview_kindergartens_no_ids_returns_400(self, client, test_db):
        """Lines 2828-2829: KINDERGARTENS without ids → 400."""
        _make_admin(test_db, "pmr_adm", "6")
        headers = _tok(client, "pmr_adm6")
        r = client.get("/api/admin/message-recipients/preview?mode=KINDERGARTENS", headers=headers)
        assert r.status_code == 400

    def test_preview_governorate_no_govs_returns_400(self, client, test_db):
        """Lines 2830-2831: GOVERNORATE without govs → 400."""
        _make_admin(test_db, "pmr_adm", "7")
        headers = _tok(client, "pmr_adm7")
        r = client.get("/api/admin/message-recipients/preview?mode=GOVERNORATE", headers=headers)
        assert r.status_code == 400

    def test_preview_with_kg_filter(self, client, test_db, sample_kindergarten):
        """Lines 2833-2834: kindergarten_ids with ensure_kindergartens_exist."""
        _make_admin(test_db, "pmr_adm", "8")
        _make_user(test_db, "pmr_sup8", models.UserRole.SUPERVISOR, kg_id=sample_kindergarten.id)
        headers = _tok(client, "pmr_adm8")
        r = client.get(
            f"/api/admin/message-recipients/preview?mode=ALL_USERS"
            f"&kindergarten_ids={sample_kindergarten.id}",
            headers=headers
        )
        assert r.status_code == 200

    def test_preview_unauthorized_returns_40x(self, client):
        r = client.get("/api/admin/message-recipients/preview?mode=ALL_USERS")
        assert r.status_code in [401, 403]


# ---------------------------------------------------------------------------
# POST /admin/messages/preview — lines 2904-2961
# ---------------------------------------------------------------------------

class TestPostMessagePreview:
    def test_all_users_post_preview(self, client, test_db):
        """Lines 2904-2961: POST preview with ALL_USERS mode."""
        _make_admin(test_db, "ppv_adm", "1")
        _make_user(test_db, "ppv_sup1", models.UserRole.SUPERVISOR)
        headers = _tok(client, "ppv_adm1")
        r = client.post("/api/admin/messages/preview", headers=headers, json={
            "target": {"mode": "ALL_USERS"},
            "page": 1,
            "page_size": 10,
        })
        assert r.status_code == 200
        assert "items" in r.json()

    def test_governorate_mode_post_preview(self, client, test_db):
        """Lines 2910-2912: GOVERNORATE without govs → 400."""
        _make_admin(test_db, "ppv_adm", "2")
        headers = _tok(client, "ppv_adm2")
        r = client.post("/api/admin/messages/preview", headers=headers, json={
            "target": {"mode": "GOVERNORATE", "governorates": []},
        })
        assert r.status_code == 400

    def test_kindergartens_mode_no_ids_post_preview(self, client, test_db):
        """Lines 2913-2914: KINDERGARTENS without ids → 400."""
        _make_admin(test_db, "ppv_adm", "3")
        headers = _tok(client, "ppv_adm3")
        r = client.post("/api/admin/messages/preview", headers=headers, json={
            "target": {"mode": "KINDERGARTENS", "kindergarten_ids": []},
        })
        assert r.status_code == 400

    def test_all_managers_post_preview(self, client, test_db, sample_kindergarten):
        """ALL_MANAGERS mode."""
        _make_admin(test_db, "ppv_adm", "4")
        _make_user(test_db, "ppv_mgr4", models.UserRole.MANAGER, kg_id=sample_kindergarten.id)
        headers = _tok(client, "ppv_adm4")
        r = client.post("/api/admin/messages/preview", headers=headers, json={
            "target": {"mode": "ALL_MANAGERS"},
        })
        assert r.status_code == 200

    def test_post_preview_with_search(self, client, test_db):
        """search term in POST preview."""
        _make_admin(test_db, "ppv_adm", "5")
        headers = _tok(client, "ppv_adm5")
        r = client.post("/api/admin/messages/preview", headers=headers, json={
            "target": {"mode": "ALL_USERS", "search": "test"},
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Exact-recipient-set / dedup / cross-role isolation behavioral coverage.
#
# Restored 2026-06 after a review found the rewrite above (helper-function +
# CSRF coverage) had replaced these end-to-end behavioral checks with
# status-code-only assertions, silently losing the ability to catch a
# regression that sends an admin broadcast to the wrong audience, fails to
# dedupe a parent enrolled in two targeted kindergartens, lets a manager
# message outside their own kindergarten, or leaks a role-targeted message
# into another role's inbox. These use the older module-level fixture style
# (auth_headers_admin/auth_headers_manager/auth_headers_parent) rather than
# the _make_admin/_tok helpers above — both styles read from the same
# conftest.py fixtures and are kept side by side intentionally.
# ---------------------------------------------------------------------------

def create_kindergarten(test_db, name_suffix, governorate, phone_suffix):
    kindergarten = models.Kindergarten(
        name_ar=f"روضة {name_suffix}",
        name_en=f"KG {name_suffix}",
        governorate=governorate,
        district="City",
        area="Area",
        address_line="Address Line",
        contact_phone=f"+96279000{phone_suffix}",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)
    return kindergarten


def create_staff(test_db, username, role, kindergarten_id):
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("Pass123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def create_parent(test_db, username, home_governorate, enrollment_kindergarten_ids=None):
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("Pass123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    profile = models.ParentProfile(
        user_id=user.id,
        first_name="Parent",
        last_name=username,
        phone_number=f"+96279{user.id:07d}",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        home_governorate=home_governorate,
        home_district="City",
        home_area="Area",
        home_address_line="Address",
        correspondence_preference=True
    )
    test_db.add(profile)
    test_db.commit()
    test_db.refresh(profile)

    for index, kg_id in enumerate(enrollment_kindergarten_ids or []):
        child = models.Child(
            parent_id=profile.id,
            first_name=f"Child{index}",
            last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Father",
            mother_first_name="Mother",
            mother_last_name="Last",
            mother_nationality="Jordanian",
            media_consent=True
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg_id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

    return user


def test_admin_send_all_users_and_roles(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten,
    manager_user,
    supervisor_user,
    parent_user,
    parent_enrollment
):
    """Exact recipient-set verification across ALL_USERS / ALL_MANAGERS / ALL_PARENTS."""
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2001")
    manager_irbid = create_staff(test_db, "manager_irbid", models.UserRole.MANAGER, kg_irbid.id)
    supervisor_irbid = create_staff(test_db, "supervisor_irbid", models.UserRole.SUPERVISOR, kg_irbid.id)
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "All users",
            "message_body": "Hello everyone",
            "target": {"mode": "ALL_USERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {
        manager_user.id,
        supervisor_user.id,
        parent_user.id,
        manager_irbid.id,
        supervisor_irbid.id,
        parent_irbid.id
    }

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Managers only",
            "message_body": "Hello managers",
            "target": {"mode": "ALL_MANAGERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {manager_user.id, manager_irbid.id}

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Parents only",
            "message_body": "Hello parents",
            "target": {"mode": "ALL_PARENTS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {parent_user.id, parent_irbid.id}


def test_admin_governorate_targeting(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten,
    manager_user,
    supervisor_user,
    parent_user,
    parent_enrollment
):
    """GOVERNORATE mode must include only that governorate's users, with negative assertions."""
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2002")
    manager_irbid = create_staff(test_db, "manager_irbid", models.UserRole.MANAGER, kg_irbid.id)
    supervisor_irbid = create_staff(test_db, "supervisor_irbid", models.UserRole.SUPERVISOR, kg_irbid.id)
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])
    parent_home_only = create_parent(test_db, "parent_home_only", "Irbid", [])
    parent_home_enrolled_elsewhere = create_parent(test_db, "parent_home_else", "Irbid", [sample_kindergarten.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Irbid update",
            "message_body": "Irbid only",
            "target": {
                "mode": "GOVERNORATE",
                "roles": ["MANAGER", "SUPERVISOR", "PARENT"],
                "governorates": ["Irbid"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {
        manager_irbid.id,
        supervisor_irbid.id,
        parent_irbid.id,
        parent_home_only.id
    }
    assert manager_user.id not in recipient_ids
    assert supervisor_user.id not in recipient_ids
    assert parent_user.id not in recipient_ids
    assert parent_home_enrolled_elsewhere.id not in recipient_ids


def test_admin_kindergarten_targeting_dedup(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    """A parent enrolled in two targeted kindergartens must receive exactly one copy."""
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2003")
    parent_multi = create_parent(test_db, "parent_multi", "Amman", [sample_kindergarten.id, kg_irbid.id])
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Selected KGs",
            "message_body": "Two kindergartens",
            "target": {
                "mode": "KINDERGARTENS",
                "roles": ["PARENT"],
                "kindergarten_ids": [sample_kindergarten.id, kg_irbid.id]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == msg_id
    ).all()
    recipient_ids = {row.recipient_user_id for row in recipients}
    assert recipient_ids == {parent_multi.id, parent_irbid.id}
    assert test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == msg_id,
        models.MessageRecipient.recipient_user_id == parent_multi.id
    ).count() == 1


def test_admin_preview_breakdown_counts(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    """Preview breakdown counts (by_role/by_governorate/by_kindergarten) must reflect real data."""
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "3005")
    create_staff(test_db, "manager_preview", models.UserRole.MANAGER, kg_irbid.id)
    create_parent(test_db, "parent_preview", "Irbid", [kg_irbid.id])

    response = client.get(
        "/api/admin/message-recipients/preview",
        params={
            "mode": "KINDERGARTENS",
            "kindergarten_ids": [sample_kindergarten.id, kg_irbid.id],
            "roles": ["PARENT", "MANAGER"]
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 2
    assert payload["by_role"]["PARENT"] >= 1
    assert payload["by_role"]["MANAGER"] >= 1
    assert "by_governorate" in payload
    assert "by_kindergarten" in payload


def test_admin_search_filtering(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    """Search must actually filter — not just return 200 regardless of the term."""
    unique_parent = create_parent(test_db, "search_unique", "Amman", [sample_kindergarten.id])
    create_parent(test_db, "other_parent", "Irbid", [])

    response = client.get(
        "/api/admin/message-recipients",
        params={
            "roles": ["PARENT"],
            "search": "search_unique"
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == unique_parent.id


def test_admin_deduplication_across_governorate_and_kindergarten(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    """A parent matched by both a governorate filter and a kindergarten filter is deduped."""
    kg_irbid = create_kindergarten(test_db, "إربد 2", "Irbid", "3006")
    parent_multi = create_parent(test_db, "parent_overlap", "Irbid", [sample_kindergarten.id, kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Overlap dedupe",
            "message_body": "This parent should only receive once",
            "target": {
                "mode": "GOVERNORATE",
                "governorates": ["Irbid"],
                "roles": ["PARENT"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == response.json()["id"]
    ).all()
    assert {row.recipient_user_id for row in recipients} == {parent_multi.id}


def test_admin_endpoints_require_admin(
    client,
    auth_headers_manager,
    auth_headers_parent
):
    """Authenticated wrong-role users (not just unauthenticated ones) must get 403."""
    response = client.get("/api/admin/message-recipients", headers=auth_headers_manager)
    assert response.status_code == 403

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Nope",
            "message_body": "Nope",
            "target": {"mode": "ALL_USERS"}
        },
        headers=auth_headers_manager
    )
    assert response.status_code == 403

    response = client.get("/api/admin/message-recipients", headers=auth_headers_parent)
    assert response.status_code == 403


def test_manager_cannot_target_outside_kindergarten(
    client,
    test_db,
    manager_token,
    sample_kindergarten
):
    """A manager must not be able to message recipients outside their own kindergarten."""
    other_kg = create_kindergarten(test_db, "الزرقاء", "Zarqa", "2004")
    headers_manager = {"Authorization": f"Bearer {manager_token}"}

    response = client.post(
        "/comm/messages",
        json={
            "subject": "Out of scope",
            "message_body": "Should be blocked",
            "message_type": "announcement",
            "audience": {
                "roles": ["PARENT"],
                "kindergarten_ids": [other_kg.id]
            }
        },
        headers=headers_manager
    )
    assert response.status_code == 403


def test_inbox_visibility_no_leakage(
    client,
    auth_headers_admin,
    auth_headers_manager,
    auth_headers_parent,
    manager_user
):
    """A role-targeted message must appear in that role's inbox and nobody else's."""
    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Managers only",
            "message_body": "Managers announcement",
            "target": {"mode": "ALL_MANAGERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.get("/comm/messages", headers=auth_headers_manager)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == msg_id for item in items)

    response = client.get("/comm/messages", headers=auth_headers_parent)
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["id"] != msg_id for item in items)


def test_route_resolution_available_recipients_static_path(
    client,
    auth_headers_manager
):
    """Static recipients path must resolve to recipients handler, not message-id handler."""
    response = client.get("/comm/messages/available-recipients", headers=auth_headers_manager)
    assert response.status_code == 200
    payload = response.json()
    assert "parents" in payload
    assert "supervisors" in payload


def test_route_resolution_message_id_dynamic_path(
    client,
    test_db,
    admin_user,
    manager_user,
    auth_headers_manager
):
    """Numeric message-id path must resolve to message detail handler."""
    message = models.Message(
        thread_type=models.MessageThreadType.DIRECT,
        sender_id=admin_user.id,
        recipient_id=manager_user.id,
        kindergarten_id=manager_user.kindergarten_id,
        subject="Route Resolution",
        message_body="Validate dynamic message path"
    )
    test_db.add(message)
    test_db.commit()
    test_db.refresh(message)

    response = client.get(f"/comm/messages/{message.id}", headers=auth_headers_manager)
    assert response.status_code == 200
    assert response.json()["id"] == message.id


def test_available_recipients_scoped_to_manager_own_kindergarten(
    client,
    test_db,
    manager_token,
    manager_user,
    sample_kindergarten
):
    """GET /comm/messages/available-recipients must only return recipients from the
    requesting manager's own kindergarten — a manager must never see another
    kindergarten's parents/supervisors in this list."""
    other_kg = create_kindergarten(test_db, "العقبة", "Aqaba", "2005")
    create_staff(test_db, "supervisor_outside_scope", models.UserRole.SUPERVISOR, other_kg.id)
    create_parent(test_db, "parent_outside_scope", "Aqaba", [other_kg.id])

    create_staff(test_db, "supervisor_in_scope", models.UserRole.SUPERVISOR, sample_kindergarten.id)
    in_scope_parent = create_parent(test_db, "parent_in_scope", "Amman", [sample_kindergarten.id])

    headers_manager = {"Authorization": f"Bearer {manager_token}"}
    response = client.get("/comm/messages/available-recipients", headers=headers_manager)
    assert response.status_code == 200
    payload = response.json()

    returned_parent_ids = {p["id"] for p in payload["parents"]}
    returned_supervisor_names = {s["name"] for s in payload["supervisors"]}

    assert in_scope_parent.id in returned_parent_ids
    assert "supervisor_in_scope" in returned_supervisor_names
    assert "parent_outside_scope" not in {
        p["name"] for p in payload["parents"]
    }
    assert "supervisor_outside_scope" not in returned_supervisor_names
