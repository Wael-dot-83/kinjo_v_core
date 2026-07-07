"""
End-to-end Manager workflow integration test.

Builds two fully isolated kindergartens (KG A / KG B) with their own
manager, supervisor, parent, child, class and daily report, then exercises
the complete Manager operational workflow for KG A and asserts that Manager A
can neither read nor mutate any KG B resource through the Manager API surface.

Auth is injected via dependency_overrides (same pattern as test_frontend.py),
so no real JWT is required.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from auth import get_password_hash
import models
from audit_actions import AuditAction
from dependencies import get_current_user, get_current_user_or_redirect


# ---------------------------------------------------------------------------
# Entity factories (use the test DB session directly)
# ---------------------------------------------------------------------------

def _kg(test_db, name_ar, name_en):
    kg = models.Kindergarten(
        name_ar=name_ar,
        name_en=name_en,
        governorate="Irbid",
        district="Irbid",
        area="Test",
        address_line="St 1",
        contact_phone="0700000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


def _user(test_db, username, role, kindergarten_id, email=None):
    u = models.User(
        username=username,
        email=email or f"{username}@test.com",
        hashed_password=get_password_hash("Password123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id,
    )
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)
    return u


def _parent_profile(test_db, user):
    p = models.ParentProfile(
        user_id=user.id,
        first_name="Walid",
        last_name="Parent",
        phone_number="0790000000",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        home_governorate="Irbid",
        home_district="Irbid",
        home_area="Test",
        home_address_line="Addr 1",
    )
    test_db.add(p)
    test_db.commit()
    test_db.refresh(p)
    return p


def _child(test_db, parent_profile, first="Child", last="A"):
    c = models.Child(
        parent_id=parent_profile.id,
        first_name=first,
        last_name=last,
        gender=models.Gender.MALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="Father",
        mother_first_name="Mother",
        mother_last_name="Last",
        mother_nationality="Jordanian",
    )
    test_db.add(c)
    test_db.commit()
    test_db.refresh(c)
    return c


def _class(test_db, kg, name_ar):
    c = models.Class(
        kindergarten_id=kg.id,
        name_ar=name_ar,
        name_en=name_ar,
        class_code=f"CLS-{uuid.uuid4().hex[:8].upper()}",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=72,
        is_active=True,
    )
    test_db.add(c)
    test_db.commit()
    test_db.refresh(c)
    return c


def _enrollment(test_db, child, kg, class_):
    e = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=class_.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add(e)
    test_db.commit()
    test_db.refresh(e)
    return e


def _daily_report(test_db, child, kg, submitted_by, status=models.DailyReportStatus.SUBMITTED):
    r = models.DailyReport(
        child_id=child.id,
        kindergarten_id=kg.id,
        date=date.today(),
        status=status,
        submitted_by=submitted_by,
        arrival_time="08:00",
    )
    test_db.add(r)
    test_db.commit()
    test_db.refresh(r)
    return r


@pytest.fixture
def scenario(test_db):
    """Two fully isolated kindergartens with manager/supervisor/parent/child/report."""
    kg_a = _kg(test_db, "حضانة أ", "KG A")
    kg_b = _kg(test_db, "حضانة ب", "KG B")

    mgr_a = _user(test_db, "mgr_a", models.UserRole.MANAGER, kg_a.id, "mgr_a@test.com")
    mgr_b = _user(test_db, "mgr_b", models.UserRole.MANAGER, kg_b.id, "mgr_b@test.com")
    sup_a = _user(test_db, "sup_a", models.UserRole.SUPERVISOR, kg_a.id, "sup_a@test.com")
    sup_b = _user(test_db, "sup_b", models.UserRole.SUPERVISOR, kg_b.id, "sup_b@test.com")
    par_a = _user(test_db, "par_a", models.UserRole.PARENT, kg_a.id, "par_a@test.com")
    par_b = _user(test_db, "par_b", models.UserRole.PARENT, kg_b.id, "par_b@test.com")

    pp_a = _parent_profile(test_db, par_a)
    pp_b = _parent_profile(test_db, par_b)

    child_a = _child(test_db, pp_a, "Child", "A")
    child_b = _child(test_db, pp_b, "Child", "B")

    class_a = _class(test_db, kg_a, "شعبة أ")
    class_b = _class(test_db, kg_b, "شعبة ب")

    _enrollment(test_db, child_a, kg_a, class_a)
    _enrollment(test_db, child_b, kg_b, class_b)

    report_a = _daily_report(test_db, child_a, kg_a, sup_a.id)
    report_b = _daily_report(test_db, child_b, kg_b, sup_b.id)

    return {
        "kg_a": kg_a, "kg_b": kg_b,
        "mgr_a": mgr_a, "mgr_b": mgr_b,
        "sup_a": sup_a, "sup_b": sup_b,
        "par_a": par_a, "par_b": par_b,
        "child_a": child_a, "child_b": child_b,
        "class_a": class_a, "class_b": class_b,
        "report_a": report_a, "report_b": report_b,
    }


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_redirect] = lambda: user


def _clear():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_redirect, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestManagerWorkflowE2E:
    def test_manager_dashboard_scoped_to_own_kg(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            r = client.get("/api/manager/dashboard")
            assert r.status_code == 200, r.text
            data = r.json()
            # Dashboard must only describe KG A, never KG B.
            assert data["kindergarten"]["id"] == scenario["kg_a"].id
            assert data["summary"]["active_enrollments"] == 1
        finally:
            _clear()

    def test_manager_workflow_create_class_assign_supervisor(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            # Canonical class creation lives on /api/classes (manager-scoped).
            payload = {
                "kindergarten_id": scenario["kg_a"].id,
                "name_ar": "شعبة جديدة",
                "name_en": "New Class",
                "class_code": "NEW-01",
                "age_group": "AGE_2_4",
                "capacity_total": 10,
                "min_age_months": 24,
                "max_age_months": 60,
                "supervisor_id": scenario["sup_a"].id,
            }
            r = client.post("/api/classes", json=payload)
            assert r.status_code in (200, 201), r.text
            assert r.json()["kindergarten_id"] == scenario["kg_a"].id

            new_class_id = r.json()["id"]
            r = client.post(
                "/api/manager/classes/assign-supervisor",
                json={"class_id": new_class_id, "supervisor_id": scenario["sup_a"].id, "is_primary": True},
            )
            assert r.status_code in (200, 201), r.text
        finally:
            _clear()

    def test_manager_views_children_and_moves_child(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            r = client.get("/api/manager/children")
            assert r.status_code == 200, r.text
            child_ids = [c["id"] for c in r.json()["children"]]
            assert scenario["child_a"].id in child_ids
            # KG B child must NOT leak into Manager A's list.
            assert scenario["child_b"].id not in child_ids

            r = client.post(
                "/api/manager/children/move-class",
                json={
                    "child_id": scenario["child_a"].id,
                    "from_class_id": scenario["class_a"].id,
                    "to_class_id": scenario["class_a"].id,
                },
            )
            assert r.status_code == 200, r.text
        finally:
            _clear()

    def test_manager_edits_and_sends_daily_report(self, client, scenario, test_db):
        try:
            _as(scenario["mgr_a"])
            rid = scenario["report_a"].id
            r = client.put(f"/api/manager/daily-reports/{rid}", json={"notes": "Reviewed by manager."})
            assert r.status_code == 200, r.text

            r = client.put(f"/api/manager/daily-reports/{rid}/send-to-parents")
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "SENT_TO_PARENT"

            # Parent notification message must have been created.
            test_db.expire_all()
            msg = (
                test_db.query(models.Message)
                .filter(models.Message.recipient_id == scenario["par_a"].id)
                .first()
            )
            assert msg is not None

            # AuditLog must record the send.
            audit = (
                test_db.query(models.AuditLog)
                .filter(models.AuditLog.action == AuditAction.DAILY_REPORT_SENT_TO_PARENT)
                .first()
            )
            assert audit is not None
        finally:
            _clear()

    def test_manager_cannot_access_kg_b_data(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            # Editing KG B's report is rejected (out of scope).
            r = client.put(
                f"/api/manager/daily-reports/{scenario['report_b'].id}",
                json={"notes": "x"},
            )
            assert r.status_code in (403, 404), r.text

            # Assigning a supervisor to a KG B class is rejected. Cross-tenant
            # access returns 404 (no existence leak) after the S2 scope unification.
            r = client.post(
                "/api/manager/classes/assign-supervisor",
                json={"class_id": scenario["class_b"].id, "supervisor_id": scenario["sup_b"].id},
            )
            assert r.status_code in (400, 403, 404, 422), r.text

            # KG B child must not appear in Manager A's children list.
            r = client.get("/api/manager/children")
            ids = [c["id"] for c in r.json()["children"]]
            assert scenario["child_b"].id not in ids
        finally:
            _clear()

    def test_null_kindergarten_manager_rejected(self, client):
        try:
            # The DB enforces `manager_must_have_kindergarten`, so a MANAGER with a
            # NULL kindergarten cannot be persisted. Exercise the API guard with an
            # in-memory user (never committed) to validate _require_manager's 403.
            mgr = models.User(
                username="mgr_null",
                email="mgr_null@test.com",
                hashed_password=get_password_hash("Password123!"),
                role=models.UserRole.MANAGER,
                status=models.UserStatus.ACTIVE,
                kindergarten_id=None,
            )
            _as(mgr)
            for path in ("/api/manager/dashboard", "/api/manager/children", "/api/manager/supervisors"):
                r = client.get(path)
                assert r.status_code == 403, f"{path} -> {r.status_code}: {r.text}"
        finally:
            _clear()

    def test_manager_pages_render_for_manager(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            for page in (
                "/dashboard",
                "/classes",
                "/manager/supervisors",
                "/children",
                "/daily-reports",
                "/manager/absence-requests",
                "/manager/kpi",
                "/manager/benchmarking",
            ):
                r = client.get(page)
                assert r.status_code in (200, 302), f"{page} -> {r.status_code}: {r.text}"
        finally:
            _clear()

    def test_single_canonical_class_crud_no_duplicate_manager_mutations(self, client, scenario):
        try:
            _as(scenario["mgr_a"])
            # The duplicate POST/PUT/DELETE /api/manager/classes write paths must
            # be removed; class create / update / deactivate live on /api/classes.
            for method, path in (
                ("post", "/api/manager/classes"),
                ("put", f"/api/manager/classes/{scenario['class_a'].id}"),
                ("delete", f"/api/manager/classes/{scenario['class_a'].id}"),
            ):
                r = getattr(client, method)(path, json={}) if method != "delete" else client.delete(path)
                assert r.status_code in (404, 405), f"{method} {path} -> {r.status_code}: {r.text}"

            # The manager-scoped READ still exists and is KG-scoped.
            r = client.get("/api/manager/classes")
            assert r.status_code == 200, r.text
            ids = [c["id"] for c in r.json()["classes"]]
            assert scenario["class_a"].id in ids

            # Canonical create works on /api/classes for the manager's KG.
            r = client.post(
                "/api/classes",
                json={
                    "kindergarten_id": scenario["kg_a"].id,
                    "name_ar": "شعبة كانون",
                    "name_en": "Canon Class",
                    "class_code": "CAN-01",
                    "age_group": "AGE_2_4",
                    "capacity_total": 10,
                    "min_age_months": 24,
                    "max_age_months": 60,
                    "supervisor_id": scenario["sup_a"].id,
                },
            )
            assert r.status_code in (200, 201), r.text
        finally:
            _clear()
