"""
End-to-end Manager workflow integration test.

Builds two complete kindergartens (A and B) and drives the full manager
operational loop through the real HTTP routes:

dashboard -> create class -> assign supervisor -> view children ->
move child -> review daily report -> edit -> send to parent ->
read-only enforcement -> absence decision -> dashboard reflects state ->
AuditLog contains every expected event.

Then verifies Manager A cannot touch any KG B resource through the same
routes.
"""
from datetime import date, timedelta

import pytest

import models
from main import app
from auth import get_password_hash
from dependencies import get_current_user
from utils.time_utils import today_amman


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _mk_kg(db, suffix):
    kg = models.Kindergarten(
        name_ar=f"حضانة {suffix}", name_en=f"KG {suffix}",
        governorate="عمّان", district="عمّان", area="الرابية",
        address_line="شارع", contact_phone="0790000001",
        contact_email=f"e2e_{suffix}@example.com",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg); db.commit(); db.refresh(kg)
    return kg


def _mk_user(db, username, role, kg_id):
    u = models.User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("Test@1234"),
        full_name=username, role=role, kindergarten_id=kg_id,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_parent(db, username, kg_id):
    user = _mk_user(db, username, models.UserRole.PARENT, kg_id)
    profile = models.ParentProfile(
        user_id=user.id, first_name="ولي", last_name="أمر",
        phone_number="0791111111", gender=models.Gender.MALE,
        nationality="الأردن", national_id=f"99{user.id:08d}",
        home_governorate="عمّان", home_district="عمّان",
        home_area="الرابية", home_address_line="شارع",
    )
    db.add(profile); db.commit(); db.refresh(profile)
    return user, profile


def _mk_child(db, parent_profile, first_name):
    child = models.Child(
        parent_id=parent_profile.id, first_name=first_name, last_name="اختبار",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="أب", mother_first_name="أم", mother_last_name="اختبار",
        mother_nationality="الأردن",
    )
    db.add(child); db.commit(); db.refresh(child)
    return child


def _mk_class(db, kg_id, name, code, capacity=10):
    cls = models.Class(
        kindergarten_id=kg_id, name_ar=name, name_en=name, class_code=code,
        age_group="AGE_2_4", capacity_total=capacity,
        min_age_months=24, max_age_months=72, is_active=True,
    )
    db.add(cls); db.commit(); db.refresh(cls)
    return cls


def _mk_enrollment(db, kg_id, child_id, class_id):
    e = models.EnrollmentApplication(
        child_id=child_id, kindergarten_id=kg_id, class_id=class_id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=date.today(), class_assignment_date=date.today(),
    )
    db.add(e); db.commit(); db.refresh(e)
    return e


def _mk_report(db, kg_id, child_id, supervisor_id, when=None):
    r = models.DailyReport(
        child_id=child_id, kindergarten_id=kg_id,
        date=when or today_amman(),
        status=models.DailyReportStatus.SUBMITTED,
        submitted_by=supervisor_id,
        arrival_time="08:00", leave_time="14:00",
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


def _mk_absence(db, kg_id, parent_profile_id, child_id, class_id):
    a = models.AbsenceRequest(
        parent_id=parent_profile_id, child_id=child_id,
        kindergarten_id=kg_id, class_id=class_id,
        start_date=date.today() + timedelta(days=2),
        end_date=date.today() + timedelta(days=2),
        reason="مرض", status=models.AbsenceRequestStatus.SUBMITTED,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


@pytest.fixture
def world(test_db):
    """Two fully-populated kindergartens."""
    w = {}
    for suffix in ("A", "B"):
        kg = _mk_kg(test_db, suffix)
        manager = _mk_user(test_db, f"e2e_mgr_{suffix}", models.UserRole.MANAGER, kg.id)
        supervisor = _mk_user(test_db, f"e2e_sup_{suffix}", models.UserRole.SUPERVISOR, kg.id)
        parent_user, parent_profile = _mk_parent(test_db, f"e2e_par_{suffix}", kg.id)
        cls = _mk_class(test_db, kg.id, f"صف {suffix}", f"E2E-{suffix}1")
        child = _mk_child(test_db, parent_profile, f"طفل{suffix}")
        enrollment = _mk_enrollment(test_db, kg.id, child.id, cls.id)
        report = _mk_report(test_db, kg.id, child.id, supervisor.id)
        absence = _mk_absence(test_db, kg.id, parent_profile.id, child.id, cls.id)
        w[suffix] = dict(kg=kg, manager=manager, supervisor=supervisor,
                         parent_user=parent_user, parent_profile=parent_profile,
                         cls=cls, child=child, enrollment=enrollment,
                         report=report, absence=absence)
    return w


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _audit_actions(db, entity_type=None):
    q = db.query(models.AuditLog.action)
    if entity_type:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    return [row[0] for row in q.all()]


class TestManagerE2EWorkflow:
    def test_full_manager_workflow_and_isolation(self, client, test_db, world):
        A, B = world["A"], world["B"]
        _as(A["manager"])

        # 1. Dashboard: reflects the pending workload of KG A only.
        r = client.get("/api/manager/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kindergarten"]["id"] == A["kg"].id
        assert d["summary"]["pending_daily_reports"] == 1
        assert d["summary"]["pending_absence_requests"] == 1
        assert d["summary"]["active_enrollments"] == 1

        # 2. Create a second class through the canonical classes API.
        r = client.post("/api/classes", json={
            "kindergarten_id": A["kg"].id, "name_ar": "صف جديد أ",
            "name_en": "New A", "class_code": "E2E-A2", "age_group": "AGE_2_4",
            "capacity_total": 5, "min_age_months": 24, "max_age_months": 72,
            "supervisor_id": A["supervisor"].id,
        })
        assert r.status_code == 201, r.text
        new_class_id = r.json()["id"]

        # 3. Assign the supervisor to the original class (audited path —
        # class creation above already auto-assigned them to the new class).
        r = client.post("/api/manager/classes/assign-supervisor", json={
            "class_id": A["cls"].id, "supervisor_id": A["supervisor"].id,
            "is_primary": True,
        })
        assert r.status_code == 201, r.text
        assert not r.json().get("already_exists")

        # 4. Children list is scoped to KG A.
        r = client.get("/api/manager/children")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["children"]]
        assert A["child"].id in ids
        assert B["child"].id not in ids

        # 5. Move the child into the new class.
        r = client.post("/api/manager/children/move-class", json={
            "child_id": A["child"].id,
            "from_class_id": A["cls"].id,
            "to_class_id": new_class_id,
        })
        assert r.status_code == 200, r.text

        # 6. Review queue shows the submitted report; edit it.
        r = client.get("/api/manager/daily-reports")
        assert r.status_code == 200
        assert any(rep["id"] == A["report"].id for rep in r.json())

        r = client.put(f"/api/manager/daily-reports/{A['report'].id}",
                       json={"notes": "ملاحظات المدير"})
        assert r.status_code == 200, r.text

        # 7. Send to parent; a notification Message is created.
        r = client.put(f"/api/manager/daily-reports/{A['report'].id}/send-to-parents")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "SENT_TO_PARENT"
        note = test_db.query(models.Message).filter(
            models.Message.recipient_id == A["parent_user"].id
        ).first()
        assert note is not None, "parent notification message missing"

        # 8. Sent report is read-only; double-send is rejected.
        r = client.put(f"/api/manager/daily-reports/{A['report'].id}",
                       json={"notes": "تعديل ممنوع"})
        assert r.status_code == 403
        r = client.put(f"/api/manager/daily-reports/{A['report'].id}/send-to-parents")
        assert r.status_code == 400

        # 9. Decide the absence request.
        r = client.post(f"/api/absence-requests/{A['absence'].id}/approve", json={})
        assert r.status_code == 200, r.text

        # 10. Dashboard reflects the completed work.
        r = client.get("/api/manager/dashboard")
        d = r.json()
        assert d["summary"]["pending_daily_reports"] == 0
        assert d["summary"]["pending_absence_requests"] == 0
        assert d["summary"]["reports_sent_today"] == 1

        # 11. AuditLog contains every expected event.
        actions = _audit_actions(test_db)
        for expected in ("SUPERVISOR_ASSIGNED", "CHILD_MOVED_CLASS",
                         "DAILY_REPORT_EDITED", "DAILY_REPORT_SENT_TO_PARENT",
                         "ABSENCE_REQUEST_APPROVED"):
            assert expected in actions, f"missing audit event {expected}"

        # 12. Isolation: every route used above rejects KG B resources.
        r = client.get(f"/api/classes/{B['cls'].id}")
        assert r.status_code == 403
        r = client.post("/api/manager/classes/assign-supervisor", json={
            "class_id": B["cls"].id, "supervisor_id": A["supervisor"].id,
        })
        assert r.status_code == 403
        r = client.post("/api/manager/children/move-class", json={
            "child_id": B["child"].id, "from_class_id": B["cls"].id,
            "to_class_id": new_class_id,
        })
        assert r.status_code == 403
        r = client.put(f"/api/manager/daily-reports/{B['report'].id}",
                       json={"notes": "تسلل"})
        assert r.status_code == 403
        r = client.put(f"/api/manager/daily-reports/{B['report'].id}/send-to-parents")
        assert r.status_code == 403
        r = client.post(f"/api/absence-requests/{B['absence'].id}/approve", json={})
        assert r.status_code == 403
        r = client.get("/api/manager/daily-reports")
        assert all(rep["id"] != B["report"].id for rep in r.json())

        # KG B state is untouched.
        test_db.refresh(B["report"]); test_db.refresh(B["absence"])
        assert B["report"].status == models.DailyReportStatus.SUBMITTED
        assert B["absence"].status == models.AbsenceRequestStatus.SUBMITTED

        app.dependency_overrides.clear()
