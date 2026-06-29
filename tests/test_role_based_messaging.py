"""
Comprehensive tests for role-based messaging system.

Tests cover:
- Authorization layer (validate_direct_permissions) for all roles
- Audience permission validation (_validate_audience_permissions)
- Recipient resolution for all scopes (global, governorate, kindergarten)
- API endpoint integration for all roles (positive + negative cases)
- Edge cases: parent with multiple kindergartens, no enrollment, cross-KG violations

Test matrix:
  Admin  → ALL_MANAGERS / ALL_SUPERVISORS / ALL_PARENTS (global)
  Admin  → by governorate(s) (single + multiple)
  Admin  → by specific kindergarten(s)
  Manager → supervisors in own KG (audience mode)
  Manager → parents in own KG (audience mode)
  Manager → direct to supervisor in own KG
  Manager → direct to parent in own KG
  Manager → FAIL: message parents outside own KG
  Supervisor → direct to own KG manager
  Supervisor → FAIL: message parents
  Supervisor → FAIL: audience mode
  Parent → direct to own KG manager
  Parent → FAIL: message supervisor
  Parent → FAIL: message other manager
  Parent → FAIL: no active enrollment
"""
import pytest
from datetime import date, timedelta
from fastapi import HTTPException

import models
from auth import get_password_hash
from messaging_permissions import (
    validate_direct_permissions,
    _validate_audience_permissions,
    resolve_recipients,
    AudienceDefinition,
    AudienceScope,
    FilterClause,
    FilterOperator,
    parent_active_kindergarten_ids,
    parent_has_active_enrollment,
)
from admin_security import forbidden_error


# ──────────────────────────────────────────────────────────────────────
# Helpers – create test data
# ──────────────────────────────────────────────────────────────────────

def _make_kindergarten(db, name, governorate="عمان", district="عمان"):
    kg = models.Kindergarten(
        name_ar=name,
        name_en=f"{name}_en",
        license_number=f"LIC-{name}-{id(name)}",
        governorate=governorate,
        district=district,
        area="TestArea",
        address_line="Test Address",
        contact_phone="+96279" + str(abs(hash(name)) % 10_000_000).zfill(7),
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2028, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _make_user(db, username, role, kindergarten_id=None):
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("TestPass123!"),
        role=role,
        kindergarten_id=kindergarten_id,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_parent_with_enrollment(db, username, kindergarten, governorate="عمان"):
    user = _make_user(db, username, models.UserRole.PARENT)
    profile = models.ParentProfile(
        user_id=user.id,
        first_name=username,
        last_name="Test",
        phone_number="+9627900" + str(abs(hash(username)) % 100000).zfill(5),
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id=str(abs(hash(username)) % 10**10).zfill(10),
        home_governorate=governorate,
        home_district="TestCity",
        home_area="TestArea",
        home_address_line="Test Address",
        correspondence_preference=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    child = models.Child(
        parent_id=profile.id,
        first_name=f"Child_{username}",
        last_name="Test",
        gender=models.Gender.MALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name=username,
        mother_first_name="MotherFirst",
        mother_last_name="MotherLast",
        mother_nationality="Jordanian",
        mother_national_id=str(abs(hash(username + "_m")) % 10**10).zfill(10),
        media_consent=True,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return user, profile, child, enrollment


def _make_parent_no_enrollment(db, username, governorate="عمان"):
    """Create parent with profile but NO enrollment."""
    user = _make_user(db, username, models.UserRole.PARENT)
    profile = models.ParentProfile(
        user_id=user.id,
        first_name=username,
        last_name="NoEnroll",
        phone_number="+9627900" + str(abs(hash(username + "ne")) % 100000).zfill(5),
        gender=models.Gender.FEMALE,
        nationality="Jordanian",
        national_id=str(abs(hash(username + "ne")) % 10**10).zfill(10),
        home_governorate=governorate,
        home_district="TestCity",
        home_area="TestArea",
        home_address_line="Test Address",
        correspondence_preference=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user


# ──────────────────────────────────────────────────────────────────────
# Unit Tests: Authorization (validate_direct_permissions)
# ──────────────────────────────────────────────────────────────────────

class TestDirectPermissions:
    """Test validate_direct_permissions for all role combinations."""

    def test_admin_can_message_anyone(self, test_db, admin_user, manager_user, supervisor_user, parent_user):
        """Admin can send direct messages to any role."""
        validate_direct_permissions(test_db, admin_user, manager_user)
        validate_direct_permissions(test_db, admin_user, supervisor_user)
        validate_direct_permissions(test_db, admin_user, parent_user)

    def test_manager_can_message_supervisor_same_kg(self, test_db, manager_user, supervisor_user):
        """Manager can message supervisor in same kindergarten."""
        validate_direct_permissions(test_db, manager_user, supervisor_user)

    def test_manager_can_message_parent_with_enrollment(self, test_db, manager_user, parent_user, parent_enrollment):
        """Manager can message parent who has child enrolled in their KG."""
        validate_direct_permissions(test_db, manager_user, parent_user)

    def test_manager_cannot_message_supervisor_other_kg(self, test_db, sample_kindergarten):
        """Manager cannot message supervisor in different kindergarten."""
        other_kg = _make_kindergarten(test_db, "other_kg", "إربد")
        manager = _make_user(test_db, "mgr_a", models.UserRole.MANAGER, sample_kindergarten.id)
        supervisor = _make_user(test_db, "sup_other", models.UserRole.SUPERVISOR, other_kg.id)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, manager, supervisor)
        assert exc_info.value.status_code == 403

    def test_manager_cannot_message_parent_outside_kg(self, test_db, sample_kindergarten):
        """Manager cannot message parent without enrollment in their KG."""
        other_kg = _make_kindergarten(test_db, "other_kg2", "إربد")
        manager = _make_user(test_db, "mgr_q", models.UserRole.MANAGER, sample_kindergarten.id)
        parent, _, _, _ = _make_parent_with_enrollment(test_db, "parent_other_kg", other_kg)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, manager, parent)
        assert exc_info.value.status_code == 403

    def test_supervisor_can_message_own_manager(self, test_db, supervisor_user, manager_user):
        """Supervisor can message manager of same kindergarten."""
        validate_direct_permissions(test_db, supervisor_user, manager_user)

    def test_supervisor_cannot_message_other_manager(self, test_db, sample_kindergarten):
        """Supervisor cannot message manager of different kindergarten."""
        other_kg = _make_kindergarten(test_db, "other_kg3", "الزرقاء")
        supervisor = _make_user(test_db, "sup_x", models.UserRole.SUPERVISOR, sample_kindergarten.id)
        other_manager = _make_user(test_db, "mgr_other", models.UserRole.MANAGER, other_kg.id)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, supervisor, other_manager)
        assert exc_info.value.status_code == 403

    def test_supervisor_cannot_message_parent(self, test_db, supervisor_user, parent_user):
        """Supervisor cannot send direct messages to parents."""
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, supervisor_user, parent_user)
        assert exc_info.value.status_code == 403

    def test_supervisor_cannot_message_supervisor(self, test_db, sample_kindergarten):
        """Supervisor cannot message another supervisor."""
        sup1 = _make_user(test_db, "sup1", models.UserRole.SUPERVISOR, sample_kindergarten.id)
        sup2 = _make_user(test_db, "sup2", models.UserRole.SUPERVISOR, sample_kindergarten.id)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, sup1, sup2)
        assert exc_info.value.status_code == 403

    def test_parent_can_message_kg_manager(self, test_db, parent_user, manager_user, parent_enrollment):
        """Parent can message manager of kindergarten where child is enrolled."""
        validate_direct_permissions(test_db, parent_user, manager_user)

    def test_parent_cannot_message_supervisor(self, test_db, parent_user, supervisor_user, parent_enrollment):
        """Parent cannot send direct messages to supervisors."""
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, parent_user, supervisor_user)
        assert exc_info.value.status_code == 403

    def test_parent_cannot_message_other_manager(self, test_db, parent_user, parent_enrollment):
        """Parent cannot message manager of a KG where they have no enrollment."""
        other_kg = _make_kindergarten(test_db, "other_kg5", "المفرق")
        other_manager = _make_user(test_db, "mgr_nochildren", models.UserRole.MANAGER, other_kg.id)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, parent_user, other_manager)
        assert exc_info.value.status_code == 403

    def test_parent_without_enrollment_cannot_message(self, test_db, sample_kindergarten):
        """Parent with no enrolled children cannot message any manager."""
        parent = _make_parent_no_enrollment(test_db, "parent_no_enroll")
        manager = _make_user(test_db, "mgr_ne", models.UserRole.MANAGER, sample_kindergarten.id)
        with pytest.raises(HTTPException) as exc_info:
            validate_direct_permissions(test_db, parent, manager)
        assert exc_info.value.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Unit Tests: Audience Permission Validation
# ──────────────────────────────────────────────────────────────────────

class TestAudiencePermissions:
    """Test _validate_audience_permissions for all roles."""

    def _audience(self, **kwargs):
        return AudienceDefinition(**kwargs)

    def test_admin_can_use_any_scope(self, test_db, admin_user):
        """Admin can send audience messages with any scope."""
        for scope in ["GLOBAL", "GOVERNORATE", "KINDERGARTEN"]:
            aud = self._audience(include_roles=["PARENT"], scope=scope)
            _validate_audience_permissions(test_db, aud, admin_user)

    def test_manager_can_use_audience_mode(self, test_db, manager_user):
        """Manager can use audience mode for SUPERVISOR and PARENT."""
        aud = self._audience(
            include_roles=["SUPERVISOR", "PARENT"],
            scope="GLOBAL",
        )
        _validate_audience_permissions(test_db, aud, manager_user)

    def test_manager_cannot_target_admin_role(self, test_db, manager_user):
        """Manager cannot target ADMIN role in audience mode."""
        aud = self._audience(include_roles=["ADMIN"], scope="GLOBAL")
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, manager_user)
        assert exc_info.value.status_code == 403

    def test_manager_cannot_target_manager_role(self, test_db, manager_user):
        """Manager cannot target other MANAGER role in audience mode."""
        aud = self._audience(include_roles=["MANAGER"], scope="GLOBAL")
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, manager_user)
        assert exc_info.value.status_code == 403

    def test_manager_cannot_use_governorate_scope(self, test_db, manager_user):
        """Manager cannot use GOVERNORATE scope."""
        aud = self._audience(
            include_roles=["PARENT"],
            scope="GOVERNORATE",
            governorate_id="عمان",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, manager_user)
        assert exc_info.value.status_code == 403

    def test_manager_cannot_target_other_kindergarten(self, test_db, manager_user):
        """Manager cannot use kindergarten_ids for a different kindergarten."""
        aud = self._audience(
            include_roles=["PARENT"],
            scope="KINDERGARTEN",
            kindergarten_ids=[99999],
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, manager_user)
        assert exc_info.value.status_code == 403

    def test_supervisor_cannot_use_audience(self, test_db, supervisor_user):
        """Supervisor cannot use audience mode at all."""
        aud = self._audience(include_roles=["PARENT"], scope="GLOBAL")
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, supervisor_user)
        assert exc_info.value.status_code == 403

    def test_parent_cannot_use_audience(self, test_db, parent_user):
        """Parent cannot use audience mode at all."""
        aud = self._audience(include_roles=["MANAGER"], scope="GLOBAL")
        with pytest.raises(HTTPException) as exc_info:
            _validate_audience_permissions(test_db, aud, parent_user)
        assert exc_info.value.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Unit Tests: Recipient Resolution
# ──────────────────────────────────────────────────────────────────────

class TestRecipientResolution:
    """Test resolve_recipients for all scopes and roles."""

    def _audience(self, **kwargs):
        return AudienceDefinition(**kwargs)

    def test_admin_global_all_parents(self, test_db, admin_user, sample_kindergarten):
        """Admin broadcast to all parents across all kindergartens."""
        p1, _, _, _ = _make_parent_with_enrollment(test_db, "p1_global", sample_kindergarten)
        p2, _, _, _ = _make_parent_with_enrollment(test_db, "p2_global", sample_kindergarten)
        aud = self._audience(include_roles=["PARENT"], scope="GLOBAL")
        result = resolve_recipients(test_db, aud, admin_user)
        assert p1.id in result
        assert p2.id in result
        assert admin_user.id not in result

    def test_admin_global_all_managers(self, test_db, admin_user, sample_kindergarten):
        """Admin broadcast to all managers."""
        m1 = _make_user(test_db, "mgr_glob1", models.UserRole.MANAGER, sample_kindergarten.id)
        aud = self._audience(include_roles=["MANAGER"], scope="GLOBAL")
        result = resolve_recipients(test_db, aud, admin_user)
        assert m1.id in result

    def test_admin_governorate_scope(self, test_db, admin_user):
        """Admin target single governorate — returns staff + parents from that governorate."""
        kg_amman = _make_kindergarten(test_db, "kg_amman", "عمان")
        kg_irbid = _make_kindergarten(test_db, "kg_irbid", "إربد")
        sup_amman = _make_user(test_db, "sup_amman", models.UserRole.SUPERVISOR, kg_amman.id)
        sup_irbid = _make_user(test_db, "sup_irbid", models.UserRole.SUPERVISOR, kg_irbid.id)
        parent_amman, _, _, _ = _make_parent_with_enrollment(test_db, "parent_amman", kg_amman, "عمان")
        parent_irbid, _, _, _ = _make_parent_with_enrollment(test_db, "parent_irbid", kg_irbid, "إربد")

        aud = self._audience(
            include_roles=["SUPERVISOR", "PARENT"],
            scope="GOVERNORATE",
            governorate_id="عمان",
        )
        result = resolve_recipients(test_db, aud, admin_user)
        assert sup_amman.id in result
        assert parent_amman.id in result
        assert sup_irbid.id not in result
        assert parent_irbid.id not in result

    def test_admin_multiple_governorates(self, test_db, admin_user):
        """Admin target multiple governorates via filters."""
        kg_amman = _make_kindergarten(test_db, "kg_am2", "عمان")
        kg_irbid = _make_kindergarten(test_db, "kg_ir2", "إربد")
        kg_zarqa = _make_kindergarten(test_db, "kg_zq2", "الزرقاء")
        p_amman, _, _, _ = _make_parent_with_enrollment(test_db, "p_am2", kg_amman)
        p_irbid, _, _, _ = _make_parent_with_enrollment(test_db, "p_ir2", kg_irbid)
        p_zarqa, _, _, _ = _make_parent_with_enrollment(test_db, "p_zq2", kg_zarqa)

        aud = self._audience(
            include_roles=["PARENT"],
            scope="GOVERNORATE",
            filters=[FilterClause(field="kindergarten.governorate", op=FilterOperator.IN, value=["عمان", "إربد"])],
        )
        result = resolve_recipients(test_db, aud, admin_user)
        assert p_amman.id in result
        assert p_irbid.id in result
        assert p_zarqa.id not in result

    def test_admin_specific_kindergartens(self, test_db, admin_user):
        """Admin target specific kindergartens by ID."""
        kg1 = _make_kindergarten(test_db, "kg_spec1", "عمان")
        kg2 = _make_kindergarten(test_db, "kg_spec2", "إربد")
        kg3 = _make_kindergarten(test_db, "kg_spec3", "الزرقاء")
        m1 = _make_user(test_db, "mgr_sp1", models.UserRole.MANAGER, kg1.id)
        m2 = _make_user(test_db, "mgr_sp2", models.UserRole.MANAGER, kg2.id)
        m3 = _make_user(test_db, "mgr_sp3", models.UserRole.MANAGER, kg3.id)

        aud = self._audience(
            include_roles=["MANAGER"],
            scope="KINDERGARTEN",
            kindergarten_ids=[kg1.id, kg2.id],
        )
        result = resolve_recipients(test_db, aud, admin_user)
        assert m1.id in result
        assert m2.id in result
        assert m3.id not in result

    def test_manager_audience_own_kg_supervisors(self, test_db, sample_kindergarten):
        """Manager resolves supervisors within their own kindergarten only."""
        manager = _make_user(test_db, "mgr_aud1", models.UserRole.MANAGER, sample_kindergarten.id)
        sup1 = _make_user(test_db, "sup_aud1", models.UserRole.SUPERVISOR, sample_kindergarten.id)
        sup2 = _make_user(test_db, "sup_aud2", models.UserRole.SUPERVISOR, sample_kindergarten.id)
        other_kg = _make_kindergarten(test_db, "other_kg_aud", "إربد")
        sup_other = _make_user(test_db, "sup_other_aud", models.UserRole.SUPERVISOR, other_kg.id)

        aud = AudienceDefinition(include_roles=["SUPERVISOR"], scope="GLOBAL")
        result = resolve_recipients(test_db, aud, manager)
        assert sup1.id in result
        assert sup2.id in result
        assert sup_other.id not in result

    def test_manager_audience_own_kg_parents(self, test_db, sample_kindergarten):
        """Manager resolves parents with enrollment in their KG only."""
        manager = _make_user(test_db, "mgr_aud_p", models.UserRole.MANAGER, sample_kindergarten.id)
        parent_in, _, _, _ = _make_parent_with_enrollment(test_db, "parent_in_kg", sample_kindergarten)
        other_kg = _make_kindergarten(test_db, "other_kg_p", "إربد")
        parent_out, _, _, _ = _make_parent_with_enrollment(test_db, "parent_out_kg", other_kg)

        aud = AudienceDefinition(include_roles=["PARENT"], scope="GLOBAL")
        result = resolve_recipients(test_db, aud, manager)
        assert parent_in.id in result
        assert parent_out.id not in result

    def test_parent_enrollment_helpers(self, test_db, parent_user, sample_kindergarten, parent_enrollment):
        """Parent enrollment helper functions work correctly."""
        active_kgs = parent_active_kindergarten_ids(test_db, parent_user.id)
        assert sample_kindergarten.id in active_kgs
        assert parent_has_active_enrollment(test_db, parent_user.id, sample_kindergarten.id)

    def test_parent_no_enrollment_helper(self, test_db):
        """Parent with no enrollment returns empty kindergarten list."""
        parent = _make_parent_no_enrollment(test_db, "parent_no_enroll2")
        active_kgs = parent_active_kindergarten_ids(test_db, parent.id)
        assert len(active_kgs) == 0


# ──────────────────────────────────────────────────────────────────────
# Integration Tests: API Endpoints
# ──────────────────────────────────────────────────────────────────────

class TestMessageAPIEndpoints:
    """Integration tests for /comm/messages endpoint."""

    def test_admin_send_direct(self, client, admin_token, manager_user):
        """Admin can send direct message to any user."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": manager_user.id,
                "subject": "Test from admin",
                "message_body": "Hello manager",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sender_id"] != data.get("recipient_id") or data["thread_type"] == "DIRECT"

    def test_admin_audience_all_supervisors(
        self, client, admin_token, supervisor_user, sample_kindergarten, test_db
    ):
        """Admin audience message to all supervisors."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Admin broadcast",
                "message_body": "To all supervisors",
                "audience": {
                    "include_roles": ["SUPERVISOR"],
                    "scope": "GLOBAL",
                },
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201

    def test_manager_send_group_to_parents(
        self, client, manager_token, manager_user, sample_kindergarten, parent_user, parent_enrollment, test_db
    ):
        """Manager sends audience message to parents in their kindergarten."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Manager announcement",
                "message_body": "Parents in my kindergarten unique msg",
                "audience": {
                    "include_roles": ["PARENT"],
                    "scope": "KINDERGARTEN",
                    "kindergarten_ids": [sample_kindergarten.id],
                },
            },
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 201

    def test_manager_cannot_message_other_kg(
        self, client, manager_token, test_db
    ):
        """Manager cannot send audience message targeting other kindergarten."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Illegal cross-KG",
                "message_body": "Should fail cross-kg msg unique",
                "audience": {
                    "include_roles": ["PARENT"],
                    "scope": "KINDERGARTEN",
                    "kindergarten_ids": [99999],
                },
            },
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 403

    def test_supervisor_direct_to_manager(
        self, client, supervisor_token, manager_user, sample_kindergarten
    ):
        """Supervisor sends direct message to their kindergarten manager."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "subject": "Supervisor to manager",
                "message_body": "Hello manager from supervisor unique msg",
                "kindergarten_id": sample_kindergarten.id,
            },
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        assert resp.status_code == 201

    def test_supervisor_cannot_send_audience(self, client, supervisor_token):
        """Supervisor cannot use audience mode."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Supervisor audience",
                "message_body": "Should fail supervisor audience unique",
                "audience": {
                    "include_roles": ["PARENT"],
                    "scope": "GLOBAL",
                },
            },
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        assert resp.status_code == 403

    def test_supervisor_cannot_message_parent(
        self, client, supervisor_token, parent_user, parent_enrollment
    ):
        """Supervisor cannot send direct message to a parent."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": parent_user.id,
                "subject": "Supervisor to parent",
                "message_body": "Should fail supervisor to parent unique",
            },
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        assert resp.status_code == 403

    def test_parent_direct_to_manager(
        self, client, parent_token, manager_user, sample_kindergarten, parent_enrollment
    ):
        """Parent sends direct message to their kindergarten manager."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "subject": "Parent to manager",
                "message_body": "Hello manager from parent unique msg",
                "kindergarten_id": sample_kindergarten.id,
            },
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 201

    def test_parent_cannot_message_supervisor(
        self, client, parent_token, supervisor_user, parent_enrollment
    ):
        """Parent cannot send direct message to a supervisor."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": supervisor_user.id,
                "subject": "Parent to supervisor",
                "message_body": "Should fail parent to supervisor unique",
            },
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    def test_parent_cannot_message_other_kg_manager(
        self, client, parent_token, test_db, parent_enrollment
    ):
        """Parent cannot message a manager of a KG where they have no child."""
        other_kg = _make_kindergarten(test_db, "other_parent_kg", "الزرقاء")
        other_manager = _make_user(test_db, "mgr_other_par", models.UserRole.MANAGER, other_kg.id)
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": other_manager.id,
                "subject": "Parent to wrong manager",
                "message_body": "Should fail - no enrollment unique",
            },
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    def test_parent_cannot_use_audience(self, client, parent_token, parent_enrollment):
        """Parent cannot use audience mode."""
        resp = client.post(
            "/comm/messages",
            json={
                "mode": "audience",
                "subject": "Parent audience",
                "message_body": "Should fail parent audience unique",
                "audience": {
                    "include_roles": ["MANAGER"],
                    "scope": "GLOBAL",
                },
            },
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    def test_inbox_listing(self, client, admin_token, admin_user, manager_user, test_db):
        """Message appears in inbox after sending."""
        # Send a message
        send_resp = client.post(
            "/comm/messages",
            json={
                "mode": "direct",
                "recipient_id": manager_user.id,
                "subject": "Inbox test unique subj",
                "message_body": "Inbox test body unique msg",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert send_resp.status_code == 201

        # Check inbox
        list_resp = client.get(
            "/comm/messages",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["pagination"]["total"] >= 1
