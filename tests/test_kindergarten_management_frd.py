"""
Functional tests for the Kindergarten Management module (FRD implementation).

Covers:
  - Manager assignment cascade (FRD §4, C1–C5): single-KG binding,
    supervisor-role stripping, previous-KG detachment, single active manager,
    replace flow, and supervisor-coverage guard.
  - Atomic kindergarten + primary-manager creation (§2.4).
  - Freeze / Unfreeze operations (§1.4).
"""
from datetime import date

import pytest

import models
from manager_assignment_service import (
    assign_user_as_manager,
    strip_supervisor_role,
    guard_supervisor_coverage,
    ManagerAssignmentError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_kg(db, name_ar, license_number, status=models.KindergartenStatus.ACTIVE):
    kg = models.Kindergarten(
        name_ar=name_ar, name_en=name_ar, governorate="Amman", district="Amman",
        area="Abdoun", address_line="X", contact_phone=f"+9627{license_number[-7:]}",
        license_number=license_number, status=status, license_valid_until=date(2027, 12, 31),
    )
    db.add(kg); db.commit(); db.refresh(kg)
    return kg


def _mk_user(db, username, role, kg_id, status=models.UserStatus.ACTIVE):
    u = models.User(
        username=username, email=f"{username}@t.jo",
        hashed_password="x", role=role, status=status, kindergarten_id=kg_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_supervisor_with_artifacts(db, username, kg):
    """Create a supervisor + SupervisorProfile + a class + assignment."""
    sup = _mk_user(db, username, models.UserRole.SUPERVISOR, kg.id)
    db.add(models.SupervisorProfile(user_id=sup.id, kindergarten_id=kg.id))
    cls = models.Class(
        kindergarten_id=kg.id, name_ar="ص", name_en="C", class_code=f"C-{sup.id}",
        age_group="AGE_1_2", capacity_total=20, min_age_months=12, max_age_months=24,
        is_active=True, supervisor_id=sup.id,
    )
    db.add(cls); db.commit(); db.refresh(cls)
    db.add(models.SupervisorAssignment(
        class_id=cls.id, supervisor_id=sup.id, is_primary=True, start_date=date.today(),
    ))
    db.commit()
    return sup, cls


# ---------------------------------------------------------------------------
# C4 / C5 — supervisor-role stripping
# ---------------------------------------------------------------------------

def test_strip_supervisor_role_removes_all_artifacts(test_db):
    kg = _mk_kg(test_db, "KG Strip", "LIC-STRIP-1")
    sup, cls = _mk_supervisor_with_artifacts(test_db, "sup_strip", kg)

    summary = strip_supervisor_role(test_db, sup, actor_id=None)
    test_db.commit()

    import validators
    assert summary["profile_removed"] is True
    assert summary["assignments_removed"] == 1
    # The retired legacy Class.supervisor_id column is no longer cleared (D1/B5);
    # soft-deleting the SupervisorAssignment rows is the whole job now.
    assert summary["classes_cleared"] == 0
    assert test_db.query(models.SupervisorProfile).filter_by(user_id=sup.id).first() is None
    active = test_db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == sup.id,
        models.SupervisorAssignment.deleted_at.is_(None),
    ).count()
    assert active == 0
    # No active primary assignment remains for the class (source of truth).
    assert validators.active_primary_supervisor_map(test_db, [cls.id]) == {}


# ---------------------------------------------------------------------------
# C1 / C3 — single KG, previous-KG detachment
# ---------------------------------------------------------------------------

def test_manager_reassignment_detaches_from_previous_kg(test_db):
    kg_a = _mk_kg(test_db, "KG A", "LIC-A")
    kg_b = _mk_kg(test_db, "KG B", "LIC-B")
    mgr = _mk_user(test_db, "mgr_move", models.UserRole.MANAGER, kg_a.id)

    assign_user_as_manager(test_db, mgr, kg_b.id, actor_id=None)
    test_db.commit(); test_db.refresh(mgr)

    assert mgr.kindergarten_id == kg_b.id
    # KG A no longer has an active manager.
    a_mgrs = test_db.query(models.User).filter(
        models.User.kindergarten_id == kg_a.id,
        models.User.role == models.UserRole.MANAGER,
        models.User.status == models.UserStatus.ACTIVE,
    ).count()
    assert a_mgrs == 0


def test_promoting_supervisor_to_manager_strips_supervisor_role(test_db):
    kg = _mk_kg(test_db, "KG Promo", "LIC-PROMO")
    target = _mk_kg(test_db, "KG Target", "LIC-TARGET")
    # Two supervisors so removing one doesn't strand the KG (coverage guard).
    sup, cls = _mk_supervisor_with_artifacts(test_db, "sup_promo", kg)
    _mk_user(test_db, "sup_backup", models.UserRole.SUPERVISOR, kg.id)

    assign_user_as_manager(test_db, sup, target.id, actor_id=None)
    test_db.commit(); test_db.refresh(sup)

    assert sup.role == models.UserRole.MANAGER
    assert sup.kindergarten_id == target.id
    assert test_db.query(models.SupervisorProfile).filter_by(user_id=sup.id).first() is None


# ---------------------------------------------------------------------------
# C2 — single active manager per KG (+ replace)
# ---------------------------------------------------------------------------

def test_assign_to_occupied_kg_conflicts_without_replace(test_db):
    kg_a = _mk_kg(test_db, "KG occ A", "LIC-OCCA")
    kg_b = _mk_kg(test_db, "KG occ B", "LIC-OCCB")
    _mk_user(test_db, "mgr_existing", models.UserRole.MANAGER, kg_b.id)
    incoming = _mk_user(test_db, "mgr_incoming", models.UserRole.MANAGER, kg_a.id)

    with pytest.raises(ManagerAssignmentError) as exc:
        assign_user_as_manager(test_db, incoming, kg_b.id, actor_id=None)
    assert exc.value.status_code == 409


def test_replace_vacates_existing_manager(test_db):
    kg_a = _mk_kg(test_db, "KG rep A", "LIC-REPA")
    kg_b = _mk_kg(test_db, "KG rep B", "LIC-REPB")
    outgoing = _mk_user(test_db, "mgr_out", models.UserRole.MANAGER, kg_b.id)
    incoming = _mk_user(test_db, "mgr_in", models.UserRole.MANAGER, kg_a.id)

    assign_user_as_manager(test_db, incoming, kg_b.id, actor_id=None, allow_replace=True)
    test_db.commit()
    test_db.refresh(outgoing); test_db.refresh(incoming)

    assert incoming.kindergarten_id == kg_b.id
    assert incoming.status == models.UserStatus.ACTIVE
    assert outgoing.status == models.UserStatus.INACTIVE  # vacated


def test_coverage_guard_blocks_stranding_kg(test_db):
    kg = _mk_kg(test_db, "KG lone", "LIC-LONE")
    target = _mk_kg(test_db, "KG lone target", "LIC-LONE-T")
    sup, _ = _mk_supervisor_with_artifacts(test_db, "sup_lone", kg)  # only supervisor

    with pytest.raises(ManagerAssignmentError) as exc:
        assign_user_as_manager(test_db, sup, target.id, actor_id=None)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# §2.4 — atomic KG + primary manager
# ---------------------------------------------------------------------------

def _kg_payload(name_ar, license_number):
    return {
        "kindergarten": {
            "name_ar": name_ar, "name_en": name_ar, "governorate": "Amman",
            "district": "Amman", "area": "Abdoun", "address_line": "Rd 1",
            "contact_phone": f"+96279{license_number[-6:]}", "license_number": license_number,
        },
        "manager": {
            "full_name": "Manager One", "phone_number": "+962790000001",
            "nationality": "Jordanian", "national_id": "9891234567",
            "username": f"mgr_{license_number.lower().replace('-', '')}",
            "email": f"{license_number.lower().replace('-', '')}@t.jo",
            "password": "Manager123!",
        },
    }


def test_create_kg_with_manager_atomic(client, auth_headers_admin, test_db):
    payload = _kg_payload("حضانة جديدة", "LIC-NEW-1")
    r = client.post("/api/admin/kindergartens/with-manager", json=payload, headers=auth_headers_admin)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kindergarten"]["status"] in ("ACTIVE", "active")
    assert body["manager"]["must_change_password"] is True

    mgr = test_db.query(models.User).filter_by(id=body["manager"]["id"]).first()
    assert mgr.role == models.UserRole.MANAGER
    assert mgr.kindergarten_id == body["kindergarten"]["id"]


def test_create_kg_with_manager_rolls_back_on_duplicate_username(client, auth_headers_admin, test_db):
    payload = _kg_payload("حضانة أ", "LIC-RB-1")
    r1 = client.post("/api/admin/kindergartens/with-manager", json=payload, headers=auth_headers_admin)
    assert r1.status_code == 201

    # Reuse username but new KG identity -> must fail and NOT create the KG.
    payload2 = _kg_payload("حضانة ب", "LIC-RB-2")
    payload2["manager"]["username"] = payload["manager"]["username"]
    before = test_db.query(models.Kindergarten).count()
    r2 = client.post("/api/admin/kindergartens/with-manager", json=payload2, headers=auth_headers_admin)
    assert r2.status_code in (409, 500)
    assert not r2.json().get("success", True)
    test_db.expire_all()
    assert test_db.query(models.Kindergarten).count() == before  # rolled back


# ---------------------------------------------------------------------------
# §1.4 — Freeze / Unfreeze
# ---------------------------------------------------------------------------

def test_freeze_and_unfreeze_cycle(client, auth_headers_admin, test_db, sample_kindergarten):
    kg_id = sample_kindergarten.id
    mgr = _mk_user(test_db, "mgr_freeze", models.UserRole.MANAGER, kg_id)

    r = client.patch(f"/api/admin/kindergartens/{kg_id}/freeze",
        json={"reason": "Test freeze"}, headers=auth_headers_admin)
    assert r.status_code == 200, r.text
    test_db.expire_all()
    kg = test_db.query(models.Kindergarten).get(kg_id)
    assert kg.status == models.KindergartenStatus.FROZEN
    assert kg.frozen_at is not None
    test_db.refresh(mgr)
    assert mgr.status == models.UserStatus.SUSPENDED

    # Double-freeze rejected.
    r2 = client.patch(f"/api/admin/kindergartens/{kg_id}/freeze", headers=auth_headers_admin, json={"reason": "xx"})
    assert r2.status_code == 400

    r3 = client.patch(f"/api/admin/kindergartens/{kg_id}/activate", headers=auth_headers_admin)
    assert r3.status_code == 200
    test_db.expire_all()
    kg = test_db.query(models.Kindergarten).get(kg_id)
    assert kg.status == models.KindergartenStatus.ACTIVE
    assert kg.frozen_at is None
    test_db.refresh(mgr)
    assert mgr.status == models.UserStatus.ACTIVE


def test_assign_manager_endpoint(client, auth_headers_admin, test_db, sample_kindergarten):
    other_kg = _mk_kg(test_db, "KG other", "LIC-OTHER-EP")
    user = _mk_user(test_db, "mgr_ep", models.UserRole.MANAGER, other_kg.id)

    r = client.post(
        f"/api/admin/kindergartens/{sample_kindergarten.id}/assign-manager",
        json={"user_id": user.id, "replace": False},
        headers=auth_headers_admin,
    )
    assert r.status_code == 200, r.text
    test_db.refresh(user)
    assert user.kindergarten_id == sample_kindergarten.id
