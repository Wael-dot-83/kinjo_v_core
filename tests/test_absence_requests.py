"""
Tests for the Absence Request workflow:
- Parent creates request
- Parent lists requests
- Parent cancels request
- Manager approves request (auto-creates attendance)
- Manager rejects request
- Overlap rejection
- Ownership validation
- Attendance correction with notification
"""
import pytest
import inspect
from datetime import date, timedelta
from pathlib import Path
import models


# ─── Helpers ───────────────────────────────────────────────────────────

def _tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()

def _day_after():
    return (date.today() + timedelta(days=2)).isoformat()

def _past():
    return (date.today() - timedelta(days=1)).isoformat()


# ─── Parent: create ───────────────────────────────────────────────────

class TestParentCreateAbsence:
    def test_parent_page_posts_to_canonical_request_contract(self):
        source = Path("templates/attendance/absence_requests.html").read_text(
            encoding="utf-8"
        )
        assert "fetch('/api/absence-requests'" in source
        assert "fetch('/api/attendance/absence-requests'" not in source
        assert "start_date:" in source
        assert "end_date:" in source
        assert "Authorization': 'Bearer" not in source
        assert "AuthStorage.getToken()" not in source
        assert 'min="{{ min_absence_date }}"' in source

        route_source = Path("scripts/compat/frontend_orig.py").read_text(
            encoding="utf-8"
        )
        assert '"min_absence_date": _today() + timedelta(days=1)' in route_source

    def test_parent_cookie_session_requires_and_accepts_matching_csrf(
        self, client, parent_user, sample_child, active_enrollment,
    ):
        login = client.post(
            "/token",
            data={"username": parent_user.username, "password": "Parent123!"},
        )
        assert login.status_code == 200, login.text
        csrf = client.cookies.get("kinjo_csrf_token")
        assert client.cookies.get("kinjo_session")
        assert csrf

        payload = {
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "cookie csrf contract",
        }
        missing = client.post("/api/absence-requests", json=payload)
        assert missing.status_code == 400
        mismatched = client.post(
            "/api/absence-requests",
            json=payload,
            headers={"X-CSRF-Token": "wrong"},
        )
        assert mismatched.status_code == 400
        accepted = client.post(
            "/api/absence-requests",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert accepted.status_code == 201, accepted.text

    def test_create_success(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "زيارة طبيب",
        }, headers=auth_headers_parent)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "SUBMITTED"
        assert "id" in data

    def test_create_rejects_past_date(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _past(),
            "end_date": _tomorrow(),
            "reason": "سبب ما",
        }, headers=auth_headers_parent)
        assert resp.status_code == 422  # Pydantic validation

    def test_create_rejects_end_before_start(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _day_after(),
            "end_date": _tomorrow(),
            "reason": "سبب ما",
        }, headers=auth_headers_parent)
        assert resp.status_code == 422  # Pydantic validation

    def test_create_rejects_span_longer_than_a_year(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        """The span is the loop bound of a write path, not just a validation nicety.

        Approving an absence writes one attendance row per day in the span. Before
        MAX_ABSENCE_SPAN_DAYS this request was accepted with 201 — a 2,912,246-day
        span that a manager could detonate into ~2.9M SELECT+INSERT pairs on a sync
        worker. Parent-supplied input, so the bound belongs at the door.
        """
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": "9999-12-31",
            "reason": "سبب ما",
        }, headers=auth_headers_parent)
        assert resp.status_code == 422, (
            f"a 2.9M-day absence was accepted with {resp.status_code}; approving it "
            "loops once per day"
        )

    def test_create_accepts_span_up_to_the_limit(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        """The bound must not break legitimate long absences — 366 days inclusive."""
        start = date.today() + timedelta(days=1)
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=365)).isoformat(),  # 366 inclusive
            "reason": "سبب ما",
        }, headers=auth_headers_parent)
        assert resp.status_code == 201, (
            f"a 366-day absence (the documented limit) was rejected with "
            f"{resp.status_code}: {resp.text[:200]}"
        )

    def test_create_wrong_child(self, client, auth_headers_parent, parent_user, test_db, sample_kindergarten):
        """Parent cannot submit for a child that doesn't belong to them."""
        other_parent_user = models.User(
            username="otherparent@test.com",
            email="otherparent@test.com",
            hashed_password="x",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other_parent_user)
        test_db.commit()
        other_profile = models.ParentProfile(
            user_id=other_parent_user.id,
            first_name="Other",
            last_name="Parent",
            phone_number="+962790000000",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Sweileh",
            home_address_line="456 Street",
        )
        test_db.add(other_profile)
        test_db.commit()
        other_child = models.Child(
            parent_id=other_profile.id,
            first_name="Noor",
            last_name="Other",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="X Y",
            mother_first_name="Z",
            mother_last_name="W",
            mother_nationality="Jordanian",
        )
        test_db.add(other_child)
        test_db.commit()

        resp = client.post("/api/absence-requests", json={
            "child_id": other_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "هذا ليس طفلي",
        }, headers=auth_headers_parent)
        assert resp.status_code == 404

    def test_create_no_active_enrollment(self, client, auth_headers_parent, parent_user, sample_child):
        """Should fail if child has no active enrollment."""
        resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "مرض",
        }, headers=auth_headers_parent)
        assert resp.status_code == 400

    def test_create_overlap_rejected(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        """Overlapping requests should be rejected."""
        # First request
        resp1 = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "السبب الأول",
        }, headers=auth_headers_parent)
        assert resp1.status_code == 201

        # Overlapping request
        resp2 = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "السبب الثاني",
        }, headers=auth_headers_parent)
        assert resp2.status_code == 409


# ─── Parent: list & cancel ────────────────────────────────────────────

class TestParentListCancel:
    def test_list(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        # Create a request first
        client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "زيارة",
        }, headers=auth_headers_parent)

        resp = client.get("/api/absence-requests", headers=auth_headers_parent)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_cancel_submitted(self, client, auth_headers_parent, parent_user, sample_child, active_enrollment):
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "إلغاء",
        }, headers=auth_headers_parent)
        rid = create_resp.json()["id"]

        cancel_resp = client.post(f"/api/absence-requests/{rid}/cancel", headers=auth_headers_parent)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELLED"

    def test_parent_without_profile_cannot_cancel_another_parents_request(
        self, client, test_db, auth_headers_parent, parent_user,
        sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "ownership regression",
        }, headers=auth_headers_parent)
        assert created.status_code == 201

        profileless = models.User(
            username="profileless_parent",
            email="profileless_parent@test.com",
            hashed_password="x",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(profileless)
        test_db.commit()
        from auth import create_access_token
        token = create_access_token(data={"sub": profileless.username})

        response = client.post(
            f"/api/absence-requests/{created.json()['id']}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        request = test_db.get(models.AbsenceRequest, created.json()["id"])
        assert request.status == models.AbsenceRequestStatus.SUBMITTED

    def test_approved_request_cannot_be_cancelled_and_attendance_remains_consistent(
        self, client, test_db, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "approved cancellation regression",
        }, headers=auth_headers_parent)
        assert created.status_code == 201
        request_id = created.json()["id"]
        approved = client.post(
            f"/api/absence-requests/{request_id}/approve",
            json={},
            headers=auth_headers_manager,
        )
        assert approved.status_code == 200

        cancelled = client.post(
            f"/api/absence-requests/{request_id}/cancel",
            headers=auth_headers_parent,
        )
        assert cancelled.status_code == 400
        request = test_db.get(models.AbsenceRequest, request_id)
        assert request.status == models.AbsenceRequestStatus.APPROVED
        attendance = test_db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == sample_child.id,
            models.AttendanceLog.date == date.today() + timedelta(days=1),
        ).one()
        assert attendance.status == models.AttendanceStatus.ABSENT


# ─── Manager: approve ─────────────────────────────────────────────────

class TestManagerApprove:
    def test_approve_creates_attendance(
        self, client, test_db, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        # Parent creates request
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "مرض",
        }, headers=auth_headers_parent)
        assert create_resp.status_code == 201
        rid = create_resp.json()["id"]

        # Manager approves
        approve_resp = client.post(
            f"/api/absence-requests/{rid}/approve",
            json={"decision_note": "سلامات"},
            headers=auth_headers_manager,
        )
        assert approve_resp.status_code == 200
        body = approve_resp.json()
        assert body["status"] == "APPROVED"
        assert body["attendance_records_created"] >= 1

        # Verify attendance records
        tomorrow = date.today() + timedelta(days=1)
        att = test_db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == sample_child.id,
            models.AttendanceLog.date == tomorrow,
        ).first()
        assert att is not None
        assert att.status == models.AttendanceStatus.ABSENT

    def test_approve_already_approved(
        self, client, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "سبب",
        }, headers=auth_headers_parent)
        rid = create_resp.json()["id"]

        # Approve once
        client.post(f"/api/absence-requests/{rid}/approve", json={}, headers=auth_headers_manager)

        # Try again
        resp = client.post(f"/api/absence-requests/{rid}/approve", json={}, headers=auth_headers_manager)
        assert resp.status_code == 400

    def test_approve_rejects_conflicting_present_attendance(
        self, client, test_db, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, sample_class, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "attendance conflict",
        }, headers=auth_headers_parent)
        assert created.status_code == 201
        attendance = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=date.today() + timedelta(days=1),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager_user.id,
        )
        test_db.add(attendance)
        test_db.commit()

        response = client.post(
            f"/api/absence-requests/{created.json()['id']}/approve",
            json={},
            headers=auth_headers_manager,
        )
        assert response.status_code == 409
        request = test_db.get(models.AbsenceRequest, created.json()["id"])
        assert request.status == models.AbsenceRequestStatus.SUBMITTED
        assert attendance.status == models.AttendanceStatus.PRESENT

    def test_decision_state_changes_use_atomic_conditional_updates(self):
        import api.absence_requests as endpoint
        import inspect

        for handler in (
            endpoint.cancel_absence_request,
            endpoint.approve_absence_request,
            endpoint.reject_absence_request,
        ):
            source = inspect.getsource(handler)
            assert "AbsenceRequest.status == models.AbsenceRequestStatus.SUBMITTED" in source
            assert ".update(" in source
            assert "transitioned != 1" in source


class TestManagerAbsencePageContract:
    def test_admin_view_is_read_only(self):
        source = Path("templates/manager/absence_requests.html").read_text(
            encoding="utf-8"
        )
        assert "const CAN_DECIDE" in source
        assert "CAN_DECIDE && r.status === 'SUBMITTED'" in source


# ─── Manager: reject ──────────────────────────────────────────────────

class TestManagerReject:
    def test_reject(
        self, client, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "سفر",
        }, headers=auth_headers_parent)
        rid = create_resp.json()["id"]

        reject_resp = client.post(
            f"/api/absence-requests/{rid}/reject",
            json={"decision_note": "غير مقبول"},
            headers=auth_headers_manager,
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "REJECTED"


# ─── Manager: list ────────────────────────────────────────────────────

class TestManagerList:
    def test_manager_sees_kg_requests(
        self, client, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "مرض",
        }, headers=auth_headers_parent)

        resp = client.get("/api/absence-requests", headers=auth_headers_manager)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "child_name" in data[0]
        assert data[0]["child_name"]

    def test_supervisor_cannot_list_requests(
        self, client, auth_headers_supervisor, supervisor_user,
    ):
        resp = client.get("/api/absence-requests", headers=auth_headers_supervisor)
        assert resp.status_code == 403

    def test_admin_can_list_requests(
        self, client, auth_headers_parent, auth_headers_admin,
        parent_user, admin_user, sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "admin national read",
        }, headers=auth_headers_parent)
        assert created.status_code == 201

        resp = client.get("/api/absence-requests", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert created.json()["id"] in {item["id"] for item in resp.json()}


# ─── Attendance correction ────────────────────────────────────────────

class TestAttendanceCorrection:
    def test_correct_status(
        self, client, test_db, auth_headers_manager,
        manager_user, sample_child, sample_kindergarten, sample_class,
    ):
        # Create an attendance record
        att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=date.today(),
            status=models.AttendanceStatus.ABSENT,
            recorded_by=manager_user.id,
        )
        test_db.add(att)
        test_db.commit()
        test_db.refresh(att)

        resp = client.patch(
            f"/api/attendance/{att.id}/status",
            json={"new_status": "PRESENT", "notes": "تصحيح"},
            headers=auth_headers_manager,
        )
        assert resp.status_code == 200
        assert resp.json()["old_status"] == "ABSENT"
        assert resp.json()["new_status"] == "PRESENT"

    def test_correct_no_change(
        self, client, test_db, auth_headers_manager,
        manager_user, sample_child, sample_kindergarten, sample_class,
    ):
        att = models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=date.today(),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager_user.id,
        )
        test_db.add(att)
        test_db.commit()
        test_db.refresh(att)

        resp = client.patch(
            f"/api/attendance/{att.id}/status",
            json={"new_status": "PRESENT"},
            headers=auth_headers_manager,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "No change needed"


# ─── Role enforcement ─────────────────────────────────────────────────

class TestRoleEnforcement:
    def test_manager_cannot_create_request(self, client, auth_headers_manager, manager_user):
        resp = client.post("/api/absence-requests", json={
            "child_id": 1,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "test",
        }, headers=auth_headers_manager)
        assert resp.status_code == 403

    def test_parent_cannot_approve(self, client, auth_headers_parent, parent_user):
        resp = client.post("/api/absence-requests/9999/approve", json={}, headers=auth_headers_parent)
        assert resp.status_code == 403


# ─── GET detail endpoint ─────────────────────────────────────────────

class TestGetAbsenceDetail:
    def test_parent_gets_own_request(
        self, client, auth_headers_parent, parent_user, sample_child, active_enrollment,
    ):
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "تفاصيل",
        }, headers=auth_headers_parent)
        assert create_resp.status_code == 201
        rid = create_resp.json()["id"]

        detail = client.get(f"/api/absence-requests/{rid}", headers=auth_headers_parent)
        assert detail.status_code == 200
        data = detail.json()
        assert data["id"] == rid
        assert data["child_name"]
        assert data["reason"] == "تفاصيل"

    def test_manager_gets_request_in_scope(
        self, client, auth_headers_parent, auth_headers_manager,
        parent_user, manager_user, sample_child, active_enrollment,
    ):
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "عرض مدير",
        }, headers=auth_headers_parent)
        rid = create_resp.json()["id"]

        detail = client.get(f"/api/absence-requests/{rid}", headers=auth_headers_manager)
        assert detail.status_code == 200
        data = detail.json()
        assert data["id"] == rid
        assert data["child_name"]

    def test_detail_not_found(self, client, auth_headers_parent, parent_user):
        resp = client.get("/api/absence-requests/99999", headers=auth_headers_parent)
        assert resp.status_code == 404

    def test_supervisor_cannot_read_detail(
        self, client, auth_headers_parent, auth_headers_supervisor,
        parent_user, supervisor_user, sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "supervisor must not read",
        }, headers=auth_headers_parent)
        assert created.status_code == 201

        resp = client.get(
            f"/api/absence-requests/{created.json()['id']}",
            headers=auth_headers_supervisor,
        )
        assert resp.status_code == 403

    def test_admin_can_read_detail(
        self, client, auth_headers_parent, auth_headers_admin,
        parent_user, admin_user, sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "admin national detail",
        }, headers=auth_headers_parent)
        assert created.status_code == 201

        resp = client.get(
            f"/api/absence-requests/{created.json()['id']}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created.json()["id"]


# ─── Cross-KG scope check ────────────────────────────────────────────

class TestCrossKGScope:
    @staticmethod
    def _other_manager_headers(test_db, kindergarten_id, username="other_manager_read"):
        other_mgr = models.User(
            username=username,
            email=f"{username}@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kindergarten_id,
        )
        test_db.add(other_mgr)
        test_db.commit()
        from auth import create_access_token
        token = create_access_token(data={"sub": other_mgr.username})
        return {"Authorization": f"Bearer {token}"}

    def test_foreign_manager_cannot_list_or_read_request(
        self, client, test_db, auth_headers_parent, parent_user,
        sample_child, active_enrollment,
    ):
        created = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "cross tenant read",
        }, headers=auth_headers_parent)
        assert created.status_code == 201

        other_kg = models.Kindergarten(
            name_ar="Other read KG",
            name_en="Other read KG",
            license_number="OTHER-READ-999",
            governorate="Amman",
            district="Amman",
            area="Sweileh",
            contact_phone="0551111112",
            address_line="Other read street",
        )
        test_db.add(other_kg)
        test_db.commit()
        headers = self._other_manager_headers(test_db, other_kg.id)

        listed = client.get("/api/absence-requests", headers=headers)
        assert listed.status_code == 200
        assert created.json()["id"] not in {item["id"] for item in listed.json()}

        detail = client.get(
            f"/api/absence-requests/{created.json()['id']}", headers=headers
        )
        assert detail.status_code == 404

    def test_approve_from_other_kg_forbidden(
        self, client, test_db, auth_headers_parent, parent_user,
        sample_child, active_enrollment, sample_kindergarten,
    ):
        """Manager from a different KG cannot approve."""
        # Create another KG + manager
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى",
            name_en="Other KG",
            license_number="OTHER-999",
            governorate="Amman",
            district="Amman",
            area="Sweileh",
            contact_phone="0551111111",
            address_line="شارع آخر",
        )
        test_db.add(other_kg)
        test_db.flush()

        other_mgr = models.User(
            username="other_manager",
            email="other_mgr@test.com",
            hashed_password="$2b$12$LJ3m4ys3Lz0BCNtNml4sAu4aN/v1lYGFhGl6Q2YO1eA3HIkfHB.MW",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=other_kg.id,
        )
        test_db.add(other_mgr)
        test_db.commit()

        # Parent creates absence in their KG
        create_resp = client.post("/api/absence-requests", json={
            "child_id": sample_child.id,
            "start_date": _tomorrow(),
            "end_date": _day_after(),
            "reason": "اختبار نطاق",
        }, headers=auth_headers_parent)
        assert create_resp.status_code == 201
        rid = create_resp.json()["id"]

        # Log in as other manager
        login_resp = client.post("/api/auth/login", data={
            "username": "other_manager",
            "password": "Test1234!",
        })
        # The other manager may or may not be able to log in depending on password
        # Use direct token approach
        from auth import create_access_token
        token = create_access_token(data={"sub": other_mgr.username})
        other_headers = {"Authorization": f"Bearer {token}"}

        approve_resp = client.post(
            f"/api/absence-requests/{rid}/approve",
            json={},
            headers=other_headers,
        )
        assert approve_resp.status_code == 404

        reject_resp = client.post(
            f"/api/absence-requests/{rid}/reject",
            json={},
            headers=other_headers,
        )
        assert reject_resp.status_code == 404
