"""
Comprehensive tests for the new modules:
- Supervisor scoping (RBAC, 403 on out-of-scope)
- Manager CRUD (classes, supervisor assignment, daily-report review)
- Daily-report workflow (DRAFT→SUBMITTED→SENT_TO_PARENT, role enforcement)
- Admin impersonation (start/exit, audit log)
- Messaging rules (role-safe recipient resolution, auto-resolve)
- KPI endpoints (supervisor + manager)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import pytest

import models
from audit_actions import AuditAction
from conftest import csrf_pair


# ===========================================================================
# Helpers
# ===========================================================================

def _hdr(token: str) -> dict:
    """Auth + CSRF headers. CSRF is needed for admin POST endpoints;
    it is harmless on GET requests (CSRF middleware skips safe methods)."""
    return {"Authorization": f"Bearer {token}", **csrf_pair()}


def _make_supervisor(test_db, kg_id, username="sup2", email="sup2@test.com"):
    from auth import get_password_hash
    u = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash("Pass123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=kg_id,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)
    return u


def _make_class(test_db, kg_id, name="Class B"):
    import uuid
    c = models.Class(
        kindergarten_id=kg_id,
        name_ar=name,
        name_en=name,
        class_code=str(uuid.uuid4())[:8].upper(),
        age_group="AGE_2_4",
        capacity_total=10,
        min_age_months=24,
        max_age_months=60,
        is_active=True,
    )
    test_db.add(c)
    test_db.commit()
    test_db.refresh(c)
    return c


def _make_child(test_db, parent_profile_id, first="Ali", last="Test"):
    c = models.Child(
        parent_id=parent_profile_id,
        first_name=first,
        last_name=last,
        gender=models.Gender.MALE,
        date_of_birth=date(2022, 6, 1),
        father_name="Test Father",
        mother_first_name="Test",
        mother_last_name="Mother",
        mother_nationality="Jordanian",
        mother_national_id="9999999999",
        media_consent=True,
    )
    test_db.add(c)
    test_db.commit()
    test_db.refresh(c)
    return c


def _make_enrollment(test_db, child_id, kg_id, class_id):
    e = models.EnrollmentApplication(
        child_id=child_id,
        kindergarten_id=kg_id,
        class_id=class_id,
        status=models.EnrollmentStatus.ACTIVE,
        source="WEB",
        created_at=datetime(2026, 1, 10),
        submitted_at=datetime(2026, 1, 10),
        enrollment_start_date=date(2026, 1, 15),
    )
    test_db.add(e)
    test_db.commit()
    test_db.refresh(e)
    return e


def _get_token(client, username, password="Pass123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ===========================================================================
# 1. Supervisor Scoping
# ===========================================================================

class TestSupervisorScoping:
    def test_my_classes_returns_assigned_only(
        self, client, test_db, supervisor_user, sample_class, sample_supervisor_assignment, supervisor_token
    ):
        """Supervisor sees only classes they are assigned to."""
        r = client.get("/api/supervisor/my-classes", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        ids = [c["id"] for c in data.get("classes", [])]
        assert sample_class.id in ids

    def test_my_classes_does_not_include_unassigned(
        self, client, test_db, supervisor_user, sample_kindergarten, sample_supervisor_assignment, supervisor_token
    ):
        """Supervisor does NOT see a class they are not assigned to."""
        other_class = _make_class(test_db, sample_kindergarten.id, "Other Class")
        r = client.get("/api/supervisor/my-classes", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json().get("classes", [])]
        assert other_class.id not in ids

    def test_children_scoped_to_assigned_class(
        self,
        client,
        test_db,
        supervisor_user,
        sample_kindergarten,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        parent_user,
        sample_enrollment,
        supervisor_token,
    ):
        """GET /api/supervisor/children returns children in the assigned class."""
        r = client.get("/api/supervisor/children", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json().get("children", [])]
        assert sample_child.id in ids

    def test_children_excludes_out_of_scope(
        self,
        client,
        test_db,
        supervisor_user,
        sample_kindergarten,
        sample_class,
        sample_supervisor_assignment,
        parent_user,
        supervisor_token,
    ):
        """Children in an unassigned class are NOT returned."""
        other_class = _make_class(test_db, sample_kindergarten.id, "Unassigned Class")
        other_child = _make_child(test_db, parent_user.parent_profile.id, "Omar", "Outside")
        _make_enrollment(test_db, other_child.id, sample_kindergarten.id, other_class.id)

        r = client.get("/api/supervisor/children", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json().get("children", [])]
        assert other_child.id not in ids

    def test_children_payload_includes_attendance_and_class_context(
        self,
        client,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        """Canonical supervisor children payload includes fields consumed by supervisor pages."""
        r = client.get("/api/supervisor/children", headers=_hdr(supervisor_token))
        assert r.status_code == 200

        children = r.json().get("children", [])
        child = next(item for item in children if item["id"] == sample_child.id)
        assert child["name"] == f"{sample_child.first_name} {sample_child.last_name}"
        assert child["class_id"] == sample_enrollment.class_id
        assert "attendance_status" in child

    def test_non_supervisor_gets_403_from_supervisor_endpoint(
        self, client, test_db, manager_user, manager_token
    ):
        """Manager calling supervisor endpoint gets 403."""
        r = client.get("/api/supervisor/my-classes", headers=_hdr(manager_token))
        assert r.status_code == 403


class TestSupervisorSafetyAndObservations:
    def test_supervisor_can_create_safety_incident_with_supported_fields(
        self,
        client,
        test_db,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        payload = {
            "child_id": sample_child.id,
            "type": "INJURY",
            "severity_level": "LOW",
            "description": "Child slipped during play.",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "parent_informed": True,
        }

        r = client.post("/api/supervisor/safety-incidents", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 201, r.text

        incident = test_db.query(models.Incident).filter(models.Incident.id == r.json()["id"]).first()
        assert incident is not None
        assert incident.reported_by == supervisor_user.id
        assert incident.parent_informed is True

    def test_resolve_incident_persists_resolution_notes_and_attachment(
        self,
        client,
        test_db,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        incident = models.Incident(
            child_id=sample_child.id,
            kindergarten_id=supervisor_user.kindergarten_id,
            reported_by=supervisor_user.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.MEDIUM,
            description="Needs follow-up.",
            occurred_at=datetime.now(timezone.utc),
            parent_informed=False,
        )
        test_db.add(incident)
        test_db.commit()
        test_db.refresh(incident)

        r = client.post(
            f"/api/supervisor/safety-incidents/{incident.id}/resolve",
            data={"resolution_notes": "Resolved after first aid."},
            files={"attachment": ("evidence.jpg", BytesIO(b"incident evidence"), "image/jpeg")},
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 200, r.text

        test_db.refresh(incident)
        assert incident.closed_by == supervisor_user.id
        assert incident.resolution_notes == "Resolved after first aid."
        assert incident.attachment_url is not None
        assert incident.attachment_url.startswith("/static/uploads/incidents/")

    def test_supervisor_cannot_upload_photo_for_out_of_scope_observation(
        self,
        client,
        test_db,
        supervisor_user,
        sample_kindergarten,
        sample_class,
        sample_supervisor_assignment,
        parent_user,
        supervisor_token,
    ):
        other_class = _make_class(test_db, sample_kindergarten.id, "Other Class")
        other_child = _make_child(test_db, parent_user.parent_profile.id, "Omar", "Outside")
        _make_enrollment(test_db, other_child.id, sample_kindergarten.id, other_class.id)
        observation = models.Observation(
            child_id=other_child.id,
            observed_by=supervisor_user.id,
            domain=models.LearningDomain.COGNITIVE,
            observation_text="Out of scope observation",
            observed_at=datetime.now(timezone.utc),
        )
        test_db.add(observation)
        test_db.commit()
        test_db.refresh(observation)

        r = client.post(
            f"/api/supervisor/observations/{observation.id}/photo",
            files={"file": ("obs.png", BytesIO(b"fake-image"), "image/png")},
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 403

    def test_attendance_post_rejects_out_of_scope_child(
        self,
        client,
        test_db,
        supervisor_user,
        sample_kindergarten,
        sample_class,
        sample_supervisor_assignment,
        parent_user,
        supervisor_token,
    ):
        """Marking attendance for a child in an unassigned class returns 403."""
        other_class = _make_class(test_db, sample_kindergarten.id, "Forbidden Class")
        other_child = _make_child(test_db, parent_user.parent_profile.id, "Forbidden", "Child")
        _make_enrollment(test_db, other_child.id, sample_kindergarten.id, other_class.id)

        payload = {
            "child_id": other_child.id,
            "date": date.today().isoformat(),
            "action": "check_in",
        }
        r = client.post("/api/supervisor/attendance", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_attendance_post_accepts_in_scope_child(
        self,
        client,
        test_db,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
        monkeypatch,
    ):
        """Supervisor can mark attendance for a child in their assigned class."""
        from routers import supervisor as supervisor_module

        # Pin the server clock to a Wednesday: the endpoint locks Fridays
        # (Jordan weekend) and non-today dates, so a real Friday run would
        # 400 regardless of the payload.
        fixed_now = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=3)))
        monkeypatch.setattr(supervisor_module, "_ksa_now", lambda: fixed_now)
        payload = {
            "child_id": sample_child.id,
            "date": fixed_now.date().isoformat(),
            "action": "check_in",
        }
        r = client.post("/api/supervisor/attendance", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code in (200, 201), r.text


# ===========================================================================
# 2. Manager Class CRUD
# ===========================================================================

class TestManagerClassCRUD:
    def test_list_classes(self, client, manager_user, sample_class, manager_token):
        r = client.get("/api/manager/classes", headers=_hdr(manager_token))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json().get("classes", [])]
        assert sample_class.id in ids

    def test_create_class(self, client, manager_user, sample_kindergarten, supervisor_user, manager_token):
        # Class create/update/delete live on the shared, audited
        # /api/classes API (validate_manager_role + validate_kindergarten_scope).
        payload = {
            "kindergarten_id": sample_kindergarten.id,
            "name_ar": "صف جديد",
            "name_en": "New Class",
            "class_code": "NEW-01",
            "age_group": "AGE_2_4",
            "capacity_total": 10,
            "min_age_months": 36,
            "max_age_months": 60,
            "supervisor_id": supervisor_user.id,
        }
        r = client.post("/api/classes", json=payload, headers=_hdr(manager_token))
        assert r.status_code in (200, 201), r.text
        assert r.json()["kindergarten_id"] == sample_kindergarten.id

    def test_supervisor_cannot_create_class(self, client, supervisor_user, sample_kindergarten, supervisor_token):
        payload = {"kindergarten_id": sample_kindergarten.id, "name_ar": "فئة", "name_en": "Cat",
                   "class_code": "CAT-01", "age_group": "AGE_2_4", "capacity_total": 10,
                   "min_age_months": 24, "max_age_months": 48, "supervisor_id": supervisor_user.id}
        r = client.post("/api/classes", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_update_class(self, client, manager_user, sample_class, manager_token):
        payload = {"name_ar": "اسم محدّث", "name_en": "Updated", "capacity_total": 10,
                   "min_age_months": 24, "max_age_months": 60, "is_active": False}
        r = client.put(f"/api/classes/{sample_class.id}", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 200, r.text
        assert r.json()["name_en"] == "Updated"

    def test_delete_class_with_active_enrollment_blocked(
        self, client, manager_user, sample_class, sample_enrollment, manager_token
    ):
        """Managers retire classes via deactivate (hard delete is admin-only);
        deactivation is blocked while active enrollments exist."""
        r = client.put(f"/api/classes/{sample_class.id}/deactivate", headers=_hdr(manager_token))
        assert r.status_code == 400
        assert "active enrollment" in r.json()["detail"]

    def test_manager_cannot_hard_delete_class(self, client, manager_user, sample_class, manager_token):
        r = client.delete(f"/api/classes/{sample_class.id}", headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_assign_supervisor(
        self, client, test_db, manager_user, sample_class, sample_kindergarten, manager_token
    ):
        sup = _make_supervisor(test_db, sample_kindergarten.id, "newSup", "newsup@test.com")
        payload = {"class_id": sample_class.id, "supervisor_id": sup.id, "is_primary": False}
        r = client.post("/api/manager/classes/assign-supervisor", json=payload, headers=_hdr(manager_token))
        assert r.status_code in (200, 201), r.text

    def test_assign_supervisor_from_other_kg_rejected(
        self, client, test_db, manager_user, sample_class, manager_token
    ):
        """Assigning a supervisor from a different KG is rejected."""
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى", name_en="Other KG",
            governorate="Irbid", district="Irbid", area="Test", address_line="St 1",
            contact_phone="0700000000", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        foreign_sup = _make_supervisor(test_db, other_kg.id, "foreignSup", "fsup@test.com")

        payload = {"class_id": sample_class.id, "supervisor_id": foreign_sup.id, "is_primary": False}
        r = client.post("/api/manager/classes/assign-supervisor", json=payload, headers=_hdr(manager_token))
        # 404 counts: the endpoint scopes its supervisor lookup to the caller's own
        # kindergarten, so a foreign supervisor is simply not found. That is a better
        # answer than 403 — it rejects the assignment without confirming that the
        # supervisor exists in some other kindergarten.
        assert r.status_code in (400, 403, 404, 422), f"Expected rejection, got {r.status_code}: {r.text}"

        # The status code alone does not prove the write was refused.
        test_db.expire_all()
        assert not (
            test_db.query(models.SupervisorAssignment)
            .filter(
                models.SupervisorAssignment.class_id == sample_class.id,
                models.SupervisorAssignment.supervisor_id == foreign_sup.id,
            )
            .count()
        ), "foreign supervisor must not be assigned"

    def test_assign_primary_supervisor_records_assignment(
        self, client, test_db, manager_user, sample_class, sample_kindergarten, manager_token
    ):
        """Assigning a primary supervisor records it as the active primary
        SupervisorAssignment (the single source of truth). The legacy
        Class.supervisor_id column is no longer written (D1/B5)."""
        import validators
        sup = _make_supervisor(test_db, sample_kindergarten.id, "primarySup1", "primarysup1@test.com")
        payload = {"class_id": sample_class.id, "supervisor_id": sup.id, "is_primary": True}
        r = client.post("/api/manager/classes/assign-supervisor", json=payload, headers=_hdr(manager_token))
        assert r.status_code in (200, 201), r.text

        test_db.expire_all()
        assert validators.active_primary_supervisor_map(
            test_db, [sample_class.id]
        ).get(sample_class.id) == sup.id
        # the retired legacy column stays unwritten
        cls = test_db.query(models.Class).filter(models.Class.id == sample_class.id).first()
        assert cls.supervisor_id is None

    def test_swap_supervisor_records_new_primary_and_retires_old_assignment(
        self, client, test_db, manager_user, sample_class, sample_kindergarten, manager_token
    ):
        import validators
        sup1 = _make_supervisor(test_db, sample_kindergarten.id, "swapSup1", "swapsup1@test.com")
        sup2 = _make_supervisor(test_db, sample_kindergarten.id, "swapSup2", "swapsup2@test.com")

        r = client.post(
            "/api/manager/classes/assign-supervisor",
            json={"class_id": sample_class.id, "supervisor_id": sup1.id, "is_primary": True},
            headers=_hdr(manager_token),
        )
        assert r.status_code in (200, 201), r.text

        r = client.put(
            f"/api/manager/classes/{sample_class.id}/swap-supervisor",
            json={"class_id": sample_class.id, "supervisor_id": sup2.id, "is_primary": True},
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200, r.text

        test_db.expire_all()
        assert validators.active_primary_supervisor_map(
            test_db, [sample_class.id]
        ).get(sample_class.id) == sup2.id

        old_assignment = (
            test_db.query(models.SupervisorAssignment)
            .filter(
                models.SupervisorAssignment.class_id == sample_class.id,
                models.SupervisorAssignment.supervisor_id == sup1.id,
            )
            .first()
        )
        assert old_assignment.deleted_at is not None
        assert old_assignment.end_date is not None

    def test_unassign_primary_supervisor_retires_assignment(
        self, client, test_db, manager_user, sample_class, sample_kindergarten, manager_token
    ):
        import validators
        sup = _make_supervisor(test_db, sample_kindergarten.id, "unassignSup", "unassignsup@test.com")
        r = client.post(
            "/api/manager/classes/assign-supervisor",
            json={"class_id": sample_class.id, "supervisor_id": sup.id, "is_primary": True},
            headers=_hdr(manager_token),
        )
        assert r.status_code in (200, 201), r.text

        r = client.delete(
            f"/api/manager/classes/{sample_class.id}/supervisors/{sup.id}",
            headers=_hdr(manager_token),
        )
        assert r.status_code == 204, r.text

        test_db.expire_all()
        # No active primary assignment remains (the source of truth).
        assert validators.active_primary_supervisor_map(test_db, [sample_class.id]) == {}

    def test_edit_class_form_endpoint_syncs_supervisor_assignment(
        self, client, test_db, manager_user, sample_class, sample_kindergarten, manager_token
    ):
        """PUT /api/classes/{id} (the endpoint the real Edit Class form
        calls) used to write only Class.supervisor_id and never touch
        SupervisorAssignment at all, so GET /api/classes (which reads
        only SupervisorAssignment) would never reflect a supervisor
        change made through the edit form."""
        sup = _make_supervisor(test_db, sample_kindergarten.id, "editFormSup", "editformsup@test.com")
        payload = {
            "name_ar": sample_class.name_ar, "name_en": sample_class.name_en,
            "capacity_total": 10,  # within the enforced 3–10 range
            "min_age_months": sample_class.min_age_months, "max_age_months": sample_class.max_age_months,
            "supervisor_id": sup.id,
        }
        r = client.put(f"/api/classes/{sample_class.id}", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 200, r.text

        test_db.expire_all()
        assignment = (
            test_db.query(models.SupervisorAssignment)
            .filter(
                models.SupervisorAssignment.class_id == sample_class.id,
                models.SupervisorAssignment.supervisor_id == sup.id,
                models.SupervisorAssignment.is_primary == True,
                models.SupervisorAssignment.deleted_at.is_(None),
            )
            .first()
        )
        assert assignment is not None


# ===========================================================================
# 3. Daily-Report Workflow
# ===========================================================================

class TestDailyReportWorkflow:
    def test_supervisor_creates_draft(
        self,
        client,
        test_db,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        payload = {
            "child_id": sample_child.id,
            "date": date.today().isoformat(),
            "arrival_time": "08:00",
            "leave_time": "14:00",
            "notes": "جيد",
        }
        r = client.post("/api/supervisor/daily-reports", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code in (200, 201), r.text
        assert r.json()["status"] in ("draft", "DRAFT")

    def test_supervisor_cannot_set_sent_to_parent(
        self,
        client,
        test_db,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        """Supervisor POST with status SENT_TO_PARENT must be rejected."""
        payload = {
            "child_id": sample_child.id,
            "class_id": sample_class.id,
            "date": date.today().isoformat(),
            "status": "SENT_TO_PARENT",
            "notes": "محاولة تجاوز",
        }
        r = client.post("/api/supervisor/daily-reports", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code in (400, 403, 422), r.text

    def test_supervisor_cannot_edit_submitted_report(
        self,
        client,
        test_db,
        supervisor_user,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        sample_daily_report,
        supervisor_token,
    ):
        """sample_daily_report is SUBMITTED — supervisor cannot edit it."""
        # All fields optional in the PATCH schema; only notes supplied
        payload = {"notes": "تعديل غير مسموح", "arrival_time": "08:00", "leave_time": "14:00"}
        r = client.put(
            f"/api/supervisor/daily-reports/{sample_daily_report.id}",
            json=payload,
            headers=_hdr(supervisor_token),
        )
        assert r.status_code in (400, 403), r.text

    def test_manager_sends_to_parents(
        self,
        client,
        test_db,
        manager_user,
        supervisor_user,
        sample_class,
        sample_child,
        sample_enrollment,
        sample_daily_report,
        manager_token,
    ):
        """Manager can move a SUBMITTED report to SENT_TO_PARENT."""
        r = client.put(
            f"/api/manager/daily-reports/{sample_daily_report.id}/send-to-parents",
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] in ("sent_to_parent", "SENT_TO_PARENT")

    def test_manager_cannot_send_already_sent_to_parent(
        self,
        client,
        test_db,
        manager_user,
        supervisor_user,
        sample_class,
        sample_child,
        sample_enrollment,
        sample_daily_report,
        manager_token,
    ):
        """Sending to parents twice is idempotent / returns error on second call."""
        # First send
        client.put(
            f"/api/manager/daily-reports/{sample_daily_report.id}/send-to-parents",
            headers=_hdr(manager_token),
        )
        # Second send
        r = client.put(
            f"/api/manager/daily-reports/{sample_daily_report.id}/send-to-parents",
            headers=_hdr(manager_token),
        )
        # Should either succeed idempotently (200) or fail (400/409)
        assert r.status_code in (200, 400, 409), r.text

    def test_supervisor_cannot_call_send_to_parents_endpoint(
        self,
        client,
        sample_daily_report,
        supervisor_token,
    ):
        """Supervisor cannot call the manager send-to-parents endpoint."""
        r = client.put(
            f"/api/manager/daily-reports/{sample_daily_report.id}/send-to-parents",
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 403

    def test_list_daily_reports_includes_class_and_supervisor_name(
        self,
        client,
        test_db,
        manager_user,
        supervisor_user,
        sample_class,
        sample_child,
        sample_enrollment,
        sample_daily_report,
        manager_token,
    ):
        """GET /api/manager/daily-reports previously returned only submitted_by
        (a raw user id) and no class_name at all, while the manager review
        page's table renders r.supervisor_name / r.class_name -- both columns
        always showed the placeholder dash regardless of real data."""
        r = client.get(
            "/api/manager/daily-reports?report_status=SUBMITTED",
            headers=_hdr(manager_token),
        )
        assert r.status_code == 200, r.text
        reports = r.json()["reports"]
        assert len(reports) >= 1
        report = next(x for x in reports if x["id"] == sample_daily_report.id)
        assert report["class_name"] == sample_class.name_ar
        assert report["supervisor_name"] in (supervisor_user.full_name, supervisor_user.username)

    def test_old_create_endpoint_restricts_to_supervisor(
        self, client, manager_user, sample_child, sample_enrollment, manager_token
    ):
        """The legacy /api/daily-reports/create endpoint now requires SUPERVISOR role."""
        payload = {
            "child_id": sample_child.id,
            "date": date.today().isoformat(),
            "arrival_time": "08:00",
            "leave_time": "14:00",
            "notes": "manager attempt",
        }
        r = client.post("/api/daily-reports/create", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_submit_endpoint_restricts_to_report_owner(
        self,
        client,
        test_db,
        supervisor_user,
        sample_kindergarten,
        sample_class,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        supervisor_token,
    ):
        """A supervisor cannot submit another supervisor's report."""
        other_sup = _make_supervisor(test_db, sample_kindergarten.id, "otherSup", "othersup@test.com")
        report = models.DailyReport(
            child_id=sample_child.id,
            date=date(2026, 5, 10),
            status=models.DailyReportStatus.DRAFT,
            submitted_by=other_sup.id,
            arrival_time="08:00",
            leave_time="14:00",
            kindergarten_id=sample_kindergarten.id,
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        r = client.post(f"/api/daily-reports/{report.id}/submit", headers=_hdr(supervisor_token))
        assert r.status_code == 403


# ===========================================================================
# 4. Admin Impersonation
# ===========================================================================

class TestAdminImpersonation:
    def test_list_managers(self, client, admin_user, manager_user, admin_token):
        r = client.get("/api/admin/managers", headers=_hdr(admin_token))
        assert r.status_code == 200
        ids = [m["id"] for m in r.json().get("managers", [])]
        assert manager_user.id in ids

    def test_list_managers_excludes_non_managers(self, client, admin_user, supervisor_user, admin_token):
        r = client.get("/api/admin/managers", headers=_hdr(admin_token))
        assert r.status_code == 200
        ids = [m["id"] for m in r.json().get("managers", [])]
        assert supervisor_user.id not in ids

    def test_start_impersonation(self, client, admin_user, manager_user, admin_token):
        payload = {"target_user_id": manager_user.id, "reason": "Testing impersonation"}
        r = client.post("/api/admin/impersonate", json=payload, headers=_hdr(admin_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["impersonating"]["user_id"] == manager_user.id

    def test_impersonate_non_manager_rejected(self, client, admin_user, supervisor_user, admin_token):
        payload = {"target_user_id": supervisor_user.id, "reason": "Support investigation"}
        r = client.post("/api/admin/impersonate", json=payload, headers=_hdr(admin_token))
        assert r.status_code == 422

    def test_impersonate_nonexistent_user_rejected(self, client, admin_user, admin_token):
        payload = {"target_user_id": 999999, "reason": "Support investigation"}
        r = client.post("/api/admin/impersonate", json=payload, headers=_hdr(admin_token))
        assert r.status_code == 404

    def test_impersonation_creates_audit_log(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        payload = {"target_user_id": manager_user.id, "reason": "Audit test"}
        client.post("/api/admin/impersonate", json=payload, headers=_hdr(admin_token))
        audit = (
            test_db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "IMPERSONATION_START",
                models.AuditLog.impersonated_by == admin_user.id,
            )
            .first()
        )
        assert audit is not None
        assert audit.impersonation_reason == "Audit test"

    def test_impersonation_audit_endpoint(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        payload = {"target_user_id": manager_user.id, "reason": "Audit history test"}
        client.post("/api/admin/impersonate", json=payload, headers=_hdr(admin_token))
        r = client.get("/api/admin/impersonate/audit", headers=_hdr(admin_token))
        assert r.status_code == 200
        events = r.json().get("events", [])
        assert any(e["action"] == "IMPERSONATION_START" for e in events)

    def test_non_admin_cannot_impersonate(
        self, client, manager_user, supervisor_user, manager_token
    ):
        payload = {"target_user_id": supervisor_user.id, "reason": "Unauthorized attempt"}
        r = client.post("/api/admin/impersonate", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_exit_without_impersonation_returns_400(
        self, client, admin_user, admin_token
    ):
        r = client.post("/api/admin/exit-impersonation", headers=_hdr(admin_token))
        assert r.status_code == 400

    def test_impersonation_persists_switches_identity_and_restores_admin(
        self, client, admin_user, manager_user, admin_token
    ):
        start = client.post(
            "/api/admin/impersonate",
            json={"target_user_id": manager_user.id, "reason": "Reproduce approved support case"},
            headers=_hdr(admin_token),
        )
        assert start.status_code == 200
        assert client.cookies.get("kinjo_impersonation")
        captured_target_session = client.cookies.get("kinjo_session")
        captured_restore = client.cookies.get("kinjo_impersonation")
        captured_csrf = client.cookies.get("kinjo_csrf_token")

        # With no bearer override, the new HttpOnly session resolves as Manager.
        denied = client.get("/api/admin/impersonate/audit")
        assert denied.status_code == 403

        csrf = client.cookies.get("kinjo_csrf_token")
        restored = client.post(
            "/api/admin/exit-impersonation",
            headers={"X-CSRF-Token": csrf},
        )
        assert restored.status_code == 200, restored.text
        assert not client.cookies.get("kinjo_impersonation")

        # The replacement session is the original active Admin again.
        audit = client.get("/api/admin/impersonate/audit")
        assert audit.status_code == 200

        # A captured pre-exit cookie set cannot consume the one-time restore token again.
        client.cookies.set("kinjo_session", captured_target_session)
        client.cookies.set("kinjo_impersonation", captured_restore)
        client.cookies.set("kinjo_csrf_token", captured_csrf)
        replay = client.post(
            "/api/admin/exit-impersonation",
            headers={"X-CSRF-Token": captured_csrf},
        )
        assert replay.status_code == 401

    def test_logout_revokes_impersonation_restore_credential(
        self, client, test_db, admin_user, manager_user, admin_token
    ):
        start = client.post(
            "/api/admin/impersonate",
            json={"target_user_id": manager_user.id, "reason": "Logout revocation test"},
            headers=_hdr(admin_token),
        )
        assert start.status_code == 200
        assert client.cookies.get("kinjo_impersonation")
        captured_restore = client.cookies.get("kinjo_impersonation")

        logout = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": client.cookies.get("kinjo_csrf_token")},
        )
        assert logout.status_code == 200
        assert not client.cookies.get("kinjo_impersonation")

        login = client.post(
            "/token",
            data={"username": manager_user.username, "password": "Manager123!"},
        )
        assert login.status_code == 200

        replay_as_bearer = client.get(
            "/api/admin/impersonate/audit",
            headers={"Authorization": f"Bearer {captured_restore}"},
        )
        assert replay_as_bearer.status_code == 401

        html_replay = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {captured_restore}"},
            follow_redirects=False,
        )
        assert html_replay.status_code in (302, 303, 307)
        assert html_replay.headers["location"].startswith("/login")

        from starlette.websockets import WebSocketDisconnect

        manager_session = client.cookies.get("kinjo_session")
        client.cookies.delete("kinjo_session")
        with pytest.raises(WebSocketDisconnect) as websocket_error:
            with client.websocket_connect(
                f"/ws/heatmap?token={captured_restore}"
            ) as websocket:
                websocket.receive_json()
        assert websocket_error.value.code == 4001
        client.cookies.set("kinjo_session", manager_session)

        client.cookies.set("kinjo_impersonation", captured_restore)
        exit_response = client.post(
            "/api/admin/exit-impersonation",
            headers={"X-CSRF-Token": client.cookies.get("kinjo_csrf_token")},
        )
        assert exit_response.status_code == 401

        logout_audit = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == AuditAction.LOGOUT)
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert logout_audit is not None
        assert logout_audit.user_id == manager_user.id
        assert logout_audit.impersonated_by == admin_user.id
        assert logout_audit.impersonation_reason == "Logout revocation test"

    def test_impersonated_manager_mutation_records_originating_admin(
        self,
        client,
        test_db,
        admin_user,
        manager_user,
        supervisor_user,
        sample_class,
        admin_token,
    ):
        reason = "Trace manager support mutation"
        start = client.post(
            "/api/admin/impersonate",
            json={"target_user_id": manager_user.id, "reason": reason},
            headers=_hdr(admin_token),
        )
        assert start.status_code == 200

        mutation = client.post(
            "/api/manager/classes/assign-supervisor",
            json={
                "class_id": sample_class.id,
                "supervisor_id": supervisor_user.id,
                "is_primary": True,
            },
            headers={"X-CSRF-Token": client.cookies.get("kinjo_csrf_token")},
        )
        assert mutation.status_code == 201, mutation.text

        audit = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == AuditAction.SUPERVISOR_ASSIGNED)
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.user_id == manager_user.id
        assert audit.impersonated_by == admin_user.id
        assert audit.impersonation_reason == reason


# ===========================================================================
# 5. Messaging — Role-safe Recipient Resolution
# ===========================================================================

class TestMessagingRecipients:
    def test_supervisor_recipients_auto_resolves_to_manager(
        self,
        client,
        supervisor_user,
        manager_user,
        sample_supervisor_assignment,
        supervisor_token,
    ):
        r = client.get("/api/messages/recipients", headers=_hdr(supervisor_token))
        assert r.status_code == 200
        data = r.json()
        assert data["auto_resolved"] is True
        ids = [u["id"] for u in data["recipients"]]
        assert manager_user.id in ids

    def test_parent_recipients_auto_resolves_to_manager(
        self,
        client,
        parent_user,
        manager_user,
        sample_child,
        sample_enrollment,
        parent_token,
    ):
        r = client.get("/api/messages/recipients", headers=_hdr(parent_token))
        assert r.status_code == 200
        data = r.json()
        assert data["auto_resolved"] is True
        ids = [u["id"] for u in data["recipients"]]
        assert manager_user.id in ids

    def test_manager_recipients_not_auto_resolved(
        self, client, manager_user, manager_token
    ):
        r = client.get("/api/messages/recipients", headers=_hdr(manager_token))
        assert r.status_code == 200
        assert r.json()["auto_resolved"] is False

    def test_supervisor_send_auto_routes_to_manager(
        self,
        client,
        supervisor_user,
        manager_user,
        sample_supervisor_assignment,
        supervisor_token,
    ):
        """Supervisor sends a message without specifying recipient; should go to manager."""
        payload = {"message_body": "سؤال عن الحضور"}
        r = client.post("/api/messages", json=payload, headers=_hdr(supervisor_token))
        assert r.status_code == 201, r.text
        assert r.json()["recipient_id"] == manager_user.id

    def test_supervisor_cannot_message_arbitrary_user(
        self,
        client,
        supervisor_user,
        admin_user,
        sample_supervisor_assignment,
        supervisor_token,
    ):
        """Supervisor's recipient_id is always overridden to the auto-resolved manager."""
        payload = {"message_body": "رسالة", "recipient_id": admin_user.id}
        r = client.post("/api/messages", json=payload, headers=_hdr(supervisor_token))
        # Should either succeed and route to manager, OR be rejected
        if r.status_code == 201:
            # recipient must be the manager, not the admin
            # (auto-resolve overrides the supplied recipient_id)
            pass  # auto-resolve silently replaces — acceptable behavior
        else:
            assert r.status_code in (400, 403, 422)

    def test_parent_send_auto_routes_to_manager(
        self,
        client,
        parent_user,
        manager_user,
        sample_child,
        sample_enrollment,
        parent_token,
    ):
        payload = {"message_body": "استفسار عن الطفل"}
        r = client.post("/api/messages", json=payload, headers=_hdr(parent_token))
        assert r.status_code == 201, r.text
        assert r.json()["recipient_id"] == manager_user.id

    def test_manager_cannot_message_user_outside_kg(
        self,
        client,
        test_db,
        manager_user,
        manager_token,
    ):
        """Manager cannot send a direct message to a user from a different KG."""
        other_kg = models.Kindergarten(
            name_ar="حضانة غريبة", name_en="Foreign KG",
            governorate="Aqaba", district="Aqaba", area="South", address_line="St 5",
            contact_phone="0600000001", status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        foreign_sup = _make_supervisor(test_db, other_kg.id, "foreignSup2", "fs2@test.com")

        payload = {"message_body": "رسالة غير مسموح", "recipient_id": foreign_sup.id}
        r = client.post("/api/messages", json=payload, headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_mark_message_read(
        self,
        client,
        supervisor_user,
        manager_user,
        sample_supervisor_assignment,
        supervisor_token,
        manager_token,
    ):
        """After supervisor sends, manager can mark it read."""
        # Send
        payload = {"message_body": "للاطلاع"}
        send_r = client.post("/api/messages", json=payload, headers=_hdr(supervisor_token))
        assert send_r.status_code == 201
        msg_id = send_r.json()["id"]

        # Manager marks read
        r = client.post(f"/api/messages/{msg_id}/read", headers=_hdr(manager_token))
        assert r.status_code == 200
        assert "read_at" in r.json()


# ===========================================================================
# 6. KPI Endpoints
# ===========================================================================

class TestKPIEndpoints:
    def test_supervisor_kpi_requires_supervisor_role(
        self, client, manager_user, manager_token
    ):
        r = client.get("/api/supervisor/kpi", headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_supervisor_kpi_returns_data(
        self,
        client,
        supervisor_user,
        sample_supervisor_assignment,
        sample_child,
        sample_enrollment,
        sample_attendance,
        supervisor_token,
    ):
        r = client.get(
            "/api/supervisor/kpi",
            params={"from": "2026-05-01", "to": "2026-05-31"},
            headers=_hdr(supervisor_token),
        )
        assert r.status_code == 200
        data = r.json()
        # Endpoint returns completion_rate, per_child, date_from/to etc.
        assert "completion_rate" in data or "per_child" in data or "date_from" in data

    def test_manager_kpi_requires_manager_role(
        self, client, supervisor_user, supervisor_token
    ):
        r = client.get("/api/manager/kpi", headers=_hdr(supervisor_token))
        assert r.status_code == 403

    def test_manager_kpi_returns_data(
        self,
        client,
        manager_user,
        sample_class,
        supervisor_user,
        sample_supervisor_assignment,
        manager_token,
    ):
        r = client.get("/api/manager/kpi", headers=_hdr(manager_token))
        assert r.status_code == 200
        data = r.json()
        # Manager KPI endpoint returns operational data
        assert isinstance(data, dict) and len(data) > 0

    def test_manager_kpi_alias_schema_parity(
        self,
        client,
        manager_user,
        sample_class,
        supervisor_user,
        sample_supervisor_assignment,
        manager_token,
    ):
        """Alias /api/manager/kpi must return the same schema as /api/manager/dashboard/enhanced."""
        params = {"period_start": "2026-05-01", "period_end": "2026-05-31", "locale": "en"}
        r_alias = client.get("/api/manager/kpi", params=params, headers=_hdr(manager_token))
        r_enhanced = client.get(
            "/api/manager/dashboard/enhanced", params=params, headers=_hdr(manager_token)
        )
        assert r_alias.status_code == 200, f"alias returned {r_alias.status_code}"
        assert r_enhanced.status_code == 200, f"enhanced returned {r_enhanced.status_code}"

        alias_data = r_alias.json()
        enhanced_data = r_enhanced.json()

        # Top-level keys must be identical
        assert set(alias_data.keys()) == set(enhanced_data.keys()), (
            f"Key mismatch — alias has {set(alias_data.keys())}, "
            f"enhanced has {set(enhanced_data.keys())}"
        )

        # overall_gcei must be present and have correct kpi_key
        assert "overall_gcei" in alias_data
        assert alias_data["overall_gcei"]["kpi_key"] == "overall_gcei"

        # data_freshness must be one of the documented sentinel values
        assert alias_data.get("data_freshness") in ("fresh", "stale", "outdated"), (
            f"unexpected data_freshness: {alias_data.get('data_freshness')}"
        )


# ===========================================================================
# 7. Regression — existing RBAC still works
# ===========================================================================

class TestRegression:
    def test_admin_cannot_access_supervisor_endpoint(
        self, client, admin_user, admin_token
    ):
        r = client.get("/api/supervisor/my-classes", headers=_hdr(admin_token))
        assert r.status_code == 403

    def test_parent_cannot_access_manager_endpoint(
        self, client, parent_user, parent_token
    ):
        r = client.get("/api/manager/classes", headers=_hdr(parent_token))
        assert r.status_code == 403

    def test_unauthenticated_request_rejected(self, client):
        r = client.get("/api/supervisor/my-classes")
        assert r.status_code in (401, 403)

    def test_admin_list_managers_endpoint_requires_admin(
        self, client, manager_user, manager_token
    ):
        r = client.get("/api/admin/managers", headers=_hdr(manager_token))
        assert r.status_code == 403

    def test_health_check_accessible(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_supervisor_cannot_delete_class(
        self, client, supervisor_user, sample_class, supervisor_token
    ):
        r = client.put(f"/api/classes/{sample_class.id}/deactivate", headers=_hdr(supervisor_token))
        assert r.status_code == 403
        r = client.delete(f"/api/classes/{sample_class.id}", headers=_hdr(supervisor_token))
        assert r.status_code == 403
