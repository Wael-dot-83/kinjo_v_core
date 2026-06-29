"""
Tests for Manager Scope – Functional Requirements gap closure.

Covers:
  GAP 1: User profile fields (manager/supervisor)
  GAP 2: Class creation requires supervisor
  GAP 3: must_change_password for manager and supervisor
  GAP 4: Identity validation on user creation
  GAP 5: Manager can act as supervisor
  GAP 6: Child has_special_needs / has_medical_condition
  GAP 7: Required document enforcement on enrollment acceptance
  GAP 8: Deactivation guard (at least one supervisor per KG)
"""
import os
import secrets
from datetime import date, timedelta

import pytest

os.environ.setdefault("TESTING", "true")

from auth import get_password_hash
import models


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _csrf_headers(token: str) -> dict:
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


def _login(client, username, password):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_kg(db, suffix="1"):
    kg = models.Kindergarten(
        name_ar=f"روضة {suffix}",
        name_en=f"KG {suffix}",
        license_number=f"LIC-{suffix}",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="Street",
        contact_phone="+962790000000",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _make_user(db, role, kg=None, username=None, password="Test1234!"):
    username = username or f"user_{secrets.token_hex(4)}"
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash(password),
        role=role,
        kindergarten_id=kg.id if kg else None,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_supervisor_with_profile(db, kg, username=None, password="Test1234!"):
    user = _make_user(db, models.UserRole.SUPERVISOR, kg, username, password)
    profile = models.SupervisorProfile(user_id=user.id, kindergarten_id=kg.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user


# =========================================================================
# GAP 1: User profile fields (manager/supervisor)
# =========================================================================

class TestUserProfileFields:

    def test_create_manager_with_profile_fields(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))

        payload = {
            "username": "mgr_profile",
            "password": "Manager1!",
            "role": "MANAGER",
            "kindergarten_id": kg.id,
            "full_name": "Ahmad Ali",
            "phone_number": "+962799000000",
            "address": "Amman, Jordan",
            "nationality": "Jordanian",
            "national_id": "1234567890",
        }
        r = client.post("/api/admin/users", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["full_name"] == "Ahmad Ali"
        assert data["phone_number"] == "+962799000000"
        assert data["nationality"] == "Jordanian"
        assert data["national_id"] == "1234567890"

    def test_create_supervisor_with_profile_fields(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr1")
        headers = _csrf_headers(_login(client, "mgr1", "Test1234!"))

        payload = {
            "username": "sv_profile",
            "email": "sv@test.com",
            "password": "Super1234!",
            "role": "SUPERVISOR",
            "full_name": "Fatima Hassan",
            "phone_number": "+962799111111",
            "address": "Irbid",
            "nationality": "Jordanian",
            "national_id": "0987654321",
        }
        r = client.post("/api/staff/create", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["full_name"] == "Fatima Hassan"
        assert data["nationality"] == "Jordanian"

    def test_get_user_returns_profile_fields(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_get")
        mgr.full_name = "Manager Name"
        mgr.nationality = "Jordanian"
        mgr.national_id = "1111111111"
        test_db.commit()

        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))
        r = client.get(f"/api/admin/users/{mgr.id}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Manager Name"
        assert data["nationality"] == "Jordanian"

    def test_update_user_profile_fields(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_upd")
        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))

        r = client.put(
            f"/api/admin/users/{mgr.id}",
            json={"full_name": "Updated Name", "address": "Zarqa"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Updated Name"
        assert data["address"] == "Zarqa"


# =========================================================================
# GAP 2: Class creation requires supervisor
# =========================================================================

class TestClassRequiresSupervisor:

    def test_create_class_without_supervisor_422(self, client, test_db):
        """ClassCreate schema requires supervisor_id — omitting it should give 422."""
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_cls")
        headers = _csrf_headers(_login(client, "mgr_cls", "Test1234!"))

        payload = {
            "kindergarten_id": kg.id,
            "name_ar": "صف بدون مشرف",
            "class_code": "X001",
            "age_group": "AGE_1_2",
            "capacity_total": 10,
            "min_age_months": 12,
            "max_age_months": 24,
            # no supervisor_id
        }
        r = client.post("/api/classes", json=payload, headers=headers)
        assert r.status_code == 422  # Pydantic validation

    def test_create_class_with_supervisor_ok(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_cls2")
        sv = _make_supervisor_with_profile(test_db, kg, "sv_cls2")
        headers = _csrf_headers(_login(client, "mgr_cls2", "Test1234!"))

        payload = {
            "kindergarten_id": kg.id,
            "name_ar": "صف مع مشرف",
            "class_code": "X002",
            "age_group": "AGE_1_2",
            "capacity_total": 10,
            "min_age_months": 12,
            "max_age_months": 24,
            "supervisor_id": sv.id,
        }
        r = client.post("/api/classes", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        assert r.json()["supervisor_id"] == sv.id

    def test_create_class_supervisor_wrong_kg_fails(self, client, test_db):
        kg1 = _make_kg(test_db, "A")
        kg2 = _make_kg(test_db, "B")
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg1, "mgr_x")
        sv = _make_supervisor_with_profile(test_db, kg2, "sv_other")
        headers = _csrf_headers(_login(client, "mgr_x", "Test1234!"))

        payload = {
            "kindergarten_id": kg1.id,
            "name_ar": "صف",
            "class_code": "X003",
            "age_group": "AGE_2_4",
            "capacity_total": 15,
            "min_age_months": 24,
            "max_age_months": 48,
            "supervisor_id": sv.id,
        }
        r = client.post("/api/classes", json=payload, headers=headers)
        assert r.status_code == 400
        assert "same kindergarten" in r.json()["detail"].lower()


# =========================================================================
# GAP 3: must_change_password for manager AND supervisor
# =========================================================================

class TestMustChangePassword:

    def test_manager_must_change_password_admin_endpoint(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))

        payload = {
            "username": "newmgr",
            "password": "Manager1!",
            "role": "MANAGER",
            "kindergarten_id": kg.id,
        }
        r = client.post("/api/admin/users", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        uid = r.json()["id"]
        u = test_db.get(models.User, uid)
        assert u.must_change_password is True

    def test_supervisor_must_change_password(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))

        payload = {
            "username": "newsv",
            "password": "Super1234!",
            "role": "SUPERVISOR",
            "kindergarten_id": kg.id,
        }
        r = client.post("/api/admin/users", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        uid = r.json()["id"]
        u = test_db.get(models.User, uid)
        assert u.must_change_password is True

    def test_staff_create_must_change_password(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_pwd")
        headers = _csrf_headers(_login(client, "mgr_pwd", "Test1234!"))

        payload = {
            "username": "staff_sv",
            "password": "Staff1234!",
            "role": "SUPERVISOR",
        }
        r = client.post("/api/staff/create", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        uid = r.json()["id"]
        u = test_db.get(models.User, uid)
        assert u.must_change_password is True


# =========================================================================
# GAP 4: Identity validation on manager/supervisor creation
# =========================================================================

class TestIdentityValidation:

    def test_jordanian_manager_requires_national_id(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))

        payload = {
            "username": "mgr_jo",
            "password": "Manager1!",
            "role": "MANAGER",
            "kindergarten_id": kg.id,
            "nationality": "Jordanian",
            # no national_id
        }
        r = client.post("/api/admin/users", json=payload, headers=headers)
        assert r.status_code == 400
        msg = r.json().get("error", {}).get("message", r.json().get("detail", ""))
        assert "national id" in msg.lower() or "الرقم الوطني" in msg

    def test_non_jordanian_supervisor_requires_passport(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_fid")
        headers = _csrf_headers(_login(client, "mgr_fid", "Test1234!"))

        payload = {
            "username": "sv_foreign",
            "password": "Super1234!",
            "role": "SUPERVISOR",
            "nationality": "Egyptian",
            # no passport_number
        }
        r = client.post("/api/staff/create", json=payload, headers=headers)
        assert r.status_code == 400
        assert "passport" in r.json()["detail"].lower() or "جواز" in r.json()["detail"]


# =========================================================================
# GAP 5: Manager can act as supervisor
# =========================================================================

class TestManagerAsSupervisor:

    def test_manager_assigned_as_supervisor_ok(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_sv")
        # Create supervisor profile for manager
        profile = models.SupervisorProfile(user_id=mgr.id, kindergarten_id=kg.id)
        test_db.add(profile)
        test_db.commit()

        # Create a class via ORM (bypass API since we need full control)
        cls = models.Class(
            kindergarten_id=kg.id,
            name_ar="صف",
            class_code="M001",
            age_group="AGE_1_2",
            capacity_total=10,
            min_age_months=12,
            max_age_months=24,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        headers = _csrf_headers(_login(client, "mgr_sv", "Test1234!"))
        r = client.post(
            "/api/supervisor/assign",
            json={
                "supervisor_id": mgr.id,
                "class_id": cls.id,
                "start_date": date.today().isoformat(),
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["supervisor_id"] == mgr.id

    def test_manager_can_create_class_as_own_supervisor(self, client, test_db):
        kg = _make_kg(test_db)
        mgr = _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_own")
        # Create supervisor profile for manager
        profile = models.SupervisorProfile(user_id=mgr.id, kindergarten_id=kg.id)
        test_db.add(profile)
        test_db.commit()

        headers = _csrf_headers(_login(client, "mgr_own", "Test1234!"))
        payload = {
            "kindergarten_id": kg.id,
            "name_ar": "صف المدير",
            "class_code": "MG01",
            "age_group": "AGE_2_4",
            "capacity_total": 15,
            "min_age_months": 24,
            "max_age_months": 48,
            "supervisor_id": mgr.id,
        }
        r = client.post("/api/classes", json=payload, headers=headers)
        assert r.status_code == 201, r.text


# =========================================================================
# GAP 6: Child special_needs / medical_condition boolean indicators
# =========================================================================

class TestChildIndicators:

    def test_child_special_needs_defaults_false(self, test_db):
        kg = _make_kg(test_db)
        parent_user = _make_user(test_db, models.UserRole.PARENT)
        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="A",
            last_name="B",
            phone_number="+962790000001",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Area",
            home_address_line="Addr",
            correspondence_preference=True,
        )
        test_db.add(profile)
        test_db.commit()
        test_db.refresh(profile)

        child = models.Child(
            parent_id=profile.id,
            first_name="Child",
            last_name="B",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 2),
            father_name="A B",
            mother_first_name="M",
            mother_last_name="B",
            mother_nationality="Jordanian",
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        assert child.has_special_needs is False
        assert child.has_medical_condition is False

    def test_child_special_needs_set(self, test_db):
        kg = _make_kg(test_db)
        parent_user = _make_user(test_db, models.UserRole.PARENT)
        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="C",
            last_name="D",
            phone_number="+962790000002",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            national_id="2222222222",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Area",
            home_address_line="Addr",
            correspondence_preference=True,
        )
        test_db.add(profile)
        test_db.commit()
        test_db.refresh(profile)

        child = models.Child(
            parent_id=profile.id,
            first_name="SN",
            last_name="D",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="C D",
            mother_first_name="M",
            mother_last_name="D",
            mother_nationality="Jordanian",
            has_special_needs=True,
            has_medical_condition=True,
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        assert child.has_special_needs is True
        assert child.has_medical_condition is True


# =========================================================================
# GAP 7: Required document enforcement on enrollment acceptance
# =========================================================================

class TestDocumentEnforcement:

    def _setup_enrollment(self, db):
        """Create a child with complete profile + submitted enrollment."""
        kg = _make_kg(db)
        mgr = _make_user(db, models.UserRole.MANAGER, kg, f"mgr_{secrets.token_hex(3)}")
        sv = _make_supervisor_with_profile(db, kg, f"sv_{secrets.token_hex(3)}")

        parent_user = _make_user(db, models.UserRole.PARENT)
        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="Parent",
            last_name="Test",
            phone_number="+962790000003",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="3333333333",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Area",
            home_address_line="Addr",
            correspondence_preference=True,
            profile_complete=True,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        child = models.Child(
            parent_id=profile.id,
            first_name="Enrolled",
            last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 2),
            father_name="Parent Test",
            mother_first_name="Mother",
            mother_last_name="Test",
            mother_nationality="Jordanian",
            mother_national_id="4444444444",
            profile_complete=True,
        )
        db.add(child)
        db.commit()
        db.refresh(child)

        kg_class = models.Class(
            kindergarten_id=kg.id,
            name_ar="الصف الأول",
            name_en="Class A",
            class_code=f"CLS{secrets.token_hex(2)}",
            age_group="AGE_1_2",
            capacity_total=20,
            min_age_months=12,
            max_age_months=36,
        )
        db.add(kg_class)
        db.commit()
        db.refresh(kg_class)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            class_id=kg_class.id,
            status=models.EnrollmentStatus.SUBMITTED,
        )
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)

        return kg, mgr, child, enrollment

    def test_enrollment_acceptance_requires_documents(self, client, test_db):
        kg, mgr, child, enrollment = self._setup_enrollment(test_db)
        headers = _csrf_headers(_login(client, mgr.username, "Test1234!"))

        r = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "missing_documents" in detail or "missing_fields" in detail

    def test_enrollment_acceptance_with_docs_ok(self, client, test_db):
        kg, mgr, child, enrollment = self._setup_enrollment(test_db)

        # Upload required documents via ORM
        for doc_type in ("birth_certificate", "health_certificate"):
            doc = models.ChildDocument(
                child_id=child.id,
                document_type=doc_type,
                file_name=f"{doc_type}.pdf",
                file_path=f"/fake/{doc_type}.pdf",
                uploaded_by=mgr.id,
            )
            test_db.add(doc)
        test_db.commit()

        headers = _csrf_headers(_login(client, mgr.username, "Test1234!"))
        r = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert r.status_code == 200, r.text


# =========================================================================
# GAP 8: Deactivation guard – at least one supervisor per KG
# =========================================================================

class TestDeactivationGuard:

    def test_deactivate_last_supervisor_blocked(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        sv = _make_supervisor_with_profile(test_db, kg, "sv_last")
        _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_guard")

        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))
        r = client.put(
            f"/api/admin/users/{sv.id}",
            json={"status": "INACTIVE"},
            headers=headers,
        )
        assert r.status_code == 400
        msg = r.json().get("error", {}).get("message", r.json().get("detail", ""))
        assert "supervisor" in msg.lower()

    def test_deactivate_supervisor_others_exist_ok(self, client, test_db):
        kg = _make_kg(test_db)
        admin = _make_user(test_db, models.UserRole.ADMIN)
        sv1 = _make_supervisor_with_profile(test_db, kg, "sv_ok1")
        sv2 = _make_supervisor_with_profile(test_db, kg, "sv_ok2")
        _make_user(test_db, models.UserRole.MANAGER, kg, "mgr_g2")

        headers = _csrf_headers(_login(client, admin.username, "Test1234!"))
        r = client.put(
            f"/api/admin/users/{sv1.id}",
            json={"status": "INACTIVE"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
